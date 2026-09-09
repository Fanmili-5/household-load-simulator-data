"""Verify all released windows against selected cumulative source readings and profiles."""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from build_lirneasia_extension import DEFAULT, digest, read_jsonl, source_profiles, split_households, VERSION, write_json


def verify(root=DEFAULT, source=None):
    root = Path(root)
    source = Path(source) if source else DEFAULT / 'sources'
    m = json.loads((root/'manifest.json').read_text())
    if digest(source/'manifest.json') != m['source_manifest_sha256']:
        raise ValueError('Source manifest mismatch')
    for name, expected in m['artifacts'].items():
        if digest(root/name) != expected:
            raise ValueError('Artifact hash mismatch: '+name)
    profiles = source_profiles(source)
    raw = defaultdict(dict)
    expected_ids = set()
    run_count = 0
    for r in read_jsonl(source/'cumulative_runs.jsonl.gz'):
        run_count += 1
        hid = r['household_id']; start = datetime.fromisoformat(r['start'])
        for i, (a,b,e,f) in enumerate(zip(r['import_register_kwh'],r['import_register_kwh'][1:],r['export_register_kwh'],r['export_register_kwh'][1:])):
            t = start + timedelta(minutes=15*i)
            if t in raw[hid] or not all(math.isfinite(v) for v in (a,b,e,f)) or b<a or e!=f:
                raise ValueError('Invalid source endpoints')
            raw[hid][t] = b-a
        expected_ids.update('lirneasia:'+hid+':'+(start+timedelta(days=i+7)).date().isoformat() for i in range(r['days']-7))
    with (root/'splits/household_holdout.csv').open() as f:
        rows = list(csv.DictReader(f))
    split_rows = {r['sample_id']: r for r in rows}
    if len(split_rows) != len(rows):
        raise ValueError('Duplicate split index')
    assignments = split_households(profiles)
    observed = set(); split_counts=Counter(); household_splits=defaultdict(set)
    retained_households=set(); quarantine_count=0
    def no_identity(obj):
        if isinstance(obj,dict):
            if any(k.endswith('_ID') or k in ('household_id','sample_id','metadata','output','profile_as_of') for k in obj):
                raise ValueError('Tracking/answer field in semantic input')
            for v in obj.values():no_identity(v)
        elif isinstance(obj,list):
            for v in obj:no_identity(v)
    from itertools import chain
    records=chain(((r,False) for r in read_jsonl(root/'data/lirneasia.jsonl.gz')), ((r,True) for r in read_jsonl(root/'quarantine/lirneasia.jsonl.gz')))
    for s, quarantined in records:
        sid=s['sample_id'];meta=s['metadata'];hid=meta['household_id'];p=profiles[hid]
        if sid in observed or s['schema_version']!=VERSION:raise ValueError('Identity/version mismatch')
        observed.add(sid);no_identity(s['input'])
        if s['input']['profile']!={k:v for k,v in p.items() if k!='as_of'}:raise ValueError('Profile mismatch')
        h=s['input']['history'];c=s['input']['context'];tw=c['target_window']
        start=datetime.fromisoformat(h['start']);origin=datetime.fromisoformat(c['forecast_origin'])
        if h['end']!=tw['start'] or h['end']!=c['forecast_origin'] or origin-start!=timedelta(days=7):raise ValueError('History leakage/boundary')
        if datetime.fromisoformat(tw['end'])-origin!=timedelta(days=1) or origin.time()!=datetime.min.time():raise ValueError('Target boundary')
        if h['interval_minutes']!=15 or tw['interval_minutes']!=15 or len(h['energy_kwh'])!=672 or len(s['output']['energy_kwh'])!=96:raise ValueError('Resolution/length')
        if meta['profile_as_of']!=p['as_of'] or datetime.fromisoformat(p['as_of']).date()>=start.date():raise ValueError('Survey time leakage')
        values=h['energy_kwh']+s['output']['energy_kwh']
        for i,v in enumerate(values):
            if type(v) not in (int,float) or not math.isfinite(v) or v<0 or v!=raw[hid][start+timedelta(minutes=15*i)]:raise ValueError('Source value/continuity mismatch')
        longest=0;current=0
        for v in values:
            current=current+1 if v==0 else 0;longest=max(longest,current)
        if quarantined!=(longest>=96):raise ValueError('Wrong quarantine classification')
        status='quarantined_continuous_zero' if quarantined else 'retained'
        expected={'sample_id':sid,'household_id':hid,'split':assignments[hid],'status':status}
        if split_rows.get(sid)!=expected or meta['split']!=assignments[hid]:raise ValueError('Split mismatch')
        household_splits[hid].add(meta['split'])
        if quarantined:quarantine_count+=1
        else:
            retained_households.add(hid);split_counts[meta['split']]+=1
    if observed!=expected_ids or observed!=set(split_rows):raise ValueError('Missing/extra windows')
    if any(len(v)!=1 for v in household_splits.values()):raise ValueError('Household leakage')
    counts={'runs':run_count,'unique_intervals':sum(map(len,raw.values())),'samples':len(observed)-quarantine_count,'quarantined_samples':quarantine_count,'qualified_windows':len(observed),'source_households':len(household_splits),'households':len(retained_households)}
    if counts!=m['counts'] or dict(split_counts)!=m['split_samples']:raise ValueError('Count mismatch')
    return {'passed':True,'version':VERSION,'counts':counts,'split_samples':dict(split_counts),
            'checks':['source/artifact hashes','all 6660 histories and targets versus cumulative readings','complete native windows','all survey dates precede history','all same-household profiles','fixed household-disjoint split','no identity or answers in input','independent continuous-zero quarantine; all original windows preserved'],
            'model_training_executed':False,'scope':'construction integrity, not model accuracy or causal validity'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=DEFAULT)
    p.add_argument('--source-dir',type=Path,default=DEFAULT/'sources')
    p.add_argument('--output',type=Path)
    a=p.parse_args();r=verify(a.root,a.source_dir)
    if a.output:write_json(a.output,r)
    print(json.dumps(r,indent=2))
