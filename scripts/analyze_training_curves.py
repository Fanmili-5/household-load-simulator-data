"""Reproducible, training-only descriptive curves and untuned naive forecasts.

Select the largest iFlex matched-input group, with lexical tie breaking, before
examining its targets. Never use validation/test rows in statistics or plots.
Requires numpy and matplotlib. Does not fit a model or change the benchmark.
"""
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/train_curves'
SOURCES = {
    'sgsc': ('benchmark/v1/data/sgsc.jsonl.gz', 'benchmark/v1/splits/household_holdout.csv'),
    'iflex': ('benchmark/v1/data/iflex.jsonl.gz', 'benchmark/v1/splits/household_holdout.csv'),
    'lirneasia': ('extensions/lirneasia_history_v1/data/lirneasia.jsonl.gz', 'extensions/lirneasia_history_v1/splits/household_holdout.csv'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_train(source, data, split):
    split_rows = list(csv.DictReader((ROOT / split).open()))
    if 'sample_id' in split_rows[0]:
        split_map = {r['sample_id']: r['split'] for r in split_rows}
        get_split = lambda d: split_map[d['sample_id']]
    else:
        split_map = {r['household_id']: r['split'] for r in split_rows}
        get_split = lambda d: split_map[d['metadata']['household_id']]
    records = []
    with gzip.open(ROOT / data, 'rt') as f:
        for line in f:
            d = json.loads(line)
            if get_split(d) != 'train':
                continue
            i = d['input']; h = i['history']; c = i['context']
            assert h['end'] == c['target_window']['start']
            assert h['start'] < h['end']
            per_hour = 60 // h['interval_minutes']
            hist = np.asarray(h['energy_kwh']).reshape(7, 24, per_hour).sum(axis=2)
            target = np.asarray(d['output']['energy_kwh']).reshape(24, per_hour).sum(axis=1)
            assert np.isfinite(hist).all() and np.isfinite(target).all()
            row = {'id': d['sample_id'], 'household': d['metadata'].get('profile_id', d['metadata'].get('household_id')),
                   'history': hist, 'target': target, 'context': c}
            if source == 'iflex':
                row['profile'] = i['profile']
            records.append(row)
    return records


def summarize(records):
    household_days = defaultdict(list)
    metric = {name: defaultdict(list) for name in ['previous_day', 'previous_week_same_day', 'seven_day_slot_mean']}
    for r in records:
        household_days[r['household']].append((float(r['history'].sum()/7), float(r['target'].sum())))
        preds = [r['history'][-1], r['history'][0], r['history'].mean(axis=0)]
        for name, pred in zip(metric, preds):
            metric[name][r['household']].append(float(np.abs(pred-r['target']).mean()))
    points = np.asarray([np.mean(v,axis=0) for _,v in sorted(household_days.items())])
    return {
        'samples': len(records), 'households': len(household_days),
        'household_mean_daily_energy_pearson_r': float(np.corrcoef(points.T)[0,1]),
        'hourly_mae_kw_equal_households': {k: float(np.mean([np.mean(v) for v in by_h.values()])) for k,by_h in metric.items()},
        'scatter_points': [{'household': h, 'mean_prior_daily_kwh': float(x), 'mean_target_daily_kwh':float(y)}
                           for h,(x,y) in zip(sorted(household_days),points)],
    }


def group_key(r):
    p=r['profile'];c=r['context']
    signature=tuple((a['type'], a['present'], a['count'], a['subtype']) for a in p['appliances'])
    return (p['household']['resident_count'], signature, c['target_window']['start'], c['region'], tuple(c['events'][0]['price_per_kwh']))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records={s: load_train(s,*p) for s,p in SOURCES.items()}
    summary={s:summarize(rs) for s,rs in records.items()}
    groups=defaultdict(list)
    for r in records['iflex']:
        if r['profile']['household']['resident_count'] is not None:
            groups[group_key(r)].append(r)
    # This choice uses input fields and group size, never target differences.
    key, selected=sorted(groups.items(), key=lambda kv:(-len(kv[1]),repr(kv[0])))[0]
    selected=sorted(selected,key=lambda r:r['id'])
    assert len({r['household'] for r in selected})==len(selected)
    assert len({group_key(r) for r in selected})==1
    profiles=[]
    for r in selected:
        p=r['profile']; y=r['target']; hist=r['history']
        profiles.append({'sample_id':r['id'],'household':r['household'],'profile':p,
                         'prior_seven_hourly_kwh':hist.tolist(),'target_hourly_kwh':y.tolist(),
                         'history_daily_mean_kwh':float(hist.sum()/7),'target_daily_kwh':float(y.sum()),
                         'target_peak_hourly_kw':float(y.max()),'target_peak_hour_start':int(y.argmax()),
                         'self_seven_day_mean_hourly_mae_kw':float(np.abs(hist.mean(axis=0)-y).mean())})
    totals=[p['target_daily_kwh'] for p in profiles]
    matched={'selection_rule':'Largest train-only group with identical resident count, complete released appliance type/present/count/subtype vector, region, target day and 24-hour experimental price; ties by repr(input key), no target-based selection.',
             'matching_does_not_establish':'Equal device ratings, unrecorded appliances, actual operations, identical dwellings, or identical weather exposure.',
             'households':len(selected),'resident_count':key[0],'region':key[3],'target_start':key[2],
             'appliance_signature':key[1],'price_signal_nok_per_kwh':key[4],
             'target_daily_min_kwh':min(totals),'target_daily_max_kwh':max(totals),
             'target_daily_max_min_ratio':max(totals)/min(totals),'members':profiles}
    evidence={'scope':'TRAIN ONLY exploratory description and untuned naive forecasts. No learned model, validation/test evaluation, causal claim, or strategy execution.',
              'aggregation':'Hourly MAE within day, mean within household, then equal household mean; sources reported separately. Correlation uses one mean point per household, not independent overlapping days.',
              'source_hashes':{s:{'data':sha(ROOT/d),'split':sha(ROOT/p)} for s,(d,p) in SOURCES.items()},
              'summary':summary,'matched_iflex':matched}
    (OUT/'training_curve_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    colors=plt.get_cmap('tab10').colors
    fig,ax=plt.subplots(3,1,figsize=(11,9),gridspec_kw={'height_ratios':[2.1,2.1,1]},constrained_layout=True)
    for j,r in enumerate(selected):
        label=r['household'].split(':')[-1]
        ax[0].stairs(r['target'],np.arange(25),label=f'{label} | {r["target"].sum():.2f} kWh',color=colors[j],linewidth=1.6)
        ax[1].stairs(100*r['target']/r['target'].sum(),np.arange(25),label=label,color=colors[j],linewidth=1.6)
    ax[0].set_ylabel('Hourly mean kW');ax[1].set_ylabel('Share of daily energy (%)')
    ax[0].legend(ncol=3,fontsize=9)
    ax[2].stairs(key[4],np.arange(25),color='#555555',fill=True,alpha=.25)
    ax[2].set_ylabel('Experiment signal\nNOK/kWh');ax[2].set_xlabel('Hour of target day (source clock)')
    for a in ax:a.set_xlim(0,24);a.set_xticks(range(0,25,3));a.grid(alpha=.18)
    fig.suptitle(f'iFlex | {len(selected)} two-person households, same recorded appliance configuration\n{key[3]} | {key[2][:10]} | same experimental signal | TRAIN ONLY',fontsize=12)
    fig.savefig(OUT/'matched_households.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(len(selected),1,figsize=(11,12),constrained_layout=True,sharex=True)
    for j,(a,r) in enumerate(zip(axs,selected)):
        for day in r['history']:a.stairs(day,np.arange(25),color='#aaaaaa',alpha=.45,linewidth=.8)
        a.stairs(r['history'].mean(axis=0),np.arange(25),color='#2878a1',linewidth=1.7,label='Prior 7-day same-hour mean')
        a.stairs(r['target'],np.arange(25),color='#d66b21',linewidth=1.8,label='Measured target day')
        a.set_title(f'{r["household"]} | prior daily mean {r["history"].sum()/7:.2f} kWh | target {r["target"].sum():.2f} kWh',loc='left',fontsize=10)
        a.set_ylabel('Hourly mean kW');a.grid(alpha=.18);a.set_xlim(0,24)
        a.set_xticks(range(0,25,3))
    axs[0].legend(fontsize=8,ncol=2);axs[-1].set_xlabel('Hour (source clock); grey = each of the 7 observed history days')
    fig.suptitle('Same matched households | observed history varies across and within households\nBlue uses only prior observations; orange is the recorded target, not a strategy effect',fontsize=12)
    fig.savefig(OUT/'matched_history_target.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(13,4.3),constrained_layout=True)
    for a,(source,s) in zip(axs,summary.items()):
        x=[p['mean_prior_daily_kwh'] for p in s['scatter_points']];y=[p['mean_target_daily_kwh'] for p in s['scatter_points']]
        a.scatter(x,y,s=12,alpha=.45,color='#31688e');lim=max(max(x),max(y))*1.03
        a.plot([0,lim],[0,lim],'--',color='#999999',linewidth=.8)
        a.set_xlim(0,lim);a.set_ylim(0,lim);a.set_xlabel('Prior 7-day daily mean (kWh)')
        a.set_ylabel('Target daily mean (kWh)');a.grid(alpha=.15)
        a.set_title(f'{source}: {s["households"]} households\nr = {s["household_mean_daily_energy_pearson_r"]:.3f}',fontsize=11)
    fig.suptitle('TRAIN ONLY | one mean point per household | descriptive scale association, not a model score',fontsize=12)
    fig.savefig(OUT/'history_target_association.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(12,4.3),constrained_layout=True)
    for a,(source,s) in zip(axs,summary.items()):
        vals=list(s['hourly_mae_kw_equal_households'].values())
        bars=a.bar(['Prev day','Prev week','7-day mean'],vals,color=['#a1b7c3','#5e8ea5','#246784'])
        a.bar_label(bars,fmt='%.3f',padding=3,fontsize=9);a.set_ylim(0,max(vals)*1.2)
        a.set_title(source);a.set_ylabel('Equal-household hourly MAE (kW)');a.grid(axis='y',alpha=.2)
    fig.suptitle('TRAIN ONLY | untuned history-only forecasts | separate sources and scales',fontsize=12)
    fig.savefig(OUT/'naive_history_diagnostics.png',dpi=170);plt.close(fig)
    print(json.dumps({'summary':{s:{k:v for k,v in z.items() if k!='scatter_points'} for s,z in summary.items()},
                      'matched':{k:v for k,v in matched.items() if k not in ['members','appliance_signature','price_signal_nok_per_kwh']}}))


if __name__=='__main__':main()
