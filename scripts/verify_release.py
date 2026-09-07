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
    parser.add_argument('--sgsc-households',type=Path)
    parser.add_argument('--write-report',action='store_true')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'provenance/manifest.json').read_text())
    report={'passed':False,'checks':[], 'records':{},'source_value_comparison':bool(args.pipeline_root)}
    seen=set()
    household_profiles={}
    if args.pipeline_root:
        selection=args.pipeline_root/'evidence/20260907_sgsc_condition_reaudit/sample_evidence_groups.jsonl'
        assert sha(selection)==manifest['selection_sha256']
        groups={r['sample_id']:r for r in map(json.loads,selection.open())}
        assert args.sgsc_households, '--sgsc-households is required with --pipeline-root'
        assert sha(args.sgsc_households)==manifest['profile_sources']['sgsc']['sha256']
        needed={g['profile_csv_record_number'] for g in groups.values() if g['new_evidence_group']!='unresolved_conflict_or_missing_boundary'}
        with args.sgsc_households.open(encoding='utf-8-sig') as f:
            original_sgsc={i:r for i,r in enumerate(csv.DictReader(f),2) if i in needed}
        survey=args.pipeline_root/'runs/iflex_all_candidates_v1/source_stage/raw/survey1_answers.csv'
        assert sha(survey)==manifest['profile_sources']['iflex']['sha256']
        with survey.open(encoding='utf-8-sig') as f:
            original_iflex={r['ID']:r for r in csv.DictReader(f)}
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
            p=r['input']['profile'];prov=r['metadata']['profile_provenance'];answers=prov['raw_answers']
            key=(source,r['household_id'])
            if key in household_profiles:assert household_profiles[key]==p
            else:household_profiles[key]=p
            assert p['profile_schema_version']=='household-baseline-profile/2'
            assert set(('people','dwelling','preferences','usage_habits','energy_attitudes','energy_systems','vehicles'))<=p.keys()
            assert answers['CUSTOMER_KEY' if source=='sgsc' else 'ID']==r['household_id']
            assert prov['not_model_input'] is True
            assert len(answers)==(46 if source=='sgsc' else 96)
            if source=='iflex':
                assert p['energy_systems']['solar_pv_present'] is False and answers['q17']=='No'
                assert p['energy_systems']['farm_or_business_shares_meter'] is False and answers['q18']=='No'
                assert p['energy_systems']['solar_pv_capacity_kw'] is None and answers['q17b.1']=='NA'
                assert p['energy_systems']['battery_connected_to_pv'] is None and answers['q17c']=='NA'
                assert p['people']['household_size']==int(answers['q19'].split()[0])
                expected_ev=int(answers['q16.1']) if answers['q16.1'].isdigit() else None
                assert p['vehicles']['electric_or_plugin_hybrid_count']==expected_ev
                ev=next(a for a in p['appliances'] if a['appliance']=='electric_or_plugin_hybrid_car')
                assert ev['count']==expected_ev
                assert p['preferences']['living_room_comfort_temperature_celsius']==float(answers['q10'])
                assert p['usage_habits']['heating_control']==answers['q13']
                assert p['people']['gross_household_income_band']==(None if answers['q22'] in ("Don't know","Don't want to answer") else answers['q22'])
                ages=[int(answers[f'q20.{i}']) for i in range(1,10)]
                invalid_age=sum(ages)!=p['people']['household_size'] or max(ages)>p['people']['household_size']
                assert (p['people']['age_group_counts'] is None)==invalid_age
                if not invalid_age:assert list(p['people']['age_group_counts'].values())==ages
                for i,name in enumerate(('school_or_kindergarten','student','part_time_work','full_time_work','unemployed_or_not_in_education','retired','other'),1):
                    status_count=int(answers[f'q24.{i}'])
                    assert p['people']['life_status_counts'][name]==(None if status_count>p['people']['household_size'] else status_count)
            else:
                assert p['preferences']['agreed_to_sms_contact']=={'Y':True,'N':False}.get(answers['HAS_AGREED_TO_SMS'])
                assert p['people']['household_size'] is None
                assert p['people']['gross_household_income_band'] is None
                assert p['energy_attitudes']['reported_electricity_reduction_effort']==(answers['REDUCING_CONSUMPTION_CD'] or None)
                assert p['energy_attitudes']['internet_access']=={'Y':True,'N':False}.get(answers['HAS_INTERNET_ACCESS'])
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
            assert p['usage_habits']['daytime_home_scope']=='weekday_daytime'
            # Independently reconstruct the whole profile from the actual CSV;
            # checking only CSV == summary_row would miss serializer omissions.
            reconstructed={}
            for group,value in p.items():
                if group in ('people','dwelling','preferences','usage_habits','energy_attitudes','energy_systems','vehicles'):
                    reconstructed[group]={}
                    for k,v in value.items():
                        cell=table[count]['profile_'+group+'_'+k]
                        reconstructed[group][k]=json.loads(cell) if isinstance(v,(dict,list)) else (None if v is None and cell=='' else cell)
                        if not isinstance(v,(dict,list)):
                            assert cell==('' if v is None else str(v))
                            reconstructed[group][k]=v
                else:
                    cell=table[count]['profile_'+group]
                    reconstructed[group]=json.loads(cell) if isinstance(value,(dict,list)) else cell
            assert reconstructed==p
            assert table[count]=={k:('' if v is None else str(v)) for k,v in row.items()}
            count+=1
            if args.pipeline_root:compare[r['sample_id']]=r
        assert len(table)==count==info['records']
        assert len(homes)==info['households']
        with (ROOT/'tables'/f'{source}_households.csv').open(encoding='utf-8-sig',newline='') as f:
            household_table=list(csv.DictReader(f))
        event_first={}
        for row in table:event_first.setdefault(row['household_id'],row)
        assert len(household_table)==len(homes)
        assert len({row['household_id'] for row in household_table})==len(homes)
        for row in household_table:
            expected={k:v for k,v in event_first[row['household_id']].items() if k in ('source','household_id','meter_configuration') or k.startswith('profile_')}
            assert row==expected
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
                    assert shared['input']['context']==raw['input']['context']
                    for key,value in raw['input']['profile'].items():
                        if key!='appliances':assert shared['input']['profile'][key]==value
                    for a in raw['input']['profile']['appliances']:
                        b=next(v for v in shared['input']['profile']['appliances'] if v['appliance']==a['appliance'])
                        for key,value in a.items():
                            if source=='iflex' and a['appliance']=='electric_or_plugin_hybrid_car' and key=='count':continue
                            assert b[key]==value
                    prov=shared['metadata']['profile_provenance']
                    if source=='sgsc':
                        record=groups[raw['sample_id']]['profile_csv_record_number']
                        assert prov['raw_answers']==original_sgsc[record]==raw['provenance']['raw_profile']
                    else:assert prov['raw_answers']==original_iflex[raw['household_id']]
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
        assert r['input']['profile']==household_profiles[(source,r['metadata']['household_id'])]
        if args.pipeline_root:
            original=json.loads((args.pipeline_root/'reports/notion_day_audit_20260907'/f'{source}_day_example.json').read_text())
            assert r['output']==original['output']
            assert r['input']['history']==original['input']['history']
            assert r['input']['context']==original['input']['context']
    for name in ('sgsc_single','sgsc_two_meter','iflex'):
        example=json.loads((ROOT/'examples'/f'{name}_observation.json').read_text())
        assert example['input']['profile']==household_profiles[(example['source'],example['household_id'])]
    report['checks']=['file hashes','candidate membership and household counts','no duplicate sample ids',
        'household meter totals for every target and history slot','history and target lengths',
        'finite nonnegative values','CSV equals distributed JSON','excluded rows absent',
        'full-day examples separate','no local paths or recognized credential prefixes in records']
    report['checks'].append('expanded household profiles, original answers, EV counts, demographic quality flags, household tables and all examples')
    if args.pipeline_root:report['checks'].append('all original curve/context values and legacy profile fields preserved; every full profile matched to original household CSV or Survey 1')
    report['passed']=True
    if args.write_report:
        (ROOT/'provenance/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
