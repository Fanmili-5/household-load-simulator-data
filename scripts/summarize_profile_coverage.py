"""Summarize information coverage among households with retained benchmark days."""
import argparse
import gzip
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    with gzip.open(path, 'rt') as f:
        yield from map(json.loads, f)


def summarize(root):
    result = {'schema_version': 'household-benchmark/1.0.0',
              'cohort': 'distinct households with at least one retained day; not all archived profiles',
              'known_definition': 'non-null, including explicit false or zero; not a positive ownership count',
              'denominator_note': 'Appliance presence percentage uses 20 fixed categories per household. It measures template coverage, not lost source records.',
              'benchmark_manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
              'sources': {}}
    for source in ('sgsc', 'iflex'):
        ids, days, complete, numeric_signal = set(), 0, 0, 0
        for r in read(root / 'data' / (source + '.jsonl.gz')):
            ids.add(r['metadata']['profile_id']); days += 1
            step = r['input']['history']['interval_minutes']
            complete += (len(r['input']['history']['energy_kwh']) == 7 * 1440 // step
                         and len(r['output']['energy_kwh']) == 1440 // step
                         and all(v is not None for v in r['input']['history']['energy_kwh'] + r['output']['energy_kwh']))
            numeric_signal += all(e['price_per_kwh'] is not None for e in r['input']['context']['events'])
        profiles = [r['profile'] for r in read(root / 'profiles' / (source + '.jsonl.gz')) if r['profile_id'] in ids]
        known = {}
        for path in ('household.resident_count', 'dwelling.type', 'dwelling.source_classified_type',
                     'dwelling.floor_area_m2.lower', 'preferences.living_room_comfort_temperature_c'):
            values = []
            for profile in profiles:
                value = profile
                for part in path.split('.'): value = value[part]
                values.append(value)
            known[path] = sum(v is not None for v in values)
        appliances = {}
        for device in profiles[0]['appliances']:
            key = device['type']
            values = [next(d for d in p['appliances'] if d['type'] == key) for p in profiles]
            appliances[key] = {'present_true': sum(d['present'] is True for d in values),
                               'present_false': sum(d['present'] is False for d in values),
                               'present_unknown': sum(d['present'] is None for d in values),
                               'count_known_including_zero': sum(d['count'] is not None for d in values),
                               'positive_count_known': sum(d['count'] is not None and d['count'] > 0 for d in values)}
        unknown = sum(d['present_unknown'] for d in appliances.values())
        result['sources'][source] = {'households': len(profiles), 'retained_days': days,
                                     'complete_history_and_target_days': complete,
                                     'days_with_numeric_price_sequence': numeric_signal,
                                     'known_households_by_field': known, 'appliances': appliances,
                                     'median_known_appliance_presence_categories': statistics.median(
                                         sum(d['present'] is not None for d in p['appliances']) for p in profiles),
                                     'unknown_presence_cells': unknown, 'all_presence_cells': len(profiles) * 20,
                                     'unknown_presence_percent': round(100 * unknown / (len(profiles) * 20), 3)}
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT / 'benchmark/v1')
    p.add_argument('--output', type=Path, default=ROOT / 'sharing/profile_coverage.json')
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(summarize(a.root), ensure_ascii=False, indent=2) + '\n')
