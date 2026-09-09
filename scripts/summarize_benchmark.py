"""Recompute dataset counts and snapshot ages from the actual published samples."""
import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
INPUTS={'sgsc':'benchmark/v1/data/sgsc.jsonl.gz',
        'iflex':'benchmark/v1/data/iflex.jsonl.gz',
        'lirneasia':'extensions/lirneasia_history_v1/data/lirneasia.jsonl.gz'}


def audit():
    result={}
    for source,relative in INPUTS.items():
        households=Counter();dates=set();ages=[]
        with gzip.open(ROOT/relative,'rt') as f:
            for line in f:
                sample=json.loads(line);meta=sample['metadata']
                hid=meta.get('household_id',meta.get('profile_id'))
                if not hid:raise ValueError('Missing household key')
                households[hid]+=1
                target=sample['input']['context']['target_window']['start'][:10]
                dates.add(target)
                if source=='lirneasia':
                    ages.append((datetime.fromisoformat(target)-datetime.fromisoformat(meta['profile_as_of'])).days)
        row={'households':len(households),'samples':sum(households.values()),
             'target_dates':len(dates),'first_target_day':min(dates),'last_target_day':max(dates),
             'samples_per_household':{'minimum':min(households.values()),'median':statistics.median(households.values()),'maximum':max(households.values())},
             'input_file':relative,'input_sha256':hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()}
        if ages:row['survey_age_at_target_days']={'minimum':min(ages),'median_over_samples':statistics.median(ages),'maximum':max(ages)}
        result[source]=row
    result['audit_scope']='Independent streamed counts from released files; no predictive evaluation or model training.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
