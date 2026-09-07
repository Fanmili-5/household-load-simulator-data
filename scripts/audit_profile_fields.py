"""Inventory all iFlex Survey 1 answer columns for the retained households.

This audit does not add unreviewed answers to model inputs or modify observations.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from read_data import ROOT, read_records


def category(k):
    if k=='ID': return 'linkage'
    if k in ('q_kjonn','q19','q21','q22','husstand') or k.startswith(('q20.','q24.')):
        return 'people_and_socioeconomic'
    if k=='q23':return 'occupancy'
    if k in ('q4','q5','q6','q7','q8') or k.startswith('q6'):
        return 'dwelling_and_meter_scope'
    if k.startswith('q16'):return 'vehicles_and_charging'
    if k.startswith('q9d') or k in ('q10','q11','q12','q13','q14b'):
        return 'comfort_and_usage_habits'
    if k.startswith(('q9','q14','q15','q17')):return 'equipment_and_energy_systems'
    if k.startswith('q_ekstra') or k in ('q1','q2','q3'):
        return 'energy_attention_and_contract'
    if k=='q18':return 'meter_scope'
    return 'requires_classification'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--survey-directory',required=True,type=Path)
    args=p.parse_args()
    existing={r['household_id']:r['input']['profile'] for r in read_records('iflex')}
    paths={n:args.survey_directory/n for n in ('survey1_answers.csv','survey1_questions.csv')}
    with paths['survey1_answers.csv'].open(encoding='utf-8-sig') as f:
        reader=csv.DictReader(f);columns=reader.fieldnames
        rows=[r for r in reader if r['ID'] in existing]
    assert len(rows)==len(existing)==len({r['ID'] for r in rows})==314
    questions={}
    with paths['survey1_questions.csv'].open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):questions.setdefault(row['Question_ID'],row['Question'])
    # Source selection additionally used meter questions; these are not model profile fields.
    used={'q4','q5','q6','q7','q19','q23','q9N1','q9N2','q9N3','q14','q16_bil_b'}
    selection={'q17','q18','q6b1','q6b2'}
    missing={'','NA','NaN','nan'}
    unknown={"Don't know","Don't want to answer","Unsure / don't know",'-'}
    inventory=[]
    for k in columns:
        inventory.append({'field':k,'question':questions.get(k,'Anonymous household ID' if k=='ID' else ''),
            'category':category(k),'households':314,
            'non_missing_answers':sum(r[k] not in missing for r in rows),
            'explicit_unknown_or_declined_answers':sum(r[k] in unknown for r in rows),
            'current_use':'linkage' if k=='ID' else 'exported_profile' if k in used else 'selection_only' if k in selection else 'not_exported',
            'timing_basis':'Survey 1; retained phase-1 cohort; no individual response timestamp established here'})
    age_oversized=age_sum_mismatch=life_oversized=0
    for r in rows:
        size=int(r['q19'].split()[0])
        ages=[int(r[f'q20.{i}']) for i in range(1,10)]
        life=[int(r[f'q24.{i}']) for i in range(1,8)]
        age_oversized+=any(n<0 or n>size for n in ages)
        age_sum_mismatch+=sum(ages)!=size
        life_oversized+=any(n<0 or n>size for n in life)
    out=ROOT/'provenance'
    with (out/'iflex_profile_field_inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
    report={'retained_households':314,'answer_columns_inventoried':len(columns),
        'question_columns_without_label':[r['field'] for r in inventory if not r['question']],
        'unclassified_fields':[r['field'] for r in inventory if r['category']=='requires_classification'],
        'source_sha256':{n:hashlib.sha256(path.read_bytes()).hexdigest() for n,path in paths.items()},
        'quality_flags':{'households_with_age_bin_count_exceeding_household_size':age_oversized,
                         'households_with_age_bin_sum_not_equal_to_household_size':age_sum_mismatch,
                         'households_with_life_status_bin_count_exceeding_household_size':life_oversized,
                         'income_unknown':sum(r['q22']=="Don't know" for r in rows),
                         'income_declined':sum(r['q22']=="Don't want to answer" for r in rows)},
        'scope':'field inventory and consistency flags only; no guessed corrections or SFT export'}
    (out/'iflex_profile_field_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
