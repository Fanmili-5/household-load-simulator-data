"""Rebuild the separate LIRNEasia 7-day -> 1-day benchmark from public excerpts."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'extensions/lirneasia_history_v1'
VERSION = 'lirneasia-day-ahead/1.0.0'
SALT = 'lirneasia-household-v1:'
STEP = timedelta(minutes=15)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def read_jsonl(path):
    with gzip.open(path, 'rt') as f:
        for line in f:
            yield json.loads(line)


def clean(row):
    # Source row identifiers are kept in sources, not semantic model input.
    return {k: v for k, v in row.items()
            if not k.endswith('_ID') and k not in ('household_id', 'w1', 'ethnicity', 'religion')}


def source_profiles(source):
    files = json.loads((source / 'manifest.json').read_text())['files']
    for name, expected in files.items():
        if digest(source / name) != expected:
            raise ValueError('Source hash mismatch: ' + name)
    profiles = {}
    for r in json.loads((source / 'household_profiles.json').read_text()):
        hid = r['household_ID']
        if hid in profiles:
            raise ValueError('Duplicate household')
        profiles[hid] = {'as_of': r['w1'], 'household': clean(r)}
    for module in ('demographics', 'appliances', 'ac_roster', 'fan_roster', 'light_roster', 'generation'):
        groups = defaultdict(list)
        for r in json.loads((source / ('household_' + module + '.json')).read_text()):
            if r['household_ID'] not in profiles:
                raise ValueError('Unknown household in source table')
            groups[r['household_ID']].append(clean(r))
        for hid, p in profiles.items():
            p[module] = groups[hid]
    return profiles


def split_households(ids):
    ordered = sorted(ids, key=lambda h: hashlib.sha256((SALT + h).encode()).hexdigest())
    train, validation = int(len(ordered) * .7), int(len(ordered) * .15)
    return {h: ('train' if i < train else 'validation' if i < train + validation else 'test')
            for i, h in enumerate(ordered)}


def validate_run(run):
    start = datetime.fromisoformat(run['start'])
    days = run['days']
    if type(days) is not int or days < 8 or start.time() != datetime.min.time() or run['interval_minutes'] != 15:
        raise ValueError('Invalid source run shape')
    imp, exp = run['import_register_kwh'], run['export_register_kwh']
    if len(imp) != days * 96 + 1 or len(exp) != len(imp):
        raise ValueError('Missing cumulative endpoint')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in imp + exp):
        raise ValueError('Invalid cumulative reading')
    values = [b - a for a, b in zip(imp, imp[1:])]
    if any(v < 0 for v in values) or any(b != a for a, b in zip(exp, exp[1:])):
        raise ValueError('Reset or export in selected run')
    return start, values


def zero_run(values):
    current = maximum = 0
    for v in values:
        current = current + 1 if v == 0 else 0
        maximum = max(maximum, current)
    return maximum


def build(source, out):
    if (out / 'manifest.json').exists():
        raise ValueError('Output already has a manifest; choose a new output directory')
    if any(out.resolve().is_relative_to((ROOT / p).resolve()) for p in ('benchmark', 'baseline')):
        raise ValueError('Cannot overwrite a frozen parent dataset')
    profiles = source_profiles(source)
    splits = split_households(profiles)
    out.mkdir(parents=True, exist_ok=True)
    for name in ('data', 'splits', 'examples', 'evaluation', 'quarantine'):
        (out / name).mkdir(exist_ok=True)
    counts = Counter()
    split_counts = Counter()
    quarantine_splits = Counter()
    retained_households = defaultdict(set)
    seen = set()
    seen_households = set()
    bounds = defaultdict(list)
    flagged = []
    first = None
    with (out / 'data/lirneasia.jsonl.gz').open('wb') as binary, \
            gzip.GzipFile(filename='', fileobj=binary, mode='wb', mtime=0) as data, \
            (out / 'quarantine/lirneasia.jsonl.gz').open('wb') as qb, \
            gzip.GzipFile(filename='', fileobj=qb, mode='wb', mtime=0) as quarantine, \
            (out / 'splits/household_holdout.csv').open('w', newline='') as sf:
        sw = csv.DictWriter(sf, fieldnames=['sample_id', 'household_id', 'split', 'status'])
        sw.writeheader()
        for run in read_jsonl(source / 'cumulative_runs.jsonl.gz'):
            hid = run['household_id']
            p = profiles[hid]
            start, values = validate_run(run)
            end = start + timedelta(days=run['days'])
            if any(start < b and end > a for a, b in bounds[hid]):
                raise ValueError('Overlapping source runs')
            bounds[hid].append((start, end))
            if start.date() <= datetime.fromisoformat(p['as_of']).date():
                raise ValueError('Survey is not before history')
            if len(p['demographics']) != int(p['household']['no_of_household_members']):
                raise ValueError('Household member count mismatch')
            seen_households.add(hid)
            counts['runs'] += 1
            counts['unique_intervals'] += len(values)
            for offset in range(run['days'] - 7):
                history_start = start + timedelta(days=offset)
                origin = history_start + timedelta(days=7)
                sid = 'lirneasia:' + hid + ':' + origin.date().isoformat()
                if sid in seen:
                    raise ValueError('Duplicate sample')
                seen.add(sid)
                observed = values[offset * 96:(offset + 8) * 96]
                maximum_zero = zero_run(observed)
                if maximum_zero >= 96:
                    flagged.append({'sample_id': sid, 'longest_exact_zero_hours': maximum_zero / 4})
                sample = {
                    'sample_id': sid, 'schema_version': VERSION,
                    'input': {
                        'profile': {k: v for k, v in p.items() if k != 'as_of'},
                        'history': {'start': history_start.isoformat(), 'end': origin.isoformat(),
                                    'interval_minutes': 15, 'energy_kwh': observed[:672]},
                        'context': {
                            'forecast_origin': origin.isoformat(),
                            'target_window': {'start': origin.isoformat(), 'end': (origin + timedelta(days=1)).isoformat(), 'interval_minutes': 15},
                            'time_basis': 'native_date_time; UTC offset and publication latency not independently established',
                            'measurement_scope': 'grid_import_interval_energy_kwh',
                            'calendar': {'target_weekday_monday_zero': origin.weekday()},
                        },
                    },
                    'output': {'energy_kwh': observed[672:]},
                    'metadata': {
                        'source': 'lirneasia', 'household_id': hid, 'split': splits[hid],
                        'profile_as_of': p['as_of'], 'profile_before_history_verified': True,
                        'input_availability': 'survey calendar date precedes history; meter publication latency unknown',
                        'quality': {'longest_exact_zero_hours': maximum_zero / 4, 'all_8day_intervals_observed': True},
                        'selection_uses_target_readings': True, 'actual_intervention_labels': False,
                        'status': 'quarantined_continuous_zero' if maximum_zero >= 96 else 'retained',
                        'formal_training_executed': False,
                    },
                }
                destination = quarantine if maximum_zero >= 96 else data
                destination.write((json.dumps(sample, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode())
                sw.writerow({'sample_id': sid, 'household_id': hid, 'split': splits[hid], 'status': sample['metadata']['status']})
                counts['qualified_windows'] += 1
                if maximum_zero >= 96:
                    counts['quarantined_samples'] += 1
                    quarantine_splits[splits[hid]] += 1
                else:
                    counts['samples'] += 1
                    split_counts[splits[hid]] += 1
                    retained_households[splits[hid]].add(hid)
                    first = sample if first is None else first
    if seen_households != set(profiles):
        raise ValueError('Profiles without samples')
    write_json(out / 'examples/lirneasia.json', first)
    write_json(out / 'evaluation/protocol.json', {
        'version': VERSION, 'task': 'asof_survey_day_ahead_grid_import',
        'history_steps': 672, 'target_steps': 96, 'native_interval_minutes': 15,
        'split': {'method': 'sort household IDs by SHA256(salt + ID), take floor(70%)/floor(15%)/remainder',
                  'salt': SALT, 'generalization': 'unseen households; calendar dates may overlap'},
        'input_variants': ['history_only', 'history_profile'],
        'variant_rule': 'Both retain target clock and calendar; history_profile additionally has the native survey modules.',
        'primary_metric': 'hourly_mae_kw',
        'secondary_metrics': ['hourly_rmse_kw', 'daily_energy_absolute_error_kwh', 'hourly_peak_absolute_error_kw', 'native_15min_mae_kw'],
        'aggregation': 'average daily metrics within each household, then equal average over households',
        'hourly_conversion': 'sum four consecutive 15min kWh; divide by 1 hour for average kW',
        'native_conversion': '15min kWh divided by 0.25 hour for native average kW',
        'quality': 'Preserve all 6660 audited windows; quarantine 335 with >=24h continuous exact-zero readings anywhere in 8 days; default evaluation uses 6325 windows from 410 households.',
        'limits': ['Target-dependent completeness/export screening is an offline cohort rule.',
                   'W1 snapshot does not prove equipment remained unchanged.',
                   'No tariff, notification, intervention, consent or causal-response labels.',
                   'No claims about future unseen dates, online availability or joint three-source ranking.'],
        'preprocessing': 'fit transforms on train only; tune on validation; freeze before test',
        'model_training_executed': False,
    })
    write_json(out / 'evaluation/zero_reading_review.json', {
        'quarantined_windows': len(flagged), 'threshold_hours': 24,
        'status': 'quarantined; original values preserved; no attribution to vacancy or meter faults', 'windows': flagged})
    artifacts = {str(p.relative_to(out)): digest(p) for directory in ('data', 'splits', 'examples', 'evaluation', 'quarantine')
                 for p in sorted((out / directory).iterdir()) if p.is_file()}
    manifest = {'version': VERSION, 'counts': dict(counts) | {'source_households': len(profiles), 'households': sum(map(len, retained_households.values()))},
                'split_source_households': dict(Counter(splits.values())),
                'split_households': {k:len(v) for k,v in retained_households.items()},
                'split_quarantined_samples': dict(quarantine_splits), 'split_samples': dict(split_counts),
                'source_manifest_sha256': digest(source / 'manifest.json'),
                'implementation_sha256': digest(Path(__file__)), 'artifacts': artifacts,
                'parent_benchmark_modified': False, 'model_training_executed': False}
    write_json(out / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, default=DEFAULT / 'sources')
    p.add_argument('--output', type=Path, default=DEFAULT)
    a = p.parse_args()
    print(json.dumps(build(a.source_dir, a.output), indent=2))
