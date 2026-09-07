"""Verify the actual distributed files. Optional --pipeline-root checks every source value."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from read_data import ROOT, read_records, summary_row


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def same(a,b):
    assert len(a)==len(b)
    assert all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-9) for x,y in zip(a,b))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-root',type=Path)
    parser.add_argument('--write-report',action='store_true')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'provenance/manifest.json').read_text())
    report={'passed':False,'checks':[], 'records':{},'source_value_comparison':bool(args.pipeline_root)}
    seen=set()
    if args.pipeline_root:
        selection=args.pipeline_root/'evidence/20260907_sgsc_condition_reaudit/sample_evidence_groups.jsonl'
        assert sha(selection)==manifest['selection_sha256']
        groups={r['sample_id']:r for r in map(json.loads,selection.open())}
    for source,info in manifest['data_files'].items():
        path=ROOT/info['file']
        assert sha(path)==info['sha256']
        homes=set();count=0;by_branch=Counter();compare={}
        with (ROOT/'tables'/f'{source}_events.csv').open(encoding='utf-8-sig',newline='') as f:
            table=list(csv.DictReader(f))
        for r in read_records(source):
            assert r['sample_id'] not in seen
            seen.add(r['sample_id']);homes.add(r['household_id']);by_branch[r['metadata']['branch']]+=1
            assert r['source']==source
            assert r['metadata']['formal_training_release'] is False
            assert not any(x in json.dumps(r) for x in ('/Users/','/private/','gho_','github_pat_','sk-proj-'))
            target=r['target']['energy_kwh'];history=r['input']['history']
            assert len(history)==7
            assert all(len(d['energy_kwh'])==(48 if source=='sgsc' else 24) for d in history)
            values=target+[v for d in history for v in d['energy_kwh']]
            assert all(math.isfinite(v) and v>=0 for v in values)
            assert math.isclose(sum(target),r['target']['event_energy_kwh'],abs_tol=1e-6)
            if source=='sgsc':
                m=r['input']['profile']['meter_configuration']
                assert m['GENERAL_SUPPLY_CNT']=='1' and m['HAS_GENERATION']=='N'
                assert all(m[k]=='0' for k in ('GROSS_SOLAR_CNT','NET_SOLAR_CNT','OTHER_LOAD_CNT'))
                controlled=m['CONTROLLED_LOAD_CNT']=='1'
                for d in history+[r['target']]:
                    channels=d['channels_kwh']
                    expected=[g+c for g,c in zip(channels['GENERAL_SUPPLY_KWH'],channels['CONTROLLED_LOAD_KWH'])] if controlled else channels['GENERAL_SUPPLY_KWH']
                    same(d['energy_kwh'],expected)
            else:
                assert len(target)==24
                assert len(r['input']['context']['experimental_price_NOK_per_kwh'])==24
            row=summary_row(r)
            assert table[count]=={k:('' if v is None else str(v)) for k,v in row.items()}
            count+=1
            if args.pipeline_root:compare[r['sample_id']]=r
        assert len(table)==count==info['records']
        assert len(homes)==info['households']
        report['records'][source]={'records':count,'households':len(homes),'meter_configurations':dict(by_branch)}
        if args.pipeline_root:
            matched=0
            for branch,b in manifest['branches'].items():
                if (source=='sgsc') != branch.startswith('sgsc'):continue
                src=args.pipeline_root/'runs'/b['source_batch']/'observations.jsonl'
                assert sha(src)==b['source_file_sha256']
                for line,raw in enumerate(map(json.loads,src.open()),1):
                    if source=='sgsc' and groups[raw['sample_id']]['new_evidence_group']=='unresolved_conflict_or_missing_boundary':
                        assert raw['sample_id'] not in compare
                        continue
                    shared=compare.pop(raw['sample_id']);matched+=1
                    assert shared['metadata']['source_line_number']==line
                    for key in ('source','sample_id','household_id','event_id','target','estimated_reference'):
                        assert shared[key]==raw[key],(raw['sample_id'],key)
                    for key in ('profile','context'):
                        assert shared['input'][key]==raw['input'][key]
                    for h,s in zip(raw['input']['history'],shared['input']['history']):
                        for key,value in h.items():assert s[key]==value
                        assert s['energy_kwh']==h.get('energy_kwh',h.get('channels_kwh',{}).get('GENERAL_SUPPLY_KWH'))
            assert not compare and matched==count
    assert len(seen)==18413
    with (ROOT/'tables/sgsc_exclusions.csv').open(encoding='utf-8-sig',newline='') as f:
        exclusions=list(csv.DictReader(f))
    assert len(exclusions)==258
    assert not seen & {r['sample_id'] for r in exclusions}
    for source,n in [('sgsc',48),('iflex',24)]:
        r=json.loads((ROOT/'examples'/f'{source}_full_day_example.json').read_text())
        assert len(r['output']['energy_kwh'])==n
        assert r['input']['history']['end']==r['input']['context']['forecast_origin']
        assert len(r['input']['history']['energy_kwh'])==n*7
    report['checks']=['file hashes','candidate membership and household counts','no duplicate sample ids',
        'household meter totals for every target and history slot','history and target lengths',
        'finite nonnegative values','CSV equals distributed JSON','excluded rows absent',
        'full-day examples separate','no local paths or recognized credential prefixes in records']
    if args.pipeline_root:report['checks'].append('every exported source input, measured target and existing reference compared with original batch')
    report['passed']=True
    if args.write_report:
        (ROOT/'provenance/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
