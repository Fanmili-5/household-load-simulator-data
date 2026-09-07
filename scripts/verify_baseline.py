"""Verify distributed baseline files, semantics, accounting, splits, and optionally every raw curve point."""
import argparse
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from baseline_contract import validate
from baseline_profile import CATALOG, VERSION
from baseline_windows import ROOT, sha, observations
from build_baseline import read, render, dump


def check_semantics(r):
    p, h, c = r['input']['profile'], r['input']['history'], r['input']['context']
    w = c['target_window']
    dt = datetime.fromisoformat
    assert h['end'] == c['forecast_origin'] == w['start']
    assert dt(h['end']) - dt(h['start']) == timedelta(days=7)
    assert dt(w['end']) - dt(w['start']) == timedelta(days=1)
    assert h['interval_minutes'] == w['interval_minutes']
    assert len(h['energy_kwh']) * h['interval_minutes'] == 7 * 1440
    assert len(r['output']['energy_kwh']) * w['interval_minutes'] == 1440
    assert [a['type'] for a in p['appliances']] == list(CATALOG)
    for a in p['appliances']:
        if a['present'] is False: assert a['count'] == 0
        if a['count'] is not None and a['count'] > 0: assert a['present'] is True
        # Neither source gives measured device power/storage capacity in this release.
        assert a['rated_power_w'] is None and a['capacity_kwh'] is None
    for b in (p['dwelling']['floor_area_m2'], p['dwelling']['construction_year'], p['household']['gross_income_band']):
        if b['lower'] is not None and b['upper'] is not None: assert b['lower'] <= b['upper']
    n = p['household']['resident_count']
    ages = list(p['household']['age_group_counts'].values())
    assert all(x is None for x in ages) or (all(x is not None for x in ages) and sum(ages) == n)
    for value in p['household']['life_status_counts'].values():
        if value is not None: assert n is not None and value <= n
    types = set(CATALOG)
    for habit in p['usage_habits']:
        if habit['subject_type'] == 'appliance_category': assert habit['subject_id'] in types
        if habit['subject_type'] == 'energy_service': assert habit['subject_id'] in p['energy_services']
    for e in c['events']:
        assert dt(w['start']) <= dt(e['start']) < dt(e['end']) <= dt(w['end'])
        if e['price_per_kwh'] is not None:
            assert len(e['price_per_kwh']) * e['price_interval_minutes'] * 60 == (dt(e['end']) - dt(e['start'])).total_seconds()
    assert r['metadata']['formal_training_release'] is False
    assert not r['metadata']['availability']['profile_individual_time_verified']
    assert set(r['input']) == {'profile', 'history', 'context'}
    # Check actual message serialization rather than assuming the renderer preserves values.
    messages = render(r)['messages']
    assert [x['role'] for x in messages] == ['system', 'user', 'assistant']
    assert json.loads(messages[1]['content']) == r['input']
    assert json.loads(messages[2]['content']) == r['output']
    assert 'raw_answers' not in messages[1]['content'] and 'source_sample_ids' not in messages[1]['content']


