"""Score complete native-resolution predictions on the fixed retrospective benchmark."""
import argparse
import gzip
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from benchmark_io import ROOT, VARIANTS, read_samples


def hourly(values, step):
    n=60//step
    return [sum(values[i:i+n]) for i in range(0,len(values),n)]


def metrics(sample, prediction):
    target=sample['output']['energy_kwh']
    if not isinstance(prediction,list) or len(prediction)!=len(target): raise ValueError('Wrong prediction length/type')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in prediction): raise ValueError('Invalid prediction value')
    step=sample['input']['context']['target_window']['interval_minutes']
    # Hourly interval kWh / 1 hour equals hourly average kW.
    y,p=hourly(target,step),hourly(prediction,step)
    errors=[a-b for a,b in zip(p,y)]
    event_errors=[]
    start=datetime.fromisoformat(sample['input']['context']['target_window']['start'])
    for e in sample['input']['context']['events']:
        lo=(datetime.fromisoformat(e['start'])-start).total_seconds()/(step*60)
        hi=(datetime.fromisoformat(e['end'])-start).total_seconds()/(step*60)
        if not lo.is_integer() or not hi.is_integer():raise ValueError('Event off native grid')
        lo,hi=int(lo),int(hi)
        event_errors.append(abs(sum(prediction[lo:hi])-sum(target[lo:hi])))
    return {'hourly_mae_kw':sum(abs(e) for e in errors)/24,
            'hourly_rmse_kw':math.sqrt(sum(e*e for e in errors)/24),
            'daily_energy_absolute_error_kwh':abs(sum(prediction)-sum(target)),
            'hourly_peak_absolute_error_kw':abs(max(p)-max(y)),
            'event_energy_absolute_error_kwh':sum(event_errors)/len(event_errors)}


def macro(rows):
    households=defaultdict(list)
    for hh,m in rows:households[hh].append(m)
    names=next(iter(households.values()))[0].keys()
    return {'samples':len(rows),'households':len(households),
            'metrics':{k:sum(sum(m[k] for m in ms)/len(ms) for ms in households.values())/len(households) for k in names}}


def evaluate(root, predictions, split, variant, sources=('sgsc','iflex')):
    opener=gzip.open if str(predictions).endswith('.gz') else open
    pred={}
    with opener(predictions,'rt') as f:
        for line in f:
            r=json.loads(line)
            if set(r)!={'sample_id','energy_kwh'}:raise ValueError('Prediction row requires exactly sample_id and energy_kwh')
            if r['sample_id'] in pred:raise ValueError('Duplicate prediction ID')
            pred[r['sample_id']]=r['energy_kwh']
    expected={r['sample_id']:r for s in sources for r in read_samples(s,split,root)}
    if not expected:raise ValueError('Empty evaluation set')
    if set(expected)!=set(pred):raise ValueError('Missing or extra prediction IDs')
    groups=defaultdict(list)
    for sid,r in expected.items():
        m=metrics(r,pred[sid]);source=r['metadata']['source'];hh=r['metadata']['profile_id']
        groups[source].append((hh,m))
        for etype in {e['type'] for e in r['input']['context']['events']}:
            groups[source+'/'+etype].append((hh,m))
    reports={s:macro(rows) for s,rows in sorted(groups.items())}
    return {'track':'retrospective_conditional','split':split,'input_variant_declared':variant,
            'input_variant_verified_from_predictions':False,
            'groups':reports,
            'equal_source_metrics':{k:sum(reports[s]['metrics'][k] for s in sources)/len(sources) for k in reports[sources[0]]['metrics']},
            'strict_prospective_claim_supported':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT/'benchmark/v1')
    p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--split',choices=['validation','test'],required=True)
    p.add_argument('--variant',choices=VARIANTS,required=True)
    p.add_argument('--source',choices=['sgsc','iflex','both'],default='both')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    r=evaluate(a.root,a.predictions,a.split,a.variant,('sgsc','iflex') if a.source=='both' else (a.source,))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    print(json.dumps(r,indent=2))
