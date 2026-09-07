"""Build benchmark 1.0 from immutable observed data, without rewriting its release."""
import argparse
import copy
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from contextlib import ExitStack
from build_baseline import read, writer, dump, csv_write, leaves
from baseline_windows import ROOT, sha
from benchmark_profile import correct_profile, VERSION
from benchmark_quality import quality

BASE = ROOT / 'baseline/v1'
EVIDENCE = ROOT / 'benchmark/source_evidence_v1'


def build(out):
    assert not (out / 'manifest.json').exists(), 'Use a new output directory to avoid stale artifacts'
    # Input integrity is checked before any source data is used.
    previous = json.loads((BASE / 'manifest.json').read_text())
    for name, info in previous['artifacts'].items(): assert sha(BASE / name) == info['sha256']
    profiles, corrections, coverage = {}, [], defaultdict(Counter)
    for source in ('sgsc', 'iflex'):
        with writer(out / 'profiles' / (source + '.jsonl.gz')) as write:
            for original in read(BASE / 'profiles' / (source + '.jsonl.gz')):
                r = correct_profile(original)
                profiles[r['profile_id']] = r
                write(r)
                for path, value in leaves(r['profile']): coverage[source, path]['unknown' if value is None else 'known'] += 1
                if r['metadata']['benchmark_corrections']:
                    corrections.append({'profile_id': r['profile_id'], 'fields': r['metadata']['benchmark_corrections'],
                                        'basis': 'q16_bil=No and no conflicting vehicle-branch answers'})
    with (BASE / 'splits/household_holdout.csv').open() as f:
        old_split = {r['sample_id']: r for r in csv.DictReader(f)}
    count, quarantine, flag_counts = Counter(), Counter(), Counter()
    homes, dates, split_rows, quarantine_rows, quality_rows = defaultdict(set), defaultdict(set), [], [], []
    strata, examples = Counter(), {}
    preferred_examples = {s: json.loads((BASE / 'examples' / (s+'.json')).read_text())['sample_id'] for s in ('sgsc','iflex')}
    for source in ('sgsc', 'iflex'):
        with writer(out / 'data' / (source + '.jsonl.gz')) as write, writer(out / 'quarantine' / (source + '.jsonl.gz')) as reject:
            for original in read(BASE / 'data' / (source + '.jsonl.gz')):
                r = copy.deepcopy(original)
                r['schema_version'] = VERSION
                r['input']['profile'] = profiles[r['metadata']['profile_id']]['profile']
                q = quality(r['input']['history']['energy_kwh'], r['output']['energy_kwh'], r['input']['history']['interval_minutes'])
                flag_counts.update(q['flags'])
                if q['flags']: quality_rows.append({'sample_id': r['sample_id'], **q})
                r['metadata']['quality'] = q
                availability = r['metadata']['availability']
                availability['profile_protocol'] = 'survey1_before_participation' if source == 'iflex' else 'not_established'
                availability['event_notice_protocol'] = 'previous_day_15_00' if source == 'iflex' else '24_hours_before_event'
                availability['event_notice_protocol_is_receipt_evidence'] = False
                r['metadata']['eligibility'] = {
                    'retrospective_conditional': q['disposition'] == 'retain',
                    'strict_prospective': False,
                    'numeric_incentive_analysis': source == 'iflex' and q['disposition'] == 'retain'}
                r['metadata']['condition_limits'] = ['sgsc_daytime_home_and_event_type_fully_confounded', 'household_numeric_rate_unverified'] if source == 'sgsc' else ['experimental_signal_not_retail_tariff']
                if q['disposition'] == 'quarantine':
                    reject(r)
                    quarantine[source] += 1
                    quarantine_rows.append({**old_split[r['sample_id']], 'reason': 'continuous_zero_at_least_24_hours'})
                    continue
                write(r)
                count[source] += 1
                homes[source].add(r['metadata']['profile_id'])
                dates[source].add(r['input']['context']['target_window']['start'][:10])
                split_rows.append(old_split[r['sample_id']])
                home = next(h['value'] for h in r['input']['profile']['usage_habits'] if h['behavior'] == 'someone_home')
                for e in r['input']['context']['events']: strata[source, e['type'], str(home)] += 1
                if source not in examples or r['sample_id'] == preferred_examples[source]: examples[source] = r
    csv_write(out / 'splits/household_holdout.csv', split_rows, ['sample_id','profile_id','source','split'])
    csv_write(out / 'quarantine/index.csv', quarantine_rows, ['sample_id','profile_id','source','split','reason'])
    csv_write(out / 'provenance/profile_field_coverage.csv',
              [{'source': s, 'field': p, 'known': c['known'], 'unknown': c['unknown'], 'applicable_rows': sum(c.values())}
               for (s, p), c in sorted(coverage.items())], ['source','field','known','unknown','applicable_rows'])
    for name in ('profile.schema.json','sample.schema.json','appliance_catalog.json','category_values.json'):
        obj = json.loads((BASE / 'schema' / name).read_text())
        obj = json.loads(json.dumps(obj).replace('household-baseline/1.0.0', VERSION))
        dump(out / 'schema' / name, obj)
    with (BASE / 'provenance/source_field_mapping.csv').open() as f: mappings = list(csv.DictReader(f))
    for r in mappings:
        if r['source'] == 'iflex' and r['source_field'] == 'q16_bil':
            r['destinations'] = json.dumps(sorted(set(json.loads(r['destinations'])) | {'household.car_count', 'appliances.electric_or_plugin_hybrid_vehicle', 'vehicle_details'}))
            r['reason'] += ' Explicit no-car answer plus empty branch yields zero cars and EVs; original answers preserved.'
    csv_write(out / 'provenance/source_field_mapping.csv', mappings, list(mappings[0]))
    dump(out / 'provenance/profile_corrections.json', corrections)
    dump(out / 'provenance/quality_flags.json', quality_rows)
    dump(out / 'provenance/input_evidence.json', json.loads((EVIDENCE / 'input_evidence.json').read_text()))
    dump(out / 'provenance/zero_review.json', json.loads((EVIDENCE / 'zero_review.json').read_text()))
    dump(out / 'provenance/event_home_cross_table.json', [
        {'source': s, 'event_type': e, 'daytime_home': h, 'samples': n} for (s,e,h),n in sorted(strata.items())])
    for source,r in examples.items(): dump(out / 'examples' / (source+'.json'),r)
    dump(out / 'evaluation/protocol.json', {
        'version': VERSION, 'task': 'retrospective_conditional_household_day_prediction',
        'horizon': 'seven preceding source-clock days to one full source-clock day',
        'split': 'preserve baseline-v1 household assignments; remove quarantined rows without rerandomization',
        'generalization': 'unseen households; dates overlap; not unseen-event or cross-country transfer',
        'eligible_track': 'retrospective_conditional', 'strict_prospective_eligible_rows': 0,
        'quality_rule': 'quarantine continuous exact-zero runs >=24h anywhere in 8-day window; near-zero daily sum in (0,0.01] kWh is flagged only',
        'selection_limit': 'Target-dependent screening conditions evaluation on screened windows; not a deployment-time filter or population estimate. Quarantine is retained for future adjudication.',
        'input_variants': ['history_only','history_profile','history_context','full','full_without_daytime_home'],
        'variant_rule': 'Use identical membership, splits, tokenizer and training budget across variants; history_only retains target clock and measurement scope for interpretation',
        'primary_metric': 'hourly_mae_kw',
        'secondary_metrics': ['hourly_rmse_kw','daily_energy_absolute_error_kwh','hourly_peak_absolute_error_kw','event_energy_absolute_error_kwh'],
        'resolution': 'SGSC adjacent half-hour kWh values are summed for scoring at 1h; iFlex unchanged. Raw training targets retain native resolution.',
        'aggregation': 'within-household mean of sample metrics, then equal-household mean within each source; pooled summary is equal-source mean',
        'stratification': ['source','source_and_event_type'],
        'invalid_predictions': 'reject run on duplicate/missing/extra IDs, wrong lengths, booleans, nonnumeric, nonfinite or negative values; never drop failed rows',
        'tuning': 'fit preprocessing and model on train only; choose settings on validation; freeze before test; report model/version/input variant/seeds',
        'claim_limits': ['no causal effect from observed load alone','no observed consent labels','SGSC daytime-home effect is not identifiable separately from event type', 'numeric incentive analysis limited to source-grounded iFlex signals'],
        'model_training_executed': False})
    manifest = {'schema_version': VERSION, 'status': 'retrospective_benchmark_data_and_evaluator',
                'counts': dict(count), 'quarantined_counts': {s: quarantine[s] for s in ('sgsc','iflex')},
                'households_with_retained_days': {s:len(h) for s,h in homes.items()},
                'profile_counts': dict(Counter(r['source'] for r in profiles.values())),
                'target_dates': {s:sorted(d) for s,d in dates.items()}, 'quality_flag_counts': dict(flag_counts),
                'corrected_profiles': len(corrections), 'strict_prospective_eligible_rows': 0,
                'parent_manifest_sha256': sha(BASE / 'manifest.json'),
                'source_evidence_sha256': {p.name: sha(p) for p in sorted(EVIDENCE.glob('*.json'))},
                'training_executed': False, 'imputation_performed': False,
                'implementation_files': {p.name:sha(p) for p in sorted((ROOT/'scripts').glob('*benchmark*.py'))},
                'artifacts': {str(p.relative_to(out)):{'sha256':sha(p),'bytes':p.stat().st_size}
                              for p in sorted(out.rglob('*')) if p.is_file()}}
    dump(out / 'manifest.json', manifest)
    print(json.dumps({k:manifest[k] for k in ('counts','quarantined_counts','households_with_retained_days','corrected_profiles')},indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'benchmark/v1')
    build(p.parse_args().output)
