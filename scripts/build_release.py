"""Package existing local observations; never rebuild targets or train models.

Usage: python3 scripts/build_release.py --pipeline-root /path/to/load_response_pipeline
The local cleaning workspace is required only for rebuilding this export.
"""
import argparse
import copy
import csv
import gzip
import hashlib
import io
import json
import shutil
from collections import Counter
from pathlib import Path
from read_data import ROOT, read_records, export_summary

BATCHES = {
    'sgsc_single': 'sgsc_all_response_verified_v1',
    'sgsc_two_meter': 'sgsc_two_meter_sum_v1',
    'iflex': 'iflex_all_candidates_v1',
}
EXPECTED = {'sgsc_single': (7939, 1149), 'sgsc_two_meter': (8403, 929), 'iflex': (2071, 314)}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def project(r, branch, batch, line, evidence):
    scope = r['target'].get('measurement_scope',
        'reported_household_demand_no_reported_pv_business_or_shared_rental_meter')
    provenance = r['provenance']
    result = {
        'schema_version': 'energybridge-observation-share/1',
        **{k: r[k] for k in ['source', 'sample_id', 'household_id', 'event_id',
                             'input', 'target', 'estimated_reference']},
        'metadata': {
            'branch': branch, 'source_schema_version': r['schema_version'],
            'source_batch': batch, 'source_line_number': line,
            'measurement_scope': scope,
            'condition_evidence_group': evidence.get('new_evidence_group', 'iflex_existing_candidate'),
            'source_readiness': r['readiness'],
            'phase': provenance.get('phase'), 'group': provenance.get('group'),
            'signal_id': provenance.get('signal_id'),
            'formal_training_release': False,
        },
    }
    result['input'] = copy.deepcopy(r['input'])
    for day in result['input']['history']:
        if 'energy_kwh' not in day:
            assert branch == 'sgsc_single'
            day['energy_kwh'] = list(day['channels_kwh']['GENERAL_SUPPLY_KWH'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-root', required=True, type=Path)
    args = parser.parse_args()
    base = args.pipeline_root
    selection = base/'evidence/20260907_sgsc_condition_reaudit/sample_evidence_groups.jsonl'
    groups = {r['sample_id']:r for r in map(json.loads,selection.open())}
    manifest = {'snapshot_date': '2026-09-07', 'schema_version': 'energybridge-observation-share/1',
                'selection_sha256': sha(selection), 'branches': {},
                'scope': 'candidate observations in existing source windows; not a full-day SFT release'}
    excluded, all_ids, household_sets = [], set(), {}
    for branch, batch in BATCHES.items():
        src = base/'runs'/batch/'observations.jsonl'
        dest = ROOT/'data'/f'{branch}.jsonl.gz'
        dest.parent.mkdir(parents=True, exist_ok=True)
        n, homes, evidence_counts, windows = 0, set(), Counter(), Counter()
        with dest.open('wb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as gz:
                with io.TextIOWrapper(gz, encoding='utf-8') as out:
                    for line, r in enumerate(map(json.loads,src.open()), 1):
                        g = groups[r['sample_id']] if r['source']=='sgsc' else {}
                        if g.get('new_evidence_group') == 'unresolved_conflict_or_missing_boundary':
                            excluded.append({'sample_id':r['sample_id'], 'household_id':r['household_id'],
                                'branch':branch, 'reason':g['unresolved_reason_exclusive']})
                            continue
                        assert r['sample_id'] not in all_ids
                        all_ids.add(r['sample_id'])
                        row = project(r,branch,batch,line,g)
                        out.write(json.dumps(row,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
                        if n==0:
                            write_json(ROOT/'examples'/f'{branch}_observation.json',row)
                        n+=1;homes.add(r['household_id'])
                        evidence_counts[row['metadata']['condition_evidence_group']]+=1
                        windows[len(r['target']['energy_kwh'])*(0.5 if r['source']=='sgsc' else 1)]+=1
        assert (n,len(homes))==EXPECTED[branch], (branch,n,len(homes))
        household_sets[branch]=homes
        manifest['branches'][branch]={'records':n,'households':len(homes),'source_batch':batch,
            'source_file_sha256':sha(src),'file':f'data/{branch}.jsonl.gz','sha256':sha(dest),
            'bytes':dest.stat().st_size,'evidence_groups':dict(evidence_counts),'window_hours_counts':dict(windows)}
    assert len(excluded)==258
    assert not household_sets['sgsc_single'] & household_sets['sgsc_two_meter']
    assert len(all_ids)==18413
    # One SGSC file for analysis; the meter configuration remains row metadata.
    sgsc_path = ROOT/'data'/'sgsc.jsonl.gz'
    with sgsc_path.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz:
            for branch in ('sgsc_single','sgsc_two_meter'):
                with gzip.open(ROOT/'data'/f'{branch}.jsonl.gz','rb') as f:
                    shutil.copyfileobj(f,gz)
    manifest['data_files']={}
    for source in ('sgsc','iflex'):
        path=ROOT/'data'/f'{source}.jsonl.gz'
        manifest['data_files'][source]={'file':f'data/{source}.jsonl.gz','sha256':sha(path),
            'bytes':path.stat().st_size,'records':16342 if source=='sgsc' else 2071,
            'households':2078 if source=='sgsc' else 314}
        export_summary(read_records(source),ROOT/'tables'/f'{source}_events.csv')
    for branch in ('sgsc_single','sgsc_two_meter'):
        (ROOT/'data'/f'{branch}.jsonl.gz').unlink()
        (ROOT/'tables'/f'{branch}_events.csv').unlink(missing_ok=True)
        for key in ('file','sha256','bytes'):
            manifest['branches'][branch].pop(key)
    with (ROOT/'tables'/'sgsc_exclusions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(excluded[0]));w.writeheader();w.writerows(excluded)
    for source in ['sgsc','iflex']:
        shutil.copyfile(base/'reports/notion_day_audit_20260907'/f'{source}_day_example.json',
                        ROOT/'examples'/f'{source}_full_day_example.json')
    manifest['excluded_sgsc_records']=len(excluded)
    manifest['total_candidate_records']=len(all_ids)
    write_json(ROOT/'provenance'/'manifest.json',manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