def raw_check(root, pipeline, manifest):
    receipts = json.loads((root / 'provenance/raw_curve_sources.json').read_text())
    by_file = {r['file']: r for r in receipts}
    raw_points = Counter()
    excluded_diagnostics = []
    exclusions = json.loads((root / 'provenance/window_exclusions.json').read_text())
    for source in ('sgsc', 'iflex'):
        expected = defaultdict(dict)
        for sample in read(root / 'data' / (source + '.jsonl.gz')):
            household = sample['metadata']['profile_id'].split(':', 1)[1]
            start = datetime.fromisoformat(sample['input']['history']['start'])
            step = sample['input']['history']['interval_minutes']
            values = sample['input']['history']['energy_kwh'] + sample['output']['energy_kwh']
            scope = sample['input']['context']['measurement_scope']
            for i, value in enumerate(values):
                time = start + timedelta(minutes=step * i)
                key = ((time + timedelta(minutes=step)).strftime('%Y-%m-%d %H:%M:%S') if source == 'sgsc'
                       else (time.date().isoformat(), time.hour + 1))
                if key in expected[household]: assert expected[household][key] == (value, scope)
                expected[household][key] = (value, scope)
        if source == 'sgsc':
            for i, (household, needed) in enumerate(sorted(expected.items())):
                file = 'runs/sgsc_all_response_branches_v2/raw/SGSC_' + household + '_interval.csv'
                path = pipeline / file
                assert sha(path) == by_file[file]['sha256']
                seen = Counter()
                household_exclusions = [x for x in exclusions if x['source'] == source and x['household_id'] == household]
                all_labels = Counter() if household_exclusions else None
                with path.open() as f:
                    for r in csv.DictReader(f, skipinitialspace=True):
                        key = r['READING_DATETIME'].strip()
                        if all_labels is not None: all_labels[key] += 1
                        if key not in needed: continue
                        assert r['CUSTOMER_ID'].strip() == household
                        seen[key] += 1
                        value, scope = needed[key]
                        general, controlled = float(r['GENERAL_SUPPLY_KWH']), float(r['CONTROLLED_LOAD_KWH'])
                        total = general if scope == 'single_general_supply' else general + controlled
                        assert math.isclose(value, total, rel_tol=1e-10, abs_tol=1e-9), (household, key, value, total, scope)
                        if scope == 'single_general_supply': assert controlled == 0
                        assert all(float(r[c]) == 0 for c in ('GROSS_GENERATION_KWH', 'NET_GENERATION_KWH', 'OTHER_KWH'))
                assert set(seen) == set(needed) and set(seen.values()) == {1}
                raw_points[source] += len(needed)
                for e in household_exclusions:
                    start = datetime.fromisoformat(e['date']) - timedelta(days=7)
                    times = [(start + timedelta(minutes=30 * n)).strftime('%Y-%m-%d %H:%M:%S') for n in range(1, 385)]
                    missing = [t for t in times if not all_labels[t]]
                    duplicate = [t for t in times if all_labels[t] > 1]
                    assert missing or duplicate
                    excluded_diagnostics.append({**e, 'missing_interval_end_labels': missing, 'duplicate_interval_end_labels': duplicate})
                if (i + 1) % 500 == 0: print('Raw verification:', source, i + 1, 'households', flush=True)
        else:
            file = 'runs/iflex_all_candidates_v1/source_stage/raw/iflex_candidates.csv'
            path = pipeline / file
            assert sha(path) == by_file[file]['sha256']
            seen = defaultdict(Counter)
            with path.open() as f:
                for r in csv.DictReader(f):
                    home = r['ID']
                    if home not in expected: continue
                    day = (datetime(1970, 1, 1) + timedelta(days=int(float(r['Date'])))).date().isoformat()
                    key = (day, int(float(r['Hour'])))
                    if key not in expected[home]: continue
                    assert math.isclose(float(r['Demand_kWh']), expected[home][key][0], rel_tol=1e-10, abs_tol=1e-9)
                    seen[home][key] += 1
            for home, needed in expected.items():
                assert set(seen[home]) == set(needed) and set(seen[home].values()) == {1}
                raw_points[source] += len(needed)
    return dict(raw_points), excluded_diagnostics


