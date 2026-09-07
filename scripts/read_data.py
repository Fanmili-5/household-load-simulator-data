"""Read the shared household observations with Python 3.10+ (standard library only)."""
import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCHES = ('sgsc', 'iflex')


def read_records(branch, root=ROOT):
    if branch not in BRANCHES:
        raise ValueError(f'Unknown branch: {branch}')
    with gzip.open(Path(root) / 'data' / f'{branch}.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def summary_row(r):
    """Flatten profile and observed outcomes; no inferred response/consent labels."""
    p, c, t = r['input']['profile'], r['input']['context'], r['target']
    h = p['household']
    sgsc = r['source'] == 'sgsc'
    start = c['start_local'] if sgsc else c['event_date'] + ' 00:00:00'
    from datetime import date, timedelta
    end = c['end_local'] if sgsc else str(date.fromisoformat(c['event_date']) + timedelta(days=1)) + ' 00:00:00'
    interval = 30 if sgsc else 60
    hours = len(t['energy_kwh']) * interval / 60
    ref = r['estimated_reference']
    ref_values = ref.get('energy_kwh') if ref else None
    total = sum(t['energy_kwh'])
    prices = c.get('experimental_price_NOK_per_kwh')
    row = {
        'source': r['source'], 'meter_configuration': r['metadata']['branch'],
        'sample_id': r['sample_id'], 'household_id': r['household_id'],
        'event_id': r['event_id'], 'event_date': start[:10],
        'target_start_source_clock': start, 'target_end_source_clock': end,
        'measurement_scope': r['metadata']['measurement_scope'],
        'interval_minutes': interval, 'window_hours': hours,
        'event_type': c.get('event_type', 'experimental_hourly_price'),
        'evidence_group': r['metadata']['condition_evidence_group'],
        'signal_id': r['metadata'].get('signal_id'),
        'group': r['metadata'].get('group'),
        'household_size': None if sgsc else int(h['q19'].split()[0]),
        'dwelling_type_raw': h.get('DWELLING_TYPE_CD') if sgsc else h.get('q4'),
        'asserted_dwelling_type_raw': h.get('ASSRTD_DWELLING_TYPE_CD'),
        'floor_area_band_raw': h.get('q5'), 'region': p.get('region'),
        'climate_zone': h.get('ASSRTD_CLIMATE_ZONE_DESC'),
        'daytime_home_raw': h.get('IS_HOME_DURING_DAYTIME') if sgsc else h.get('q23'),
        'heated_rooms_raw': h.get('NUM_ROOMS_HEATED'),
        'gas_heating_raw': h.get('HAS_GAS_HEATING'),
        'target_total_kwh': round(total, 9),
        'target_mean_kw': round(total / hours, 9),
        'target_max_interval_mean_kw': max(t['energy_kwh']) * 60 / interval,
        'existing_reference_total_kwh': sum(ref_values) if ref_values is not None else None,
        'delta_vs_existing_reference_kwh': total-sum(ref_values) if ref_values is not None else None,
        'reference_method': ref.get('method') if ref else None,
        'experimental_price_min_nok_per_kwh': min(prices) if prices else None,
        'experimental_price_max_nok_per_kwh': max(prices) if prices else None,
        'sgsc_incentive_rate': c.get('incentive_rate'),
    }
    for category in ('refrigerator', 'air_conditioner', 'clothes_dryer', 'pool_pump',
                     'panel_heater', 'electric_underfloor_heating', 'heat_pump',
                     'separate_electric_water_heater', 'electric_or_plugin_hybrid_car'):
        a = next((x for x in p['appliances'] if x['appliance'] == category), {})
        present = a.get('present')
        if a.get('count') is not None:
            present = a['count'] > 0
        row[category + '_present'] = present
        row[category + '_count'] = a.get('count')
        row[category + '_answer_raw'] = a.get('source_value', a.get('usage_level_raw', a.get('type_raw')))
    for group in ('people','dwelling','preferences','usage_habits','energy_attitudes','energy_systems','vehicles'):
        for key,value in p.get(group,{}).items():
            row['profile_'+group+'_'+key]=json.dumps(value,ensure_ascii=False,sort_keys=True) if isinstance(value,(dict,list)) else value
    row['profile_quality_flags']=json.dumps(r['metadata'].get('profile_provenance',{}).get('quality_flags',[]))
    return row


def export_summary(records, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = None
        for record in records:
            row = summary_row(record)
            if writer is None:
                writer = csv.DictWriter(stream, fieldnames=list(row), lineterminator="\n")
                writer.writeheader()
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=BRANCHES)
    parser.add_argument('--export-csv', type=Path)
    args = parser.parse_args()
    if args.export_csv:
        if not args.source:
            parser.error('--export-csv requires --source')
        export_summary(read_records(args.source), args.export_csv)
        print(args.export_csv)
        return
    for branch in ([args.source] if args.source else BRANCHES):
        households, windows = set(), Counter()
        count = 0
        for r in read_records(branch):
            count += 1
            households.add(r['household_id'])
            interval = 30 if r['source'] == 'sgsc' else 60
            windows[len(r['target']['energy_kwh']) * interval / 60] += 1
        print(json.dumps({'branch': branch, 'records': count, 'households': len(households),
                          'window_hours_counts': dict(windows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
