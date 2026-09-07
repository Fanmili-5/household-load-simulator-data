"""Check corrected semantics, unchanged observed curves, quarantine and frozen membership."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path
from build_baseline import read, dump, leaves
from baseline_contract import validate
from baseline_windows import ROOT, sha
from verify_baseline import check_semantics
from benchmark_profile import VERSION
from benchmark_io import VARIANTS, model_input, render


def verify(root, reference_schema=False):
    m=json.loads((root/'manifest.json').read_text())
    assert m['schema_version']==VERSION
    for name,info in m['artifacts'].items():
        assert sha(root/name)==info['sha256'] and (root/name).stat().st_size==info['bytes'],name
    for name,digest in m['implementation_files'].items():assert sha(ROOT/'scripts'/name)==digest,name
    base=ROOT/'baseline/v1'
    assert sha(base/'manifest.json')==m['parent_manifest_sha256']
    for name,digest in m['source_evidence_sha256'].items():assert sha(ROOT/'benchmark/source_evidence_v1'/name)==digest
    schemas={s:json.loads((root/'schema'/(s+'.schema.json')).read_text()) for s in ('profile','sample')}
    validators={}
    if reference_schema:
        from jsonschema import Draft202012Validator
        for k,s in schemas.items():Draft202012Validator.check_schema(s);validators[k]=Draft202012Validator(s)
    with (base/'splits/household_holdout.csv').open() as f:old_split={r['sample_id']:r for r in csv.DictReader(f)}
    with (root/'splits/household_holdout.csv').open() as f:split={r['sample_id']:r for r in csv.DictReader(f)}
    with (root/'quarantine/index.csv').open() as f:qindex={r['sample_id']:r for r in csv.DictReader(f)}
    assert set(split).isdisjoint(qindex) and set(split)|set(qindex)==set(old_split)
    for sid,r in split.items():assert r==old_split[sid]
    homes=defaultdict(set);counts=Counter();seen=set();corrected=0;corrected_samples=0;coverage=defaultdict(Counter)
    for source in ('sgsc','iflex'):
        profiles={r['profile_id']:r for r in read(root/'profiles'/(source+'.jsonl.gz'))}
        old_profiles={r['profile_id']:r for r in read(base/'profiles'/(source+'.jsonl.gz'))}
        assert set(profiles)==set(old_profiles)
        for key,r in profiles.items():
            validate(r['profile'],schemas['profile'])
            if validators:validators['profile'].validate(r['profile'])
            old=old_profiles[key]
            assert r['metadata']['source_profile_provenance']==old['metadata']['source_profile_provenance']
            raw=r['metadata']['source_profile_provenance']['raw_answers'];p=r['profile']
            if source=='iflex' and raw['q16_bil']=='No':
                assert p['household']['car_present'] is False and p['household']['car_count']==0
                ev=next(d for d in p['appliances'] if d['type']=='electric_or_plugin_hybrid_vehicle')
                assert ev['present'] is False and ev['count']==0 and p['vehicle_details']==[]
                # Restore just the authorized semantic changes; all other profile content must match.
                import copy
                reverted=copy.deepcopy(p)
                reverted['household']['car_count']=old['profile']['household']['car_count']
                reverted['vehicle_details']=old['profile']['vehicle_details']
                reverted['appliances']=old['profile']['appliances']
                assert reverted==old['profile']
                assert [d for d in p['appliances'] if d['type']!='electric_or_plugin_hybrid_vehicle']==[d for d in old['profile']['appliances'] if d['type']!='electric_or_plugin_hybrid_vehicle']
                corrected+=1
            else:assert p==old['profile']
            for path,value in leaves(p):coverage[source,path]['unknown' if value is None else 'known']+=1
        originals={r['sample_id']:r for r in read(base/'data'/(source+'.jsonl.gz'))}
        for folder in ('data','quarantine'):
            for r in read(root/folder/(source+'.jsonl.gz')):
                sid=r['sample_id'];assert sid not in seen;seen.add(sid)
                old=originals[sid]
                validate(r,schemas['sample'])
                if validators:validators['sample'].validate(r)
                check_semantics(r)
                for key in ('history','context'):assert r['input'][key]==old['input'][key]
                assert r['output']==old['output']
                assert r['metadata']['source_sample_ids']==old['metadata']['source_sample_ids']
                assert r['input']['profile']==profiles[r['metadata']['profile_id']]['profile']
                values=r['input']['history']['energy_kwh']+r['output']['energy_kwh']
                longest=max((sum(1 for _ in g) for zero,g in groupby(v==0 for v in values) if zero),default=0)
                reject=longest*r['input']['history']['interval_minutes']>=1440
                assert reject==(folder=='quarantine')
                assert r['metadata']['quality']['longest_zero_minutes']==longest*r['input']['history']['interval_minutes']
                assert r['metadata']['eligibility']['retrospective_conditional']==(not reject)
                assert not r['metadata']['eligibility']['strict_prospective']
                assert r['metadata']['availability']['event_notice_protocol_is_receipt_evidence'] is False
                assert (sid in qindex)==reject
                if not reject:
                    homes[source].add(r['metadata']['profile_id'])
                    if profiles[r['metadata']['profile_id']]['metadata']['benchmark_corrections']:corrected_samples+=1
                for variant in VARIANTS:
                    x=render(r,variant);assert json.loads(x['messages'][1]['content'])==model_input(r,variant)
                    assert json.loads(x['messages'][2]['content'])==r['output']
                counts[source+'/'+folder]+=1
    assert seen==set(old_split)
    assert {s:counts[s+'/data'] for s in ('sgsc','iflex')}==m['counts']
    assert {s:counts[s+'/quarantine'] for s in ('sgsc','iflex')}==m['quarantined_counts']
    assert {s:len(h) for s,h in homes.items()}==m['households_with_retained_days']
    with (root/'provenance/profile_field_coverage.csv').open() as f:
        cr=list(csv.DictReader(f))
    assert len(cr)==len(coverage)
    for r in cr:
        c=coverage[r['source'],r['field']]
        assert int(r['known'])==c['known'] and int(r['unknown'])==c['unknown']
    assert corrected==m['corrected_profiles']==22 and corrected_samples==149
    report={'passed':True,'schema_version':VERSION,'counts':dict(counts),'corrected_profiles':corrected,
            'corrected_retained_samples':corrected_samples,'reference_json_schema':reference_schema,
            'checks':['artifact integrity','all observed histories, contexts and targets unchanged','only explicit no-car branches corrected',
                      'independent continuous-zero screening','retained plus quarantine equals parent membership',
                      'household split preserved','coverage recomputed','all five input variants round-trip',
                      'prospective gate closed; protocol does not imply receipt'], 'training_executed':False}
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT/'benchmark/v1')
    p.add_argument('--reference-json-schema',action='store_true')
    p.add_argument('--write-report',action='store_true')
    a=p.parse_args();r=verify(a.root,a.reference_json_schema)
    if a.write_report:dump(a.root/'validation.json',r)
