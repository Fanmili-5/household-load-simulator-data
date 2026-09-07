"""Account for every source profile column and every exported profile component.

Run after build_release.py. verify_release.py separately checks raw answers against
original source files; this audit checks their disposition in the release.
"""
import csv
import json
from collections import Counter, defaultdict
from read_data import ROOT, read_records

EMPTY = {'', 'NA', 'NaN', 'nan'}
LEGACY_SGSC = {
    'NUM_REFRIGERATORS': 'input.profile.appliances[refrigerator].count',
    'HAS_AIRCON': 'input.profile.appliances[air_conditioner].present',
    'AIRCON_TYPE_CD': 'input.profile.appliances[air_conditioner].type_raw',
    'DRYER_USAGE_CD': 'input.profile.appliances[clothes_dryer].usage_level_raw',
    'HAS_POOLPUMP': 'input.profile.appliances[pool_pump].present',
}
SGSC_DEFERRED = {
    'TRIAL_CUSTOMER_TYPE': '试验招募类型，保留供分组审查；不能解释为住户使用习惯。',
    'CONTROL_GROUP_FLAG': '试验分组标记；保留样本来源说明，不作为家庭特征。',
    'FEEDBACK_TECH1_PRODUCT_CD': '反馈技术产品代码；可能与用电有关，但尚未确认各活动日前是否已启用，暂不送入预测输入。',
    'FEEDBACK_TECH2_PRODUCT_CD': '第二项反馈技术代码；保留原值，活动日前启用时间及产品含义尚未逐户核实。',
    'LIFESTYLE_AUDIT_PRODUCT_CD': '生活方式审计产品代码，当前保留家庭均无回答；不是具体生活习惯。',
    'INFERRED_CELL': '字典标明为内部项目编号；不作为家庭特征。',
    'VERIFIED_CELL': '字典标明为内部项目编号；不作为家庭特征。',
    'SERVICE_TYPE': '家庭供电服务分类；保留来源口径。',
    'SERVICE_LOC_STATUS_NAME': '试验服务状态可能含事后退出或产品变更；不放入预测前输入。',
    'ASSRTD_GAS_USAGE_GROUP_CD': '假定用气等级，推断过程及时点未确认，不当作已观测习惯。',
    'ASSRTD_ELECTRICITY_USE_GRP_CD': '假定用电等级，可能带入目标用电信息，不当作已观测习惯。',
    'AGREEMENT_EXIT_REASON': '退出试验的原因可能在活动后产生；只保留追溯。',
}


def main():
    report={'passed':False,'scope':'retained SGSC household master (46 columns) and iFlex Survey 1 (96 columns); not all source tables or SFT readiness','sources':{}}
    for source in ('sgsc','iflex'):
        records={}
        for r in read_records(source):records.setdefault(r['household_id'],r)
        destinations=defaultdict(set)
        for r in records.values():
            p=r['input']['profile'];prov=r['metadata']['profile_provenance']
            for path,field in prov['field_sources'].items():
                if field:
                    # Multi-select answers feed a list, not a child named q... .
                    if path.endswith('.'+field):path=path[:-(len(field)+1)]
                    for number in (1,2,3):
                        path=path.replace('electric_or_plugin_hybrid_details.'+str(number)+'.',
                                          'electric_or_plugin_hybrid_details['+str(number-1)+'].')
                    destinations[field].add('input.profile.'+path)
            for field in p['household']:destinations[field].add('input.profile.household.'+field)
            for field in p.get('meter_configuration',{}):destinations[field].add('input.profile.meter_configuration.'+field)
            for a in p['appliances']:
                if a.get('source_field'):destinations[a['source_field']].add('input.profile.appliances['+a['appliance']+']')
        if source=='sgsc':
            for field,path in LEGACY_SGSC.items():destinations[field].add(path)
        first=next(iter(records.values()))['metadata']['profile_provenance']['raw_answers']
        columns=list(first);inventory=[]
        for field in columns:
            answers=[r['metadata']['profile_provenance']['raw_answers'][field] for r in records.values()]
            n=sum(v not in EMPTY for v in answers)
            paths=sorted(destinations[field]);reason='整理字段保留原含义；异常、未知、拒答按字段状态处理，原回答留作追溯。'
            if paths:disposition='structured_input'
            elif field==('CUSTOMER_KEY' if source=='sgsc' else 'ID'):
                disposition='household_linkage';paths=['household_id'];reason='同户关联标识；不解释为行为特征。'
            elif source=='sgsc' and field=='TARIFF_PRODUCT_CD':
                disposition='event_context_reviewed_separately';paths=['input.context.tariff_product_code'];reason='输入的活动产品代码沿用已核对的活动构造；主表记录保留追溯，不用来覆盖活动时点条件。'
            elif source=='sgsc' and field=='ASSRTD_CLIMATE_ZONE_CD':
                disposition='equivalent_description_in_input';paths=['input.profile.household.ASSRTD_CLIMATE_ZONE_DESC'];reason='输入已保留假定气候区文字描述；数值代码保留追溯。'
            elif source=='sgsc' and field in SGSC_DEFERRED:
                disposition='provenance_only';reason=SGSC_DEFERRED[field]
            elif source=='sgsc' and field.endswith('_DATE'):
                disposition='provenance_only';reason='安装、调查、办理或退出日期用于时点审查；不直接作为住户使用习惯或预测特征。'
            elif source=='iflex' and field in ('q16b6.3','q16bN3','q16b1_3','q16b2_3','q16b3_3','q16b4_3','q16b5_3.1'):
                assert n==0
                disposition='no_answer_in_retained_cohort';reason='第三辆电动车的后续问题；保留家庭最多报告两辆，当前无回答，不虚构第三辆车。'
            else:raise AssertionError(('unaccounted_source_field',source,field))
            inventory.append({'source':source,'field':field,'households':len(records),'non_missing_answers':n,
                'disposition':disposition,'input_destination':'; '.join(paths),
                'raw_destination':'metadata.profile_provenance.raw_answers.'+field,'reason':reason})
        assert len(inventory)==(46 if source=='sgsc' else 96)
        with (ROOT/'provenance'/f'{source}_extraction_inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(inventory[0]),lineterminator='\n');w.writeheader();w.writerows(inventory)
        # Check the full device list in both files, not a selection of old columns.
        for kind in ('households','events'):
            with (ROOT/'tables'/f'{source}_{kind}.csv').open(encoding='utf-8-sig',newline='') as f:
                for row in csv.DictReader(f):
                    p=records[row['household_id']]['input']['profile']
                    assert json.loads(row['profile_appliances'])==p['appliances']
                    for k in ('household','meter_configuration'):
                        if k in p:assert json.loads(row['profile_'+k])==p[k]
                    if 'region' in p:assert row['profile_region']==p['region']
        report['sources'][source]={'households':len(records),'source_columns':len(inventory),
            'field_disposition_counts':dict(Counter(r['disposition'] for r in inventory)),
            'unaccounted_columns':[], 'complete_appliance_list_in_household_and_event_tables':True,
            'provenance_only_with_answers':[r['field'] for r in inventory if r['disposition']=='provenance_only' and r['non_missing_answers']]}
    report['passed']=True
    (ROOT/'provenance/extraction_completeness.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
