"""Select matching SGSC source records, verify against raw CSVs, and plot observed loads."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    with gzip.open(path,'rt') as f:
        for line in f:yield json.loads(line)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode(x):return json.dumps(x,sort_keys=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--household-csv',type=Path,required=True)
    p.add_argument('--pipeline-root',type=Path,required=True)
    p.add_argument('--plot',action='store_true')
    a=p.parse_args();out=ROOT/'analysis/sgsc_matching_households';out.mkdir(parents=True,exist_ok=True)
    profiles={r['profile_id']:r for r in read(ROOT/'benchmark/v1/profiles/sgsc.jsonl.gz')}
    splits={r['sample_id']:r['split'] for r in csv.DictReader((ROOT/'benchmark/v1/splits/household_holdout.csv').open())}
    raw_fields=[k for k in next(iter(profiles.values()))['metadata']['source_profile_provenance']['raw_answers'] if k!='CUSTOMER_KEY' and not k.endswith('_DATE')]
    required=['DWELLING_TYPE_CD','NUM_REFRIGERATORS','NUM_ROOMS_HEATED','HAS_GAS','HAS_GAS_HEATING','HAS_GAS_HOT_WATER','HAS_GAS_COOKING','HAS_AIRCON','AIRCON_TYPE_CD','HAS_POOLPUMP','HAS_GAS_OTHER_APPLIANCE','IS_HOME_DURING_DAYTIME','HAS_GENERATION']
    groups=defaultdict(list);all_rows=list(read(ROOT/'benchmark/v1/data/sgsc.jsonl.gz'));eligible=0
    for d in all_rows:
        if splits[d['sample_id']]!='train':continue
        if any('profile_event_support_only' in e for e in d['metadata']['condition_evidence_groups']):continue
        raw=profiles[d['metadata']['profile_id']]['metadata']['source_profile_provenance']['raw_answers']
        if any(not raw[k] for k in required):continue
        if raw['HAS_GENERATION']!='N' or raw['NET_SOLAR_CNT']!='0' or raw['GROSS_SOLAR_CNT']!='0':continue
        eligible+=1
        sig=encode([d['input']['profile'],{k:raw[k] for k in raw_fields},d['input']['context'],d['metadata']['condition_evidence_groups']])
        groups[sig].append(d)
    candidates=[rs for rs in groups.values() if len(rs)>=2]
    candidates.sort(key=lambda rs:(-len(rs),rs[0]['input']['context']['target_window']['start'],sorted(d['metadata']['profile_id'] for d in rs)))
    if not candidates:raise ValueError('No exact matched source-record group')
    selected=sorted(candidates[0],key=lambda d:d['metadata']['profile_id'])[:3]
    ids=[d['metadata']['profile_id'] for d in selected]
    raw_profiles={hid:profiles[hid]['metadata']['source_profile_provenance']['raw_answers'] for hid in ids}
    differing={k:[raw_profiles[h][k] for h in ids] for k in next(iter(raw_profiles.values())) if len({raw_profiles[h][k] for h in ids})>1}
    # Current selected pair also matches all recorded dates, beyond selection requirements.
    assert set(differing)=={'CUSTOMER_KEY'},differing
    assert len(next(iter(raw_profiles.values())))==46
    assert len({encode(d['input']['profile']) for d in selected})==1
    assert len({encode(d['input']['context']) for d in selected})==1
    assert len({d['metadata']['source_sample_ids'][0].split(':')[-1] for d in selected})==1
    csv_hash=sha(a.household_csv);matched_source={}
    with a.household_csv.open(encoding='utf-8-sig') as f:
        for number,r in enumerate(csv.DictReader(f),start=2):
            hid='sgsc:'+r['CUSTOMER_KEY']
            if hid in ids:
                assert hid not in matched_source
                prov=profiles[hid]['metadata']['source_profile_provenance']
                assert r==raw_profiles[hid] and number==prov['csv_record_number_including_header'] and csv_hash==prov['sha256']
                matched_source[hid]=number
    assert set(matched_source)==set(ids)
    by_date=defaultdict(dict)
    for d in all_rows:
        if d['metadata']['profile_id'] in ids:by_date[d['input']['context']['target_window']['start']][d['metadata']['profile_id']]=d
    shared={date:rs for date,rs in sorted(by_date.items()) if set(rs)==set(ids) and len({encode(d['input']['context']) for d in rs.values()})==1 and len({encode(d['metadata']['condition_evidence_groups']) for d in rs.values()})==1}
    verified={};raw_sources={r.get('household_id'):r for r in json.loads((ROOT/'baseline/v1/provenance/raw_curve_sources.json').read_text()) if r.get('source')=='sgsc'}
    for hid in ids:
        key=hid.split(':')[-1];receipt=raw_sources[key];path=a.pipeline_root/receipt['file'];digest=sha(path);assert digest==receipt['sha256']
        lookup={};duplicate=set()
        with path.open() as f:
            for r in csv.DictReader(f,skipinitialspace=True):
                r={k.strip():v.strip() for k,v in r.items()};assert r['CUSTOMER_ID']==key
                t=r['READING_DATETIME']
                if t in lookup:duplicate.add(t)
                lookup[t]=r
        checked=set();window_count=0;max_error=0.0;values=[]
        for date,rs in shared.items():
            d=rs[hid];hist=d['input']['history'];start=datetime.fromisoformat(hist['start']);pred=d['output']['energy_kwh'];whole=hist['energy_kwh']+pred
            assert len(whole)==384 and d['input']['context']['measurement_scope']=='single_general_supply'
            for i,v in enumerate(whole,1):
                label=(start+timedelta(minutes=30*i)).strftime('%Y-%m-%d %H:%M:%S')
                assert label in lookup and label not in duplicate
                row=lookup[label];channels={k:float(row[k]) for k in ['GENERAL_SUPPLY_KWH','CONTROLLED_LOAD_KWH','GROSS_GENERATION_KWH','NET_GENERATION_KWH','OTHER_KWH']}
                assert all(math.isfinite(x) and x>=0 for x in channels.values())
                assert all(channels[k]==0 for k in channels if k!='GENERAL_SUPPLY_KWH')
                err=abs(channels['GENERAL_SUPPLY_KWH']-v);max_error=max(max_error,err);assert err==0
                checked.add(label);values.append(v)
            window_count+=1
        verified[hid]={'source_profile_record':matched_source[hid],'source_curve_sha256':digest,'windows_verified':window_count,'point_comparisons':window_count*384,'unique_half_hours':len(checked),'maximum_difference_kwh':max_error,'missing_or_duplicate_selected_intervals':0,'negative_or_nonfinite_selected_values':0,'non_general_channels_nonzero':False}
    primary=selected[0]['input']['context']['target_window']['start']
    result={'selection':{'scope':'Train-only descriptive source-record matching. Source classifications and administrative states are used for matching only, not added to predictive inputs; their acquisition times are unverified. No causal interpretation.',
                        'eligible_samples':eligible,'matched_date_groups':len(candidates),'largest_group_size':len(candidates[0]),'sort':'largest matched group, earliest target date, then lexical household IDs; no target values used directly for ranking','required_nonempty_fields':required,'matched_source_fields':raw_fields},
            'source_hashes':{'household_csv':csv_hash,'benchmark':sha(ROOT/'benchmark/v1/data/sgsc.jsonl.gz'),'profiles':sha(ROOT/'benchmark/v1/profiles/sgsc.jsonl.gz'),'split':sha(ROOT/'benchmark/v1/splits/household_holdout.csv')},
            'households':ids,'raw_profiles':raw_profiles,'differing_original_columns':differing,'equal_original_columns_except_id':45,'common_profile':selected[0]['input']['profile'],
            'primary_date':primary,'common_context':selected[0]['input']['context'],'verification':verified,
            'unverified':['Resident counts and floor areas are not collected in these source profiles.','Device count/power/use and precise location are incomplete.','Shared product and event do not verify equal numeric rates.','Separate customer IDs and different meter series do not independently establish distinct physical dwellings.'],
            'shared_days':{date:{hid:{'sample_id':d['sample_id'],'event':d['input']['context']['events'],'history_kwh':d['input']['history']['energy_kwh'],'target_kwh':d['output']['energy_kwh'],'history_daily_mean_kwh':math.fsum(d['input']['history']['energy_kwh'])/7,'target_daily_kwh':math.fsum(d['output']['energy_kwh'])} for hid,d in rs.items()} for date,rs in shared.items()}}
    (out/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if a.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        colors=['#1769aa','#d46418','#35835b'];edges=np.arange(49)/2
        fig,axs=plt.subplots(2,1,figsize=(11,7.5),sharex=True,layout='constrained')
        for hid,color in zip(ids,colors):
            row=result['shared_days'][primary][hid];v=np.array(row['target_kwh']);name=hid.split(':')[-1]
            axs[0].stairs(v*2,edges,label=f'{name}: {v.sum():.3f} kWh',color=color,lw=1.9,baseline=None)
            axs[1].stairs(v/v.sum()*100,edges,label=name,color=color,lw=1.9,baseline=None)
        event=selected[0]['input']['context']['events'][0];origin=datetime.fromisoformat(primary)
        lo=(datetime.fromisoformat(event['start'])-origin).total_seconds()/3600;hi=(datetime.fromisoformat(event['end'])-origin).total_seconds()/3600
        for ax in axs:
            ax.axvspan(lo,hi,color='grey',alpha=.12,label='Recorded event window');ax.grid(alpha=.2);ax.set_xlim(0,24);ax.set_xticks(range(0,25,3));ax.legend()
        axs[0].set(title='SGSC: two customer records with identical recorded attributes | '+primary[:10],ylabel='Half-hour average power (kW)')
        axs[1].set(title='Shape comparison (normalized for display only)',ylabel='Share of daily energy (%)',xlabel='Hour (source clock)')
        fig.savefig(out/'matched_pair.png',dpi=170);plt.close(fig)
        fig,axs=plt.subplots(3,3,figsize=(13,9),sharex=True,sharey=True,layout='constrained')
        for ax,(date,rs) in zip(axs.flat,result['shared_days'].items()):
            for hid,color in zip(ids,colors):ax.stairs(np.array(rs[hid]['target_kwh'])*2,edges,color=color,label=hid.split(':')[-1],lw=1.2,baseline=None)
            ax.set_title(date[:10]);ax.set_xticks([0,6,12,18,24]);ax.set_xlim(0,24);ax.grid(alpha=.15)
        axs[0,0].legend();fig.suptitle('All nine shared retained event dates: the same two SGSC records')
        fig.supxlabel('Hour (source clock)');fig.supylabel('Half-hour average power (kW)')
        fig.savefig(out/'all_shared_days.png',dpi=150);plt.close(fig)
    print(json.dumps({'households':ids,'original_equal_columns':45,'shared_days':len(shared),'primary':primary,'primary_totals':{h:result['shared_days'][primary][h]['target_daily_kwh'] for h in ids},'verification':verified},indent=2))

if __name__=='__main__':main()
