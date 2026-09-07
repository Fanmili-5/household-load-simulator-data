"""Read and render screened benchmark records; never start model training."""
import argparse
import copy
import csv
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ('history_only','history_profile','history_context','full','full_without_daytime_home')


def read_samples(source, split=None, root=None):
    root = Path(root) if root else ROOT / 'benchmark/v1'
    if source not in ('sgsc','iflex'): raise ValueError(source)
    if split not in (None,'train','validation','test'): raise ValueError(split)
    with (root / 'splits/household_holdout.csv').open() as f:
        ids = {r['sample_id'] for r in csv.DictReader(f) if r['source']==source and (split is None or r['split']==split)}
    with gzip.open(root / 'data' / (source+'.jsonl.gz'),'rt') as f:
        for line in f:
            r=json.loads(line)
            if r['sample_id'] in ids:
                assert r['metadata']['eligibility']['retrospective_conditional']
                yield r


def model_input(sample, variant):
    if variant not in VARIANTS: raise ValueError(variant)
    result=copy.deepcopy(sample['input'])
    if variant in ('history_only','history_context'): result.pop('profile')
    if variant in ('history_only','history_profile'):
        result['context']={k:v for k,v in result['context'].items() if k in ('forecast_origin','target_window','time_basis','measurement_scope')}
    if variant=='full_without_daytime_home':
        result['profile']['usage_habits']=[h for h in result['profile']['usage_habits'] if h['behavior']!='someone_home']
    return result


def render(sample, variant):
    return {'sample_id':sample['sample_id'], 'schema_version':sample['schema_version'],
            'messages':[
                {'role':'system','content':'根据所提供的家庭资料、历史用电和目标日条件预测整户电量。每个数值是指定间隔内的kWh；null表示未知。只输出含energy_kwh数组的JSON，按目标窗口排序。'},
                {'role':'user','content':json.dumps(model_input(sample,variant),ensure_ascii=False,separators=(',',':'),allow_nan=False)},
                {'role':'assistant','content':json.dumps(sample['output'],separators=(',',':'),allow_nan=False)}],
            'metadata':{'track':'retrospective_conditional','input_variant':variant,
                        'availability':sample['metadata']['availability'],
                        'loss_scope_required':'assistant_content_only',
                        'strict_prospective_eligible':False}}


def export(root, output, split, variant, track):
    if track!='retrospective_conditional':
        raise ValueError('No individually time-verified rows qualify for strict_prospective; use the explicitly retrospective track.')
    if split not in ('train','validation','test'): raise ValueError(split)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    n=0
    with output.open('wb') as binary, gzip.GzipFile(filename='',fileobj=binary,mode='wb',mtime=0) as f:
        for source in ('sgsc','iflex'):
            for r in read_samples(source,split,root):
                f.write((json.dumps(render(r,variant),ensure_ascii=False,allow_nan=False)+'\n').encode());n+=1
    print(json.dumps({'records':n,'split':split,'variant':variant,'track':track,'training_executed':False}))
    return n


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT/'benchmark/v1')
    p.add_argument('--split',choices=['train','validation','test'],required=True)
    p.add_argument('--variant',choices=VARIANTS,default='full')
    p.add_argument('--track',choices=['retrospective_conditional','strict_prospective'],required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();export(a.root,a.output,a.split,a.variant,a.track)
