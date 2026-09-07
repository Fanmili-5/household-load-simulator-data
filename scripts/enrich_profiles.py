"""Restore same-household questionnaire information without changing measured curves."""
import copy
import csv
import hashlib
from pathlib import Path

AGE_BANDS = ('0_1','2_5','6_15','16_22','23_29','30_39','40_49','50_66','67_plus')
LIFE_STATES = ('school_or_kindergarten','student','part_time_work','full_time_work',
               'unemployed_or_not_in_education','retired','other')
EMPTY = {'','NA','NaN','nan'}
UNKNOWN = {"Don't know","Unsure / don't know"}
DECLINED = {"Don't want to answer"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Answers:
    def __init__(self, raw):
        self.raw=raw
        self.status={}
        self.fields={}
        self.flags=[]

    def get(self, key, path, mode='text'):
        self.fields[path]=key
        if key is None or key not in self.raw:
            self.status[path]='not_collected_in_this_source';return None
        value=self.raw[key]
        if value in EMPTY:
            self.status[path]='source_missing_or_not_applicable';return None
        if value in UNKNOWN:
            self.status[path]='explicit_unknown';return None
        if value in DECLINED:
            self.status[path]='declined';return None
        if value=='-':
            self.status[path]='source_placeholder';return None
        if mode=='bool':
            if value not in ('Yes','No','Y','N'):
                self.status[path]='unmapped_answer';return None
            value=value in ('Yes','Y')
        elif mode in ('int','float','people'):
            try:
                parsed=float(value.split()[0] if mode=='people' else value)
                if parsed<0 or (mode in ('int','people') and not parsed.is_integer()):raise ValueError(value)
                value=int(parsed) if mode in ('int','people') else parsed
            except (ValueError,TypeError):
                self.status[path]='invalid_numeric_answer';return None
        self.status[path]='source_answer'
        return value

    def multi(self, keys, path):
        values=[self.get(k,path+'.'+k) for k in keys]
        return [v for v in values if v is not None] or None


def enrich(old_profile, raw, source):
    p=copy.deepcopy(old_profile)
    a=Answers(raw)
    is_iflex=source=='iflex'
    def g(path, iflex=None, sgsc=None, mode='text'):
        return a.get(iflex if is_iflex else sgsc,path,mode)
    p['profile_schema_version']='household-baseline-profile/2'
    people={
        'household_size':g('people.household_size','q19',mode='people'),
        'household_type':g('people.household_type','husstand'),
        'survey_sex_answer':g('people.survey_sex_answer','q_kjonn'),
        'highest_household_education':g('people.highest_household_education','q21'),
        'gross_household_income_band':g('people.gross_household_income_band','q22'),
        'age_group_counts':None,'life_status_counts':None,
    }
    if is_iflex:
        n=people['household_size']
        age={band:a.get(f'q20.{i}',f'people.age_group_counts.{band}','int') for i,band in enumerate(AGE_BANDS,1)}
        invalid=any(v is None or v>n for v in age.values()) or sum(v or 0 for v in age.values())!=n
        if invalid:
            a.flags.append('age_distribution_inconsistent_with_household_size')
            a.status['people.age_group_counts']='invalid_distribution_raw_retained'
        else:people['age_group_counts']=age
        life={name:a.get(f'q24.{i}',f'people.life_status_counts.{name}','int') for i,name in enumerate(LIFE_STATES,1)}
        for name,v in life.items():
            if v is not None and v>n:
                life[name]=None
                a.status['people.life_status_counts.'+name]='invalid_count_exceeds_household_size'
                a.flags.append('life_status_count_exceeds_household_size')
        people['life_status_counts']=life
    else:
        a.get(None,'people.age_group_counts');a.get(None,'people.life_status_counts')
    p['people']=people
    p['dwelling']={
        'type':g('dwelling.type','q4','DWELLING_TYPE_CD'),
        'floor_area_band_m2':g('dwelling.floor_area_band_m2','q5'),
        'owner_occupied':g('dwelling.owner_occupied','q6',mode='bool'),
        'construction_year_band':g('dwelling.construction_year_band','q7'),
        'energy_renovation_reported':g('dwelling.energy_renovation_reported','q8',mode='bool'),
        'rental_unit_present':g('dwelling.rental_unit_present','q6b1',mode='bool'),
        'rental_unit_separate_meter':g('dwelling.rental_unit_separate_meter','q6b2',mode='bool'),
        'shared_flat':g('dwelling.shared_flat','q6c',mode='bool'),
        'heated_room_count':g('dwelling.heated_room_count',sgsc='NUM_ROOMS_HEATED',mode='int'),
    }
    p['preferences']={'living_room_comfort_temperature_celsius':g('preferences.living_room_comfort_temperature_celsius','q10',mode='float')}
    p['usage_habits']={
        'daytime_home':g('usage_habits.daytime_home','q23','IS_HOME_DURING_DAYTIME',mode='bool'),
        'daytime_home_scope':'weekday_daytime' if is_iflex else 'daytime_days_unspecified',
        'lower_temperature_in_less_used_rooms':g('usage_habits.lower_temperature_in_less_used_rooms','q11',mode='bool'),
        'reduce_temperature_at_night_or_away':g('usage_habits.reduce_temperature_at_night_or_away','q12',mode='bool'),
        'heating_control':g('usage_habits.heating_control','q13'),
        'water_heater_control':g('usage_habits.water_heater_control','q14b'),
        'dryer_usage_level':g('usage_habits.dryer_usage_level',sgsc='DRYER_USAGE_CD'),
        'wood_stove_use_answers':a.multi([f'q9d{i}' for i in range(1,5)],'usage_habits.wood_stove_use_answers') if is_iflex else None,
    }
    p['energy_attitudes']={
        'reported_electricity_reduction_effort':g('energy_attitudes.reported_electricity_reduction_effort',sgsc='REDUCING_CONSUMPTION_CD'),
        'follows_electricity_use':g('energy_attitudes.follows_electricity_use','q_ekstra_a',mode='bool'),
        'follows_electricity_prices':g('energy_attitudes.follows_electricity_prices','q_ekstra_c',mode='bool'),
        'internet_access':g('energy_attitudes.internet_access',sgsc='HAS_INTERNET_ACCESS',mode='bool'),
        'use_information_channels':a.multi([f'q_ekstra_b_{i}' for i in range(1,5)],'energy_attitudes.use_information_channels') if is_iflex else None,
        'price_information_channels':a.multi([f'q_ekstra_d_{i}' for i in range(1,6)],'energy_attitudes.price_information_channels') if is_iflex else None,
    }
    p['energy_systems']={
        'electricity_contract':g('energy_systems.electricity_contract','q2'),
        'respondent_receives_bill':g('energy_systems.respondent_receives_bill','q1',mode='bool'),
        'renewable_electricity_contract':g('energy_systems.renewable_electricity_contract','q3',mode='bool'),
        'hot_water_arrangement':g('energy_systems.hot_water_arrangement','q14'),
        'ventilation_answers':a.multi([f'q15_{i}' for i in range(1,5)],'energy_systems.ventilation_answers') if is_iflex else None,
    }
    for name,field in [('gas_available','HAS_GAS'),('gas_heating','HAS_GAS_HEATING'),('gas_hot_water','HAS_GAS_HOT_WATER'),('gas_cooking','HAS_GAS_COOKING'),('gas_other_appliance','HAS_GAS_OTHER_APPLIANCE')]:
        p['energy_systems'][name]=g('energy_systems.'+name,sgsc=field,mode='bool')
    p['vehicles']={
        'car_present':g('vehicles.car_present','q16_bil',mode='bool'),
        'car_count':g('vehicles.car_count','q16_bil_a.1',mode='int'),
        'electric_or_plugin_hybrid_present':g('vehicles.electric_or_plugin_hybrid_present','q16_bil_b',mode='bool'),
        'electric_or_plugin_hybrid_count':g('vehicles.electric_or_plugin_hybrid_count','q16.1',mode='int'),
        'electric_or_plugin_hybrid_details':None,
    }
    if is_iflex:
        count=p['vehicles']['electric_or_plugin_hybrid_count']
        if count is not None or p['vehicles']['electric_or_plugin_hybrid_present'] is False:
            p['vehicles']['electric_or_plugin_hybrid_details']=[]
        for i in range(1,(min(count,3) if count is not None else 0)+1):
            stem=f'vehicles.electric_or_plugin_hybrid_details.{i}'
            detail={'vehicle_number':i}
            for name,field,mode in [
                ('electric_range_km',f'q16b6.{i}','float'),('usual_charging_location',f'q16bN{i}','text'),
                ('home_charging_method',f'q16b1_{i}','text'),('home_charging_frequency',f'q16b2_{i}','text'),
                ('usual_charging_time',f'q16b3_{i}','text'),('charging_control',f'q16b4_{i}','text'),
                ('distance_before_charging_km',f'q16b5_{i}.1','float')]:
                detail[name]=a.get(field,stem+'.'+name,mode)
            p['vehicles']['electric_or_plugin_hybrid_details'].append(detail)
        for device in p['appliances']:
            if device['appliance']=='electric_or_plugin_hybrid_car':device['count']=count
            if device['appliance'] in ('panel_heater','electric_underfloor_heating','heat_pump'):
                device['heating_use']={'Main heat source':'main','Additional heat source':'additional','No':'not_used'}.get(device['source_value'])
        for i,name in enumerate(('geothermal_heating','fireplace_or_wood_stove','oil_paraffin_gas_bio_heater','district_or_shared_heating','other_heating'),4):
            field=f'q9N{i}';answer=raw[field]
            p['appliances'].append({'appliance':name,'present':True if answer in ('Main heat source','Additional heat source') else None,
                'count':None,'source_field':field,'source_value':answer,
                'heating_use':{'Main heat source':'main','Additional heat source':'additional','No':'not_used'}.get(answer)})
    provenance={'raw_answers':dict(raw),'field_sources':a.fields,'field_status':a.status,'quality_flags':a.flags,
        'source_stage':'Survey 1, retained Phase 1 cohort' if is_iflex else 'SGSC customer household record',
        'individual_questionnaire_timestamp':None,
        'timing_status':'exact field acquisition times not established; review before SFT',
        'not_model_input':True}
    if not is_iflex:
        provenance['recorded_dates']={k:v for k,v in raw.items() if k.endswith('_DATE')}
        provenance['inferred_fields_not_new_model_features']={k:v for k,v in raw.items() if k.startswith(('ASSRTD_','INFERRED_','VERIFIED_'))}
    return p,provenance


class ProfileSources:
    def __init__(self, pipeline_root, sgsc_households, groups):
        survey=pipeline_root/'runs/iflex_all_candidates_v1/source_stage/raw/survey1_answers.csv'
        with survey.open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.iflex={r['ID']:(i,r) for i,r in enumerate(rows,2)}
        assert len(self.iflex)==len(rows)
        needed={g['profile_csv_record_number'] for g in groups.values() if g['new_evidence_group']!='unresolved_conflict_or_missing_boundary'}
        with sgsc_households.open(encoding='utf-8-sig') as f:
            self.sgsc={i:r for i,r in enumerate(csv.DictReader(f),2) if i in needed}
        assert set(self.sgsc)==needed
        self.files={'sgsc':{'filename':sgsc_households.name,'sha256':sha(sgsc_households)},
                    'iflex':{'filename':survey.name,'sha256':sha(survey)}}

    def apply(self, r, evidence):
        if r['source']=='sgsc':
            line=evidence['profile_csv_record_number'];raw=self.sgsc[line]
            assert raw['CUSTOMER_KEY']==r['household_id']
            assert raw==r['provenance']['raw_profile'],r['sample_id']
        else:
            line,raw=self.iflex[r['household_id']]
            assert raw['ID']==r['household_id']
        profile,provenance=enrich(r['input']['profile'],raw,r['source'])
        provenance.update(self.files[r['source']]);provenance['csv_record_number_including_header']=line
        return profile,provenance
