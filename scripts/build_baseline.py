"""Build the versioned baseline from verified observations and complete-day raw windows."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from pathlib import Path
from baseline_profile import VERSION, CATALOG, map_profile
from baseline_contract import PROFILE, SAMPLE, document, validate
from baseline_windows import ROOT, observations, sha


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


@contextmanager
def writer(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as binary, gzip.GzipFile(filename='', mode='wb', fileobj=binary, mtime=0) as f:
        yield lambda value: f.write((json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode())


def read(path):
    with gzip.open(path, 'rt') as f:
        for line in f:
            yield json.loads(line)


def csv_write(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, v in value.items():
            yield from leaves(v, prefix + '.' + key if prefix else key)
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        for i, v in enumerate(value):
            name = v.get('type') or (v.get('subject_id', '') + ':' + v.get('behavior', '') if 'behavior' in v else str(i + 1))
            yield from leaves(v, prefix + '.' + name)
    else:
        yield prefix, value


def render(sample):
    return {'schema_version': VERSION, 'sample_id': sample['sample_id'], 'messages': [
        {'role': 'system', 'content': '根据家庭资料、此前七天用电和目标日条件预测目标日整户电量。每个数值为一个时间区间的kWh；间隔由interval_minutes给出。null表示未知，不能当作零。只输出含energy_kwh数组的JSON，按目标窗口时间排序。'},
        {'role': 'user', 'content': json.dumps(sample['input'], ensure_ascii=False, separators=(',', ':'), allow_nan=False)},
        {'role': 'assistant', 'content': json.dumps(sample['output'], ensure_ascii=False, separators=(',', ':'), allow_nan=False)}],
        'metadata': {'profile_id': sample['metadata']['profile_id'], 'formal_training_release': False,
                     'availability': sample['metadata']['availability'],
                     'loss_scope_required': 'assistant_content_only_not_implemented_by_this_export'}}


def build(cache, out):
    report = json.loads(cache.with_suffix('.report.json').read_text())
    assert sha(cache) == report['cache_sha256'], 'Window cache changed'
    profiles, original_ids, source_groups = {}, set(), {}
    mappings, coverage, categories, counts, profile_counts = [], defaultdict(Counter), defaultdict(set), Counter(), Counter()
    for source in ('sgsc', 'iflex'):
        field_usage = defaultdict(set)
        with writer(out / 'profiles' / (source + '.jsonl.gz')) as write:
            for row in observations(source):
                original_ids.add(row['sample_id'])
                source_groups[row['sample_id']] = row['metadata']['evidence_group'] if 'evidence_group' in row['metadata'] else row['metadata'].get('condition_evidence_group')
                key = source + ':' + row['household_id']
                if key in profiles:
                    continue
                profile, meta = map_profile(row)
                validate(profile, PROFILE)
                assert [a['type'] for a in profile['appliances']] == list(CATALOG)
                for path, evidence in meta['field_evidence'].items():
                    for field in evidence['source_fields']:
                        field_usage[field].add(path)
                for path, value in leaves(profile):
                    coverage[(source, path)]['known' if value is not None else 'unknown'] += 1
                    if isinstance(value, str): categories[path].add(value)
                    elif isinstance(value, list):
                        categories[path].update(v for v in value if isinstance(v, str))
                record = {'schema_version': VERSION, 'profile_id': key, 'source': source,
                          'household_id': row['household_id'], 'profile': profile, 'metadata': meta}
                profiles[key] = record
                write(record)
                profile_counts[source] += 1
        # Every source column has a destination or an explicit exclusion from model input.
        with (ROOT / 'provenance' / (source + '_extraction_inventory.csv')).open(encoding='utf-8-sig') as f:
            inventory = list(csv.DictReader(f))
        for row in inventory:
            field = row['field']
            destinations = sorted(field_usage[field])
            disposition = 'semantic_profile' if destinations else row['disposition']
            reason = 'Typed semantic mapping; original answer and unknown/invalid states retained.'
            if field in ('GENERAL_SUPPLY_CNT', 'CONTROLLED_LOAD_CNT', 'NET_SOLAR_CNT', 'GROSS_SOLAR_CNT', 'OTHER_LOAD_CNT', 'HAS_GENERATION'):
                destinations = ['input.context.measurement_scope', 'profile.metadata.source_profile_provenance.raw_answers.' + field]
                disposition = 'meter_context_and_provenance'
                reason = 'Meter coverage in context; original registry counts retained outside model input.'
            elif field == 'HAS_AGREED_TO_SMS':
                disposition = 'administrative_only'
                reason = 'Contact permission is not a household behavior or event consent.'
            elif not destinations:
                assert row['disposition'] != 'structured_input', ('Unmapped previously extracted field', source, field)
                reason = row['reason']
            mappings.append({'source': source, 'source_field': field, 'disposition': disposition,
                             'destinations': json.dumps(destinations, ensure_ascii=False), 'reason': reason})
    dump(out / 'schema/profile.schema.json', document(PROFILE, 'profile.schema.json'))
    dump(out / 'schema/sample.schema.json', document(SAMPLE, 'sample.schema.json'))
    dump(out / 'schema/appliance_catalog.json', {'schema_version': VERSION, 'categories': list(CATALOG),
                                               'overlap_policy': 'No total device count; geothermal/shared heating stay in services; heat pumps across services are not duplicated.'})
    dump(out / 'schema/category_values.json', {k: sorted(v) for k, v in sorted(categories.items())})
    csv_write(out / 'provenance/source_field_mapping.csv', mappings, ['source', 'source_field', 'disposition', 'destinations', 'reason'])
    csv_write(out / 'provenance/profile_field_coverage.csv',
              [{'source': s, 'field': p, 'known': c['known'], 'unknown': c['unknown'], 'applicable_rows': c.total() if hasattr(c, 'total') else sum(c.values())}
               for (s, p), c in sorted(coverage.items())], ['source', 'field', 'known', 'unknown', 'applicable_rows'])
    dump(out / 'provenance/raw_curve_sources.json', report['source_files'])
    dump(out / 'provenance/window_exclusions.json', report['exclusions'])
    split_entries, used_ids, sample_ids, selected = [], set(), set(), {}
    household_lists = defaultdict(set)
    for w in read(cache): household_lists[w['source']].add(w['household_id'])
    splits = {}
    for source, households in household_lists.items():
        ordered = sorted(households, key=lambda h: hashlib.sha256(('household-baseline-v1|' + source + '|' + h).encode()).hexdigest())
        a, b = int(.7 * len(ordered)), int(.85 * len(ordered))
        for i, h in enumerate(ordered): splits[source + ':' + h] = 'train' if i < a else 'validation' if i < b else 'test'
    with ExitStack() as stack:
        writers = {s: stack.enter_context(writer(out / 'data' / (s + '.jsonl.gz'))) for s in ('sgsc', 'iflex')}
        for w in read(cache):
            key = w['source'] + ':' + w['household_id']
            sample_id = key + ':' + w['date']
            assert sample_id not in sample_ids
            sample_ids.add(sample_id)
            assert not used_ids.intersection(w['source_sample_ids'])
            used_ids.update(w['source_sample_ids'])
            sample = {'schema_version': VERSION, 'sample_id': sample_id,
                      'input': {'profile': profiles[key]['profile'], 'history': w['history'], 'context': w['context']},
                      'output': w['output'],
                      'metadata': {'source': w['source'], 'profile_id': key, 'source_sample_ids': w['source_sample_ids'],
                                   'raw_curve_sha256': w['raw_curve_sha256'],
                                   'condition_evidence_groups': sorted(set(source_groups[i] or 'recorded_source_condition' for i in w['source_sample_ids'])),
                                   'construction_status': 'verified_measured_household_day',
                                   'availability': {'history_precedes_origin': True, 'profile_individual_time_verified': False,
                                                    'event_notice_individual_time_verified': False,
                                                    'event_notice_protocol': 'previous_day_15_00' if w['source'] == 'iflex' else None},
                                   'formal_training_release': False}}
            validate(sample, SAMPLE)
            writers[w['source']](sample)
            counts[w['source']] += 1
            split_entries.append({'sample_id': sample_id, 'profile_id': key, 'source': w['source'], 'split': splits[key]})
            if w['source'] not in selected or (w['household_id'], w['date']) in [('10041674', '2013-01-17'), ('Exp_1', '2020-02-11')]:
                selected[w['source']] = sample
    excluded_ids = {i for x in report['exclusions'] for i in x['source_sample_ids']}
    assert used_ids.isdisjoint(excluded_ids) and used_ids | excluded_ids == original_ids
    assert dict(counts) == report['counts']
    csv_write(out / 'splits/household_holdout.csv', split_entries, ['sample_id', 'profile_id', 'source', 'split'])
    for source, sample in selected.items():
        dump(out / 'examples' / (source + '.json'), sample)
        dump(out / 'examples' / (source + '_messages.json'), render(sample))
    artifacts = {}
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.name not in ('manifest.json', 'validation.json') and path.suffix != '.md':
            artifacts[str(path.relative_to(out))] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    dump(out / 'manifest.json', {
        'schema_version': VERSION, 'data_release_status': 'constructed_observation_baseline',
        'formal_training_release': False, 'counts': dict(counts), 'profile_counts': dict(profile_counts),
        'households_with_day_samples': {s: len(v) for s, v in household_lists.items()},
        'source_observation_count': len(original_ids), 'included_source_observations': len(used_ids),
        'excluded_source_observations': len(excluded_ids), 'excluded_days': len(report['exclusions']),
        'original_observation_files': {s: sha(ROOT / 'data' / (s + '.jsonl.gz')) for s in ('sgsc', 'iflex')},
        'window_cache_sha256': report['cache_sha256'], 'artifacts': artifacts,
        'implementation_files': {name: sha(ROOT / 'scripts' / name) for name in
                                 ('baseline_profile.py', 'baseline_contract.py', 'baseline_windows.py',
                                  'build_baseline.py', 'verify_baseline.py', 'read_baseline.py', 'export_baseline_sft.py')},
        'time_contract': '7 preceding source-clock days to 1 complete source-clock day; no UTC assumption',
        'split_contract': '70/15/15 by distinct households within source, frozen hash order; measures unseen-household generalization, dates may overlap',
        'remaining_training_checks': ['individual_profile_acquisition_time', 'individual_event_notice_delivery_time',
                                      'model_tokenizer_and_context_length', 'assistant_loss_mask'],
        'training_executed': False, 'imputation_performed': False})
    print(json.dumps({'sample_counts': dict(counts), 'profile_counts': dict(profile_counts), 'excluded_days': len(report['exclusions'])}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-cache', type=Path, default=ROOT / 'outputs/baseline_windows.jsonl.gz')
    parser.add_argument('--output', type=Path, default=ROOT / 'baseline/v1')
    args = parser.parse_args()
    build(args.window_cache, args.output)