def verify(root, pipeline=None, reference_schema=False, write_report=False):
    manifest = json.loads((root / 'manifest.json').read_text())
    schemas = {k: json.loads((root / 'schema' / (k + '.schema.json')).read_text()) for k in ('profile', 'sample')}
    validators = {}
    if reference_schema:
        from jsonschema import Draft202012Validator
        for k, s in schemas.items():
            Draft202012Validator.check_schema(s)
            validators[k] = Draft202012Validator(s)
    for name, info in manifest['artifacts'].items():
        assert sha(root / name) == info['sha256'], name
        assert (root / name).stat().st_size == info['bytes'], name
    for name, digest in manifest.get('implementation_files', {}).items():
        assert sha(ROOT / 'scripts' / name) == digest, 'Implementation changed: ' + name
    profiles, sample_ids, source_ids = {}, set(), set()
    source_counts, home_sets, partition_counts = Counter(), defaultdict(set), Counter()
    with (root / 'splits/household_holdout.csv').open() as f: split_rows = list(csv.DictReader(f))
    split_by_sample = {r['sample_id']: r for r in split_rows}
    assert len(split_by_sample) == len(split_rows)
    home_split = {}
    for row in split_rows:
        key = row['profile_id']
        if key in home_split: assert home_split[key] == row['split']
        home_split[key] = row['split']
        partition_counts[row['source'] + '/' + row['split']] += 1
    for source in ('sgsc', 'iflex'):
        for r in read(root / 'profiles' / (source + '.jsonl.gz')):
            assert r['schema_version'] == VERSION and r['source'] == source
            assert r['profile_id'] not in profiles
            profiles[r['profile_id']] = r
            validate(r['profile'], schemas['profile'])
            if validators: validators['profile'].validate(r['profile'])
        for r in read(root / 'data' / (source + '.jsonl.gz')):
            validate(r, schemas['sample'])
            if validators: validators['sample'].validate(r)
            check_semantics(r)
            assert r['sample_id'] not in sample_ids
            sample_ids.add(r['sample_id'])
            assert not source_ids.intersection(r['metadata']['source_sample_ids'])
            source_ids.update(r['metadata']['source_sample_ids'])
            assert r['input']['profile'] == profiles[r['metadata']['profile_id']]['profile']
            assert split_by_sample[r['sample_id']]['profile_id'] == r['metadata']['profile_id']
            home_sets[source].add(r['metadata']['profile_id'])
            source_counts[source] += 1
            if source_counts[source] % 4000 == 0:
                print('File/schema verification:', source, source_counts[source], 'records', flush=True)
        example = json.loads((root / 'examples' / (source + '.json')).read_text())
        assert example['sample_id'] in sample_ids
        assert json.loads((root / 'examples' / (source + '_messages.json')).read_text()) == render(example)
    assert set(split_by_sample) == sample_ids
    assert dict(source_counts) == manifest['counts']
    assert {s: len(v) for s, v in home_sets.items()} == manifest['households_with_day_samples']
    exclusions = json.loads((root / 'provenance/window_exclusions.json').read_text())
    excluded_ids = {i for x in exclusions for i in x['source_sample_ids']}
    legacy_ids = set()
    for source in ('sgsc', 'iflex'):
        assert sha(ROOT / 'data' / (source + '.jsonl.gz')) == manifest['original_observation_files'][source]
        for r in observations(source):
            legacy_ids.add(r['sample_id'])
            key = source + ':' + r['household_id']
            assert profiles[key]['metadata']['source_profile_provenance'] == r['metadata']['profile_provenance']
    assert source_ids.isdisjoint(excluded_ids) and source_ids | excluded_ids == legacy_ids
    with (root / 'provenance/source_field_mapping.csv').open() as f: mapping = list(csv.DictReader(f))
    assert len(mapping) == 142 and len({(x['source'], x['source_field']) for x in mapping}) == 142
    report = {'passed': True, 'schema_version': VERSION, 'counts': dict(source_counts),
              'profiles': len(profiles), 'excluded_days': len(exclusions),
              'source_column_accounting': {'sgsc': 46, 'iflex': 96},
              'reference_json_schema_validator': reference_schema,
              'checks': ['artifact hashes', 'strict profile/sample schemas', 'time boundaries and native intervals',
                         'device presence/count semantics', 'household demographic consistency',
                         'profile equality across household days', 'complete original source-column accounting',
                         'original household provenance preserved', 'candidate inclusion/exclusion accounting',
                         'no household overlap across partitions', 'full SFT serialization round trip'],
              'split_record_counts': dict(partition_counts), 'raw_curve_points_verified': None,
              'formal_training_release': False, 'training_executed': False}
    if pipeline:
        points, diagnostics = raw_check(root, pipeline, manifest)
        report['raw_curve_points_verified'] = points
        report['excluded_window_diagnostics'] = diagnostics
        report['checks'].append('every required raw curve point checked independently; raw files hashed')
    if write_report: dump(root / 'validation.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'excluded_window_diagnostics'}, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT / 'baseline/v1')
    p.add_argument('--pipeline-root', type=Path)
    p.add_argument('--reference-json-schema', action='store_true')
    p.add_argument('--write-report', action='store_true')
    args = p.parse_args()
    verify(args.root, args.pipeline_root, args.reference_json_schema, args.write_report)
