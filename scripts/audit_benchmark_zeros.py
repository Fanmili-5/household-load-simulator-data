"""Review flagged SGSC windows against available raw readings and service records."""
import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from build_baseline import read, dump
from baseline_windows import ROOT, sha
from benchmark_quality import quality


def audit(pipeline, output):
    groups = defaultdict(list)
    for r in read(ROOT / 'baseline/v1/data/sgsc.jsonl.gz'):
        q = quality(r['input']['history']['energy_kwh'], r['output']['energy_kwh'], 30)
        if q['flags']:
            groups[r['metadata']['profile_id']].append((r, q))
    profiles = {r['profile_id']: r for r in read(ROOT / 'baseline/v1/profiles/sgsc.jsonl.gz')}
    result = []
    for key, samples in sorted(groups.items()):
        hh = key.split(':', 1)[1]
        path = pipeline / 'runs/sgsc_all_response_branches_v2/raw' / ('SGSC_' + hh + '_interval.csv')
        scope = samples[0][0]['input']['context']['measurement_scope']
        readings = []
        with path.open() as f:
            for r in csv.DictReader(f, skipinitialspace=True):
                value = float(r['GENERAL_SUPPLY_KWH'])
                if scope != 'single_general_supply': value += float(r['CONTROLLED_LOAD_KWH'])
                readings.append((datetime.fromisoformat(r['READING_DATETIME'].strip()), value))
        readings.sort()
        raw = profiles[key]['metadata']['source_profile_provenance']['raw_answers']
        record_dates = {k: v for k, v in raw.items() if k.endswith('_DATE')}
        for r, q in samples:
            start = datetime.fromisoformat(r['input']['history']['start'])
            end = datetime.fromisoformat(r['input']['context']['target_window']['end'])
            needed = [(t, v) for t, v in readings if start < t <= end]
            assert [v for t, v in needed] == r['input']['history']['energy_kwh'] + r['output']['energy_kwh']
            positive_before = [t for t, v in readings if t <= start and v > 0]
            positive_after = [t for t, v in readings if t > end and v > 0]
            result.append({'sample_id': r['sample_id'], 'quality': q,
                           'raw_file': str(path.relative_to(pipeline)), 'raw_sha256': sha(path),
                           'raw_window_exactly_matches': True,
                           'last_positive_before_window': max(positive_before).isoformat() if positive_before else None,
                           'first_positive_after_window': min(positive_after).isoformat() if positive_after else None,
                           'available_raw_start': readings[0][0].isoformat(),
                           'available_raw_end': readings[-1][0].isoformat(),
                           'recorded_service_status': raw['SERVICE_LOC_STATUS_NAME'],
                           'recorded_dates': record_dates,
                           'diagnosis': 'No timestamped outage, occupancy or meter-health evidence establishes the cause; registry status is not a day-specific diagnosis.'})
    dump(output, {'audit': 'raw_zero_window_review_v1', 'records': result,
                  'policy': 'Preserve raw readings; quarantine any continuous 24-hour zero run in history or target; near-zero alone is a review flag, not an exclusion.'})
    print({'flagged_windows_reviewed': len(result), 'households': len(groups)})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pipeline-root', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'benchmark/source_evidence_v1/zero_review.json')
    a = p.parse_args()
    audit(a.pipeline_root, a.output)
