"""Extract complete measured household days; no resampling or filling missing reads."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def observations(source):
    with gzip.open(ROOT / 'data' / (source + '.jsonl.gz'), 'rt') as f:
        for line in f:
            yield json.loads(line)


def day_of(r):
    return (r['input']['context']['start_local'][:10] if r['source'] == 'sgsc'
            else r['target']['date'])


def events(rows, start, step):
    result = []
    for r in rows:
        c = r['input']['context']
        if r['source'] == 'sgsc':
            e = dict(start=c['start_local'].replace(' ', 'T'), end=c['end_local'].replace(' ', 'T'),
                     type={'DPP': 'peak_price_penalty', 'DPR': 'reduction_reward'}[c['event_type']],
                     currency='AUD', price_per_kwh=None, price_interval_minutes=None,
                     rate_per_reduced_kwh=None)
        else:
            e = dict(start=start.isoformat(), end=(start + timedelta(days=1)).isoformat(),
                     type='experimental_price_for_reward_calculation', currency='NOK',
                     price_per_kwh=c['experimental_price_NOK_per_kwh'], price_interval_minutes=step,
                     rate_per_reduced_kwh=None)
        if e not in result:
            result.append(e)
    return sorted(result, key=lambda e: (e['start'], e['end'], e['type']))


def extract(pipeline, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    exclusions, receipts, counts = [], [], defaultdict(int)
    temp = destination.with_suffix('.tmp')
    with temp.open('wb') as binary, gzip.GzipFile(filename='', mode='wb', fileobj=binary, mtime=0) as output:
        for source in ('sgsc', 'iflex'):
            groups = defaultdict(lambda: defaultdict(list))
            for r in observations(source):
                groups[r['household_id']][day_of(r)].append(r)
            iflex = defaultdict(dict)
            if source == 'iflex':
                path = pipeline / 'runs/iflex_all_candidates_v1/source_stage/raw/iflex_candidates.csv'
                digest = sha(path)
                receipts.append({'source': source, 'file': str(path.relative_to(pipeline)), 'sha256': digest})
                with path.open() as f:
                    for r in csv.DictReader(f):
                        if r['ID'] not in groups:
                            continue
                        day = (datetime(1970, 1, 1) + timedelta(days=int(float(r['Date'])))).date().isoformat()
                        key = (day, int(float(r['Hour'])))
                        value = float(r['Demand_kWh'])
                        if key in iflex[r['ID']]:
                            iflex[r['ID']][key] = None
                        else:
                            iflex[r['ID']][key] = value
            for idx, (household, days) in enumerate(sorted(groups.items())):
                if source == 'sgsc':
                    path = pipeline / 'runs/sgsc_all_response_branches_v2/raw' / f'SGSC_{household}_interval.csv'
                    digest = sha(path)
                    receipts.append({'source': source, 'household_id': household,
                                     'file': str(path.relative_to(pipeline)), 'sha256': digest})
                    readings = {}
                    with path.open() as f:
                        for r0 in csv.DictReader(f, skipinitialspace=True):
                            r = {k.strip(): v.strip() for k, v in r0.items()}
                            if r['CUSTOMER_ID'] != household:
                                raise ValueError('Raw household mismatch: ' + household)
                            key = r['READING_DATETIME']
                            if key in readings:
                                readings[key] = None
                            else:
                                readings[key] = r
                for day, rows in sorted(days.items()):
                    start = datetime.fromisoformat(day)
                    hist_start, end = start - timedelta(days=7), start + timedelta(days=1)
                    step = 30 if source == 'sgsc' else 60
                    n = 1440 // step
                    reasons = []
                    channels = None
                    if source == 'sgsc':
                        labels = [(hist_start + timedelta(minutes=step * i)).strftime('%Y-%m-%d %H:%M:%S')
                                  for i in range(1, n * 8 + 1)]
                        selected = [readings.get(t) for t in labels]
                        if any(r is None for r in selected):
                            reasons.append('missing_or_duplicate_interval')
                        else:
                            try:
                                channels = {k: [float(r[k]) for r in selected] for k in
                                            ('GENERAL_SUPPLY_KWH', 'CONTROLLED_LOAD_KWH',
                                             'GROSS_GENERATION_KWH', 'NET_GENERATION_KWH', 'OTHER_KWH')}
                            except ValueError:
                                reasons.append('invalid_numeric_interval')
                            if channels is not None:
                                controlled = rows[0]['input']['profile']['meter_configuration']['CONTROLLED_LOAD_CNT'] == '1'
                                forbidden = ['GROSS_GENERATION_KWH', 'NET_GENERATION_KWH', 'OTHER_KWH']
                                if not controlled:
                                    forbidden.append('CONTROLLED_LOAD_KWH')
                                if any(v != 0 for k in forbidden for v in channels[k]):
                                    reasons.append('unexpected_nonzero_meter_channel')
                                values = [g + c if controlled else g for g, c in
                                          zip(channels['GENERAL_SUPPLY_KWH'], channels['CONTROLLED_LOAD_KWH'])]
                    else:
                        keys = [((hist_start + timedelta(days=d)).date().isoformat(), hour)
                                for d in range(8) for hour in range(1, 25)]
                        values = [iflex[household].get(key) for key in keys]
                        if any(v is None for v in values):
                            reasons.append('missing_or_duplicate_interval')
                    if not reasons and any(not math.isfinite(v) or v < 0 for v in values):
                        reasons.append('nonfinite_or_negative_interval')
                    if not reasons:
                        history, target = values[:n * 7], values[n * 7:]
                        for r in rows:
                            if source == 'sgsc':
                                c = r['input']['context']
                                lo = int((datetime.fromisoformat(c['start_local']) - start).total_seconds() / (step * 60))
                                hi = int((datetime.fromisoformat(c['end_local']) - start).total_seconds() / (step * 60))
                                subset = target[lo:hi]
                                old_hist = [v for h in r['input']['history'] for v in h['energy_kwh']]
                                # Legacy labels begin one interval earlier. Never merely relabel them.
                                if len(old_hist) != n * 7 or not close(history[:-1], old_hist[1:]):
                                    reasons.append('legacy_history_disagrees_with_raw')
                            else:
                                subset = target
                                if not close(history, [v for h in r['input']['history'] for v in h['energy_kwh']]):
                                    reasons.append('legacy_history_disagrees_with_raw')
                            if not close(subset, r['target']['energy_kwh']):
                                reasons.append('legacy_event_target_disagrees_with_raw')
                    ids = sorted(r['sample_id'] for r in rows)
                    if reasons:
                        exclusions.append({'source': source, 'household_id': household, 'date': day,
                                           'source_sample_ids': ids, 'reasons': sorted(set(reasons))})
                        continue
                    p = rows[0]['input']['profile']
                    measurement = (rows[0]['target']['measurement_scope'] if source == 'sgsc'
                                   else 'reported_household_demand_no_reported_pv_business_or_shared_rental_meter')
                    context = {'forecast_origin': start.isoformat(),
                               'target_window': {'start': start.isoformat(), 'end': end.isoformat(),
                                                 'horizon_hours': 24, 'interval_minutes': step},
                               'country': 'AU' if source == 'sgsc' else 'NO',
                               'region': p.get('region'),
                               'time_basis': 'source_clock_intervals_no_utc_conversion',
                               'measurement_scope': measurement, 'events': events(rows, start, step)}
                    record = {'source': source, 'household_id': household, 'date': day,
                              'history': {'start': hist_start.isoformat(), 'end': start.isoformat(),
                                          'interval_minutes': step, 'unit': 'kWh', 'energy_kwh': history},
                              'context': context, 'output': {'energy_kwh': target},
                              'source_sample_ids': ids, 'raw_curve_sha256': digest}
                    output.write((json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode())
                    counts[source] += 1
                if (idx + 1) % 250 == 0:
                    print(source, idx + 1, 'households read;', dict(counts), 'days kept', flush=True)
    temp.replace(destination)
    report = {'counts': dict(counts), 'exclusions': exclusions, 'source_files': receipts,
              'cache_sha256': sha(destination), 'no_imputation': True, 'legacy_subwindow_and_history_compared': True}
    destination.with_suffix('.report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'counts': dict(counts), 'excluded_days': len(exclusions)}, ensure_ascii=False), flush=True)


def close(a, b):
    return len(a) == len(b) and all(math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-9) for x, y in zip(a, b))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/baseline_windows.jsonl.gz')
    args = parser.parse_args()
    extract(args.pipeline_root, args.output)
