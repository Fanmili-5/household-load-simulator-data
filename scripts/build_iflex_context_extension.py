"""Build optional past-weather inputs and a separate, post-trial review sidecar.

The default command rebuilds from the bundled source excerpts using only stdlib.
--hourly-csv and --survey-dir refresh those excerpts from verified source files.
Neither mode writes benchmark/v1 or exports follow-up answers as model inputs.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'extensions/iflex_context_v1'
STATIONS = {
    'Oslo': 'SN18700', 'Stavanger': 'SN44640', 'Bergen': 'SN50540',
    'Trondheim': 'SN68230', 'Bodø': 'SN82310', 'Tromsø': 'SN90450',
}
FIELDS = ['Aq1_' + str(i) for i in range(1, 11)]
CATEGORIES = dict(zip(FIELDS[1:], [
    'electric_car_purchase', 'space_heating_equipment_purchase',
    'shared_heating_or_district_heating_source_translation', 'water_based_heating',
    'reduced_building_heat_loss', 'solar_installation', 'resident_count_change',
    'home_in_february_due_to_coronavirus_self_report', 'other_unspecified',
]))
SOURCE_HASH = 'e3e857f0797aae1878492580fc68b3bca797989352ba1114b3908c13f2d77524'
SURVEY_MD5 = {'survey2_answers.csv': 'd25f3dfc6fd44faf8b189e5d72bd5b2b',
              'survey2_questions.csv': '7bad88234d50a86e7360c006cbca58b4'}


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':'),
                             allow_nan=False) + '\n' for r in rows).encode()
    if str(path).endswith('.gz'):
        with path.open('wb') as f:
            with gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as z:
                z.write(data)
    else:
        path.write_bytes(data)


def history_slots(sample):
    h = sample['input']['history']
    context = sample['input']['context']
    start, end = (datetime.fromisoformat(h[k]) for k in ('start', 'end'))
    origin = datetime.fromisoformat(context['forecast_origin'])
    if (h['interval_minutes'] != 60 or len(h['energy_kwh']) != 168
            or end - start != timedelta(days=7) or end != origin
            or context['target_window']['start'] != context['forecast_origin']):
        raise ValueError('Invalid history boundary: ' + sample['sample_id'])
    return [(start + timedelta(hours=i)).isoformat() for i in range(168)]


def classify_followup(row, dictionary):
    if row is None:
        return 'followup_unavailable', []
    selected = []
    for field in FIELDS[1:]:
        value = row[field]
        if value in ('-', 'NA'):
            continue
        if value not in dictionary[field]['answers']:
            raise ValueError('Unrecognized answer: ' + field + ': ' + value)
        selected.append(CATEGORIES[field])
    # Aq1_1 has an ambiguous "No" suffix in the dictionary. Use only explicit
    # detail answers to identify changes; never infer stability from its polarity.
    return ('reported_change_detail' if selected else 'no_change_details_recorded'), selected


def prepare_sources(samples, hourly_csv, survey_dir, source_dir):
    if digest(hourly_csv) != SOURCE_HASH:
        raise ValueError('Hourly CSV differs from the verified v1 extraction')
    for name, expected in SURVEY_MD5.items():
        if digest(survey_dir / name, 'md5') != expected:
            raise ValueError('Publisher checksum mismatch: ' + name)
    required, regions = {}, {}
    for s in samples:
        hh = s['metadata']['profile_id'].split(':', 1)[1]
        region = s['input']['context']['region']
        if hh in regions and regions[hh] != region:
            raise ValueError('Household region changed')
        regions[hh] = region
        for ts, demand in zip(history_slots(s), s['input']['history']['energy_kwh']):
            key = (hh, ts)
            if key in required and required[key] != demand:
                raise ValueError('Conflicting parent history')
            required[key] = demand
    seen, weather = set(), {}
    with hourly_csv.open(newline='') as f:
        for record, row in enumerate(csv.DictReader(f), 2):
            if row['ID'] not in regions or row['Participation_Phase'] != 'Phase_1':
                continue
            day = float(row['Date'])
            hour = float(row['Hour'])
            if not day.is_integer() or not hour.is_integer() or not 1 <= hour <= 24:
                raise ValueError('Invalid original Date/Hour')
            ts = (datetime(1970, 1, 1) + timedelta(days=day, hours=hour-1)).isoformat()
            key = (row['ID'], ts)
            if key not in required:
                continue
            if key in seen:
                raise ValueError('Duplicate household/hour')
            seen.add(key)
            demand, temperature, source_from = (float(row[k]) for k in
                                                ('Demand_kWh', 'Temperature', 'From'))
            if not all(map(math.isfinite, [demand, temperature, source_from])):
                raise ValueError('Non-finite source observation')
            if not math.isclose(demand, required[key], rel_tol=0, abs_tol=1e-9):
                raise ValueError('Source demand does not match parent history')
            region = regions[row['ID']]
            wk = (region, ts)
            value = {'region': region, 'timestamp': ts, 'temperature_c': temperature,
                     'source_from_numeric': source_from, 'source_csv_record': record}
            if wk in weather:
                if any(weather[wk][k] != value[k] for k in
                       ('temperature_c', 'source_from_numeric')):
                    raise ValueError('Conflicting regional weather')
            else:
                weather[wk] = value
    if seen != set(required):
        raise ValueError('Missing source history observations')
    dictionary = {}
    with (survey_dir / 'survey2_questions.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            field = row['Question_ID']
            if field in FIELDS:
                d = dictionary.setdefault(field, {'question': row['Question'], 'answers': []})
                if d['question'] != row['Question']:
                    raise ValueError('Conflicting question text')
                d['answers'].append(row['Answer'])
    answers, all_ids = [], set()
    with (survey_dir / 'survey2_answers.csv').open(newline='') as f:
        for record, row in enumerate(csv.DictReader(f), 2):
            if row['ID'] in all_ids:
                raise ValueError('Duplicate Survey 2 household')
            all_ids.add(row['ID'])
            if row['ID'] in regions:
                answers.append({'ID': row['ID'], 'source_csv_record': record,
                                **{k: row[k] for k in FIELDS}})
    write_jsonl(source_dir / 'regional_temperature.jsonl.gz',
                [weather[k] for k in sorted(weather)])
    write_jsonl(source_dir / 'survey2_change_answers.jsonl', sorted(answers, key=lambda r: r['ID']))
    write_json(source_dir / 'survey2_change_dictionary.json', dictionary)
    write_json(source_dir / 'extraction.json', {
        'dataset_doi': '10.5281/zenodo.8248802',
        'paper_doi': '10.1016/j.dib.2023.109571',
        'temperature_definition': 'Regional station air temperature 2 m above ground, degrees Celsius; paper Table 11',
        'station_mapping_evidence': 'Paper Table 7',
        'hourly_csv_sha256': digest(hourly_csv),
        'survey_files': {name: {'md5': digest(survey_dir / name, 'md5'),
                               'sha256': digest(survey_dir / name)} for name in SURVEY_MD5},
        'unique_household_hours_demand_checked': len(seen),
        'unique_region_hours': len(weather),
        'demand_alignment_tolerance_kwh': 1e-9,
        'temperature_imputation': False,
        'regional_values_checked_equal_across_matched_households': True,
    })


def build(samples, source_dir, out):
    weather = {}
    for r in read_jsonl(source_dir / 'regional_temperature.jsonl.gz'):
        key = (r['region'], r['timestamp'])
        if key in weather or not math.isfinite(r['temperature_c']):
            raise ValueError('Invalid bundled regional weather')
        weather[key] = r
    source_answers = read_jsonl(source_dir / 'survey2_change_answers.jsonl')
    answers = {r['ID']: r for r in source_answers}
    if len(answers) != len(source_answers):
        raise ValueError('Duplicate bundled follow-up ID')
    dictionary = json.loads((source_dir / 'survey2_change_dictionary.json').read_text())
    records, reviews = [], {}
    ids = set()
    for s in samples:
        if s['sample_id'] in ids:
            raise ValueError('Duplicate parent sample')
        ids.add(s['sample_id'])
        pid = s['metadata']['profile_id']
        hh = pid.split(':', 1)[1]
        context, history = s['input']['context'], s['input']['history']
        region = context['region']
        observed = [weather[(region, t)] for t in history_slots(s)]
        if any(b['source_from_numeric'] - a['source_from_numeric'] != 3600
               for a, b in zip(observed, observed[1:])):
            raise ValueError('Non-consecutive original measurement starts')
        records.append({'sample_id': s['sample_id'], 'history_weather': {
            'start': history['start'], 'end': history['end'], 'interval_minutes': 60,
            'time_basis': context['time_basis'], 'unit': 'degC',
            'measurement': 'regional_station_air_temperature_2m_above_ground',
            'region': region, 'station_id': STATIONS[region],
            'temperature_c': [r['temperature_c'] for r in observed],
        }})
        if pid not in reviews:
            status, categories = classify_followup(answers.get(hh), dictionary)
            reviews[pid] = {'profile_id': pid, 'use': 'retrospective_review_only',
                'eligible_as_model_input': False,
                'survey_collection_start': '2020-05-12', 'survey_collection_end': '2020-06-09',
                'question_reference_month': '2020-02', 'status': status,
                'reported_changes': categories, 'exact_change_date': None,
                'sample_ids_in_reference_month': [], 'sample_ids_after_reference_month': [],
                'source_record': answers[hh]['source_csv_record'] if hh in answers else None}
        date = context['target_window']['start'][:10]
        if not '2020-02-01' <= date < '2020-04-01':
            raise ValueError('Unexpected target date for February follow-up review')
        key = ('sample_ids_in_reference_month' if date.startswith('2020-02-')
               else 'sample_ids_after_reference_month')
        reviews[pid][key].append(s['sample_id'])
    write_jsonl(out / 'inputs/history_weather.jsonl.gz', records)
    write_jsonl(out / 'review/household_changes.jsonl', list(reviews.values()))
    write_json(out / 'example.json', records[0])
    changes = [r for r in reviews.values() if r['status'] == 'reported_change_detail']
    counts = {'samples_with_history_weather': len(records), 'households': len(reviews),
              'followup_status_households': dict(Counter(r['status'] for r in reviews.values())),
              'reported_change_household_samples_in_february': sum(len(r['sample_ids_in_reference_month']) for r in changes),
              'reported_change_household_samples_in_march': sum(len(r['sample_ids_after_reference_month']) for r in changes),
              'reported_change_categories_households': dict(Counter(c for r in changes for c in r['reported_changes']))}
    write_json(out / 'manifest.json', {
        'extension_version': 'iflex-context/1.0.0', 'parent_version': 'household-benchmark/1.0.0',
        'parent_iflex_data_sha256': digest(ROOT / 'benchmark/v1/data/iflex.jsonl.gz'),
        'parent_manifest_sha256': digest(ROOT / 'benchmark/v1/manifest.json'),
        'implementation_sha256': digest(Path(__file__)), 'counts': counts,
        'example_sha256': digest(out / 'example.json'),
        'target_day_actual_weather_in_inputs': False, 'followup_answers_in_inputs': False,
        'split_assignment': 'inherit parent household_holdout.csv; no resplitting',
        'weather_track': 'optional iFlex retrospective extension; report separately from v1 input variants',
        'prospective_weather_publication_latency_verified': False,
        'limits': ['No imputation; no new households or days.',
                   'Reported change is not proof a particular sample has a stale profile.',
                   'No change details and missing follow-up are not proof of stability.',
                   'February change dates and persistence into March are unknown.',
                   'Aq1_1 polarity is not used; explicit detail answers determine status.',
                   'Survey reports are not independently verified device events.',
                   'Historical regional weather does not establish a measured appliance trajectory.'],
        'artifacts': {str(p.relative_to(out)): digest(p) for folder in ['sources', 'inputs', 'review']
                      for p in sorted((out / folder).glob('*')) if p.is_file()},
    })
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--hourly-csv', type=Path)
    ap.add_argument('--survey-dir', type=Path)
    ap.add_argument('--output', type=Path, default=DEFAULT)
    ap.add_argument('--source-dir', type=Path, default=DEFAULT / 'sources')
    args = ap.parse_args()
    if bool(args.hourly_csv) != bool(args.survey_dir):
        ap.error('--hourly-csv and --survey-dir must be supplied together')
    if any(path.resolve().is_relative_to((ROOT / p).resolve())
           for path in [args.output, args.source_dir] for p in ['benchmark', 'baseline']):
        ap.error('Output/source directory cannot overwrite a parent dataset')
    samples = read_jsonl(ROOT / 'benchmark/v1/data/iflex.jsonl.gz')
    if args.hourly_csv:
        prepare_sources(samples, args.hourly_csv, args.survey_dir, args.source_dir)
    if args.output / 'sources' != args.source_dir:
        for p in args.source_dir.glob('*'):
            destination = args.output / 'sources' / p.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(p.read_bytes())
    print(json.dumps(build(samples, args.output / 'sources', args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
