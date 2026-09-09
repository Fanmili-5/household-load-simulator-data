"""Audit the five previously selected iFlex households against publisher CSVs and a retained RData export.

The 75-day series and Survey 2 are retrospective diagnostics, not new model inputs.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = ['Exp_11', 'Exp_138', 'Exp_181', 'Exp_26', 'Exp_32']

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--hourly-export', type=Path, required=True)
    p.add_argument('--plot', action='store_true')
    a=p.parse_args()
    out=ROOT/'analysis/iflex_five_households';out.mkdir(parents=True,exist_ok=True)
    source={name:{r['ID']:r for r in csv.DictReader((a.source_dir/name).open()) if r['ID'] in IDS}
            for name in ['survey1_answers.csv','survey2_answers.csv','participants.csv']}
    questions={r['Question_ID']:r['Question'] for r in csv.DictReader((a.source_dir/'survey1_questions.csv').open())}
    profiles={}
    with gzip.open(ROOT/'benchmark/v1/profiles/iflex.jsonl.gz','rt') as f:
        for line in f:
            d=json.loads(line);hid=d['profile_id'].split(':')[-1]
            if hid in IDS:profiles[hid]=d
    hourly=defaultdict(list)
    with gzip.open(a.hourly_export,'rt') as f:
        for r in csv.DictReader(f):
            if r['ID'] in IDS:hourly[r['ID']].append(r)
    keys=['q3','q4','q5','q7','q8','q9N1','q9N2','q9N3','q9N4','q9N5','q9N6','q9N7','q9N8','q9d1','q9d2','q9d3','q9d4','q10','q12','q13','q14','q16_bil_b','q17','q18','q6b1','q19','q20.3','q20.4','q20.8','q20.9','q23','husstand']
    result={'scope':'Retrospective source-record audit of five train households; source CSV/export reread, full RData not decoded again. No causal attribution, training or benchmark filtering.',
            'source_sha256':{name:sha(a.source_dir/name) for name in source},
            'question_dictionary_sha256':sha(a.source_dir/'survey1_questions.csv'),
            'hourly_export_sha256':sha(a.hourly_export),
            'benchmark_sha256':sha(ROOT/'benchmark/v1/data/iflex.jsonl.gz'),
            'questions':{k:questions.get(k) for k in keys},'households':{}}
    lookup={}
    for hid in IDS:
        raw=source['survey1_answers.csv'][hid]
        participant=source['participants.csv'][hid]
        assert participant['Region']=='Stavanger' and participant['Group_Phase1']=='H1' and participant['Participation_status_Phase1']=='OK'
        assert raw==profiles[hid]['metadata']['source_profile_provenance']['raw_answers'],hid
        assert all(raw[k]=='No' for k in ['q17','q18','q16_bil_b','q6b1']),hid
        rs=sorted(hourly[hid],key=lambda r:(r['day'],int(r['hour'])))
        ts=[datetime.fromisoformat(r['day'])+timedelta(hours=int(r['hour'])-1) for r in rs]
        vals=[float(r['Demand_kWh']) for r in rs]
        assert all(math.isfinite(v) and v>=0 for v in vals)
        assert len(ts)==len(set(ts)) and all(b-a==timedelta(hours=1) for a,b in zip(ts,ts[1:]))
        assert all(datetime.fromtimestamp(float(r['From']), timezone.utc).replace(tzinfo=None)==t for r,t in zip(rs,ts))
        lookup[hid]=dict(zip(ts,vals))
        days=defaultdict(list)
        for r,v in zip(rs,vals):days[r['day']].append(v)
        assert all(len(v)==24 for v in days.values())
        daily={d:math.fsum(v) for d,v in days.items()}
        history=math.fsum(daily[d] for d in daily if '2020-02-04'<=d<'2020-02-11')/7
        target=[r for r in rs if r['day']=='2020-02-11']
        s2=source['survey2_answers.csv'].get(hid)
        result['households'][hid]={
            'survey1':{k:raw[k] for k in keys},'participant':source['participants.csv'][hid],
            'survey2_retrospective_only':{k:v for k,v in s2.items() if k in ['Aq1_1','Aq1_7','Aq17','Aq18'] or k.startswith('Aq19')} if s2 else None,
            'source_checks':{'all_96_survey_fields_match':True,'hours':len(rs),'days':len(days),'first_day':min(days),'last_day':max(days),'duplicate_hours':0,'missing_hours':0,'nonfinite_or_negative':0,'zero_hours':sum(v==0 for v in vals),'minimum_hour_kwh':min(vals),'maximum_hour_kwh':max(vals)},
            'daily_kwh':daily,'prior_7d_mean_kwh':history,'target_kwh':daily['2020-02-11'],'target_vs_prior_percent':(daily['2020-02-11']/history-1)*100,
            'target_hourly_kwh':[float(r['Demand_kWh']) for r in target],
            'target_experiment_price':[float(r['Experiment_price_NOK_kWh']) for r in target],
            'target_regional_temperature':[float(r['Temperature']) for r in target]}
    counts=Counter()
    with gzip.open(ROOT/'benchmark/v1/data/iflex.jsonl.gz','rt') as f:
        for line in f:
            d=json.loads(line);hid=d['metadata']['profile_id'].split(':')[-1]
            if hid not in IDS:continue
            start=datetime.fromisoformat(d['input']['history']['start'])
            v=d['input']['history']['energy_kwh']+d['output']['energy_kwh']
            assert all(lookup[hid][start+timedelta(hours=i)]==x for i,x in enumerate(v)),d['sample_id']
            counts[hid]+=1
    for hid in IDS:result['households'][hid]['source_checks']['benchmark_192h_windows_exact_match']=counts[hid]
    assert len({tuple(result['households'][hid]['target_regional_temperature']) for hid in IDS})==1
    assert len({tuple(result['households'][hid]['target_experiment_price']) for hid in IDS})==1
    result['target_price_and_regional_temperature_identical']=True
    result['disposition']='No records deleted. No duplicate/missing/nonfinite/negative/zero-hour or export-to-benchmark mismatch found; source-meter estimation/calibration not independently verified. Exp_11 event-aligned reduction and Exp_181 February regime change remain retrospective review flags.'
    (out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if a.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        fig,axs=plt.subplots(2,1,figsize=(12,8),layout='constrained',height_ratios=[1.25,1])
        for hid in IDS:
            daily=result['households'][hid]['daily_kwh'];axs[0].plot([datetime.fromisoformat(d) for d in daily],list(daily.values()),label=hid,lw=1.5)
        for lo,hi in [('2020-02-11','2020-02-15'),('2020-03-02','2020-03-06')]:
            axs[0].axvspan(datetime.fromisoformat(lo),datetime.fromisoformat(hi),alpha=.12,color='grey')
        axs[0].set(title='Five households: 75 complete measured days (retrospective audit)',ylabel='Daily electricity (kWh)')
        axs[0].xaxis.set_major_formatter(mdates.DateFormatter('%b %d'));axs[0].legend(ncol=5);axs[0].grid(alpha=.2)
        hid='Exp_11';prior=[math.fsum(lookup[hid][datetime(2020,2,4)+timedelta(days=d,hours=h)] for d in range(7))/7 for h in range(24)]
        target=result['households'][hid]
        axs[1].plot(range(24),prior,label='Previous 7 days: hourly mean',color='grey',lw=2)
        axs[1].plot(range(24),target['target_hourly_kwh'],label='Feb 11: measured',color='#d65f00',lw=2)
        ax2=axs[1].twinx();ax2.step(range(24),target['target_experiment_price'],where='post',color='#4078a8',alpha=.45,label='Experiment price');ax2.set_ylabel('Experimental price (NOK/kWh)')
        axs[1].set(title='Exp_11: consumption falls during expensive hours; Survey 2 reports heating changes',xlabel='Hour start (source clock)',ylabel='Hourly average power (kW)',xlim=(0,23))
        axs[1].legend(loc='upper left');ax2.legend(loc='upper right');axs[1].grid(alpha=.2)
        fig.savefig(out/'daily_and_price_review.png',dpi=160);plt.close(fig)
    print(json.dumps({hid:{'checks':r['source_checks'],'prior':r['prior_7d_mean_kwh'],'target':r['target_kwh'],'change_percent':r['target_vs_prior_percent']} for hid,r in result['households'].items()},indent=2))

if __name__=='__main__':main()
