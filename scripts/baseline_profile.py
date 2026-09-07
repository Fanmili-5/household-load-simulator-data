"""Version 1.0.0 semantic household mapping. Sources are observations, never another household."""
import copy
import re

VERSION = 'household-baseline/1.0.0'
CATALOG = ('refrigerator', 'freezer', 'washing_machine', 'dishwasher', 'clothes_dryer',
           'air_conditioner', 'panel_heater', 'electric_underfloor_heating', 'heat_pump',
           'electric_water_heater', 'fireplace_or_wood_stove', 'fuel_heater', 'pool_pump',
           'electric_or_plugin_hybrid_vehicle', 'solar_pv', 'battery_storage',
           'mechanical_ventilation', 'electric_cooking_appliance', 'television', 'lighting')
AGE_BANDS = ('0_1', '2_5', '6_15', '16_22', '23_29', '30_39', '40_49', '50_66', '67_plus')
LIFE_STATES = ('school_or_kindergarten', 'student', 'part_time_work', 'full_time_work',
               'unemployed_or_not_in_education', 'retired', 'other')
CATEGORY_MAP = {
    'SeparateHouse': 'detached_house', 'Detached house': 'detached_house',
    'SemiDetached': 'semi_detached_house', 'Semi-detached house': 'semi_detached_house',
    'Unit': 'apartment', 'Apartment block': 'apartment', 'NotUnit': 'not_apartment',
    'Townhouses, chain houses and other small houses with 3 homes or more': 'terraced_or_linked_housing',
    'Other type of building': 'other', 'SplitSystem': 'split_system', 'Ducted': 'ducted',
    'HI': 'high', 'MED': 'medium', 'LOW': 'low', 'NONE': 'none',
    'No': 'none', 'Yes, manually': 'manual',
    'Yes, manually (turn on and off panel heaters, regulate temperature on thermostats, etc.)': 'manual',
    'Yes, automated by time': 'time_scheduled',
    'Yes, automated by time (set schedule in thermostat)': 'time_scheduled',
    'Yes, automated by price (advanced control based on spot price for electricity)': 'price_based',
    'Spot price / Hourly spot': 'hourly_spot', 'Fixed price': 'fixed_price', 'Variable price': 'variable_price',
    'Primary school (up to 10 years of schooling)': 'primary',
    'High school / High school level (11-13 years of schooling)': 'secondary',
    'College / University, undergraduate degree (1-3 years)': 'university_undergraduate',
    'College / University, higher degree (4 years or more)': 'university_higher_degree',
    'Natural ventilation (ventilation via windows and air vents)': 'natural_ventilation',
    'Mechanical ventilation manually controlled': 'manual_mechanical_ventilation',
    'Balanced ventilation system with heat recovery': 'balanced_heat_recovery_ventilation',
    'Own electric water heater': 'separate_electric_water_heater',
    'Shared water heater or district heating': 'shared_water_heater_or_district_heating',
    'Heat pump': 'heat_pump', 'Main heat source': 'main', 'Additional heat source': 'additional',
}
UNKNOWN = {None, '', '-', 'NA', '0', "Don't know", "Unsure / don't know", "Don't want to answer"}


def category(value):
    if isinstance(value, list):
        return [v for v in (category(x) for x in value) if v is not None] or None
    if value in UNKNOWN:
        return None
    value = value.removeprefix('What air ventilation system do you have in your home? ')
    if value in UNKNOWN:
        return None
    return CATEGORY_MAP.get(value, re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_'))


def band(value, kind):
    result = {'lower': None, 'upper': None, 'lower_inclusive': None, 'upper_inclusive': None}
    if value is None:
        return result
    v = value.replace('NOK', '').replace('m2', '')
    # Separators within income values denote thousands, not separate endpoints.
    if kind == 'income':
        v = re.sub(r'(?<=\d)\s+(?=\d)', '', v)
    numbers = [int(x) for x in re.findall(r'\d+', v)]
    if len(numbers) == 2:
        result.update(lower=numbers[0], upper=numbers[1], lower_inclusive=True, upper_inclusive=True)
    elif len(numbers) == 1:
        if 'Below' in v:
            result.update(upper=numbers[0], upper_inclusive=False)
        elif 'earlier' in v:
            result.update(upper=numbers[0], upper_inclusive=True)
        else:
            result.update(lower=numbers[0], lower_inclusive=True)
    else:
        raise ValueError('Unsupported range: ' + value)
    return result


def get(obj, path):
    for key in path.split('.'):
        if obj is None or not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


class Mapping:
    def __init__(self, row):
        self.row = row
        self.profile = row['input']['profile']
        self.provenance = row['metadata']['profile_provenance']
        self.evidence = {}

    def value(self, destination, original, transform=None):
        value = copy.deepcopy(get(self.profile, original))
        related = {k: v for k, v in self.provenance['field_sources'].items()
                   if k == original or k.startswith(original + '.')}
        states = {k: v for k, v in self.provenance['field_status'].items()
                  if k == original or k.startswith(original + '.')}
        self.evidence[destination] = {
            'observation_profile_paths': [original], 'source_fields': sorted(set(v for v in related.values() if v)),
            'source_status': states, 'transformation': transform.__name__ if transform else 'preserve_typed_value',
            'availability': 'individual_acquisition_time_unverified'}
        transformed = transform(value) if transform else value
        self.evidence[destination]['value_state'] = ('unknown_after_category_normalization' if value is not None and transformed is None
                                                     else 'unknown_or_invalid_in_source' if transformed is None else 'mapped_value')
        return transformed

    def raw(self, destination, fields, rule):
        self.evidence[destination] = {
            'observation_profile_paths': [], 'source_fields': fields, 'source_status': {},
            'transformation': rule, 'availability': 'individual_acquisition_time_unverified'}


def map_profile(row):
    m = Mapping(row)
    p = m.profile
    raw = m.provenance['raw_answers']
    source = row['source']
    v = m.value
    household = {}
    for dest, original, transform in [
        ('resident_count', 'household_size', None), ('composition', 'household_type', category),
        ('respondent_sex', 'survey_sex_answer', category),
        ('highest_household_education', 'highest_household_education', category)]:
        household[dest] = v('household.' + dest, 'people.' + original, transform)
    income = v('household.gross_income_band', 'people.gross_household_income_band')
    household['gross_income_band'] = {**band(income, 'income'), 'currency': 'NOK' if source == 'iflex' else None, 'period': None}
    m.evidence['household.gross_income_band']['transformation'] = 'parse_recorded_bounds_keep_open_boundary_period_unverified'
    for dest, names in [('age_group_counts', AGE_BANDS), ('life_status_counts', LIFE_STATES)]:
        counts = v('household.' + dest, 'people.' + dest)
        household[dest] = {name: counts.get(name) if counts else None for name in names}
    for dest, path in [('car_present', 'vehicles.car_present'), ('car_count', 'vehicles.car_count'),
                       ('internet_access', 'energy_attitudes.internet_access')]:
        household[dest] = v('household.' + dest, path)
    dwelling = {}
    for key in ('type', 'owner_occupied', 'energy_renovation_reported', 'rental_unit_present',
                'rental_unit_separate_meter', 'shared_flat', 'heated_room_count'):
        dwelling[key] = v('dwelling.' + key, 'dwelling.' + key, category if key == 'type' else None)
    for dest, old, kind in [('floor_area_m2', 'floor_area_band_m2', 'area'),
                            ('construction_year', 'construction_year_band', 'year')]:
        dwelling[dest] = band(v('dwelling.' + dest, 'dwelling.' + old), kind)
        m.evidence['dwelling.' + dest]['transformation'] = 'parse_recorded_band_bounds_no_midpoint_imputation'
    # Classified housing remains separate from the respondent's dwelling answer.
    dwelling['source_classified_type'] = category(p.get('household', {}).get('ASSRTD_DWELLING_TYPE_CD'))
    dwelling['climate_zone'] = category(p.get('household', {}).get('ASSRTD_CLIMATE_ZONE_DESC'))
    m.raw('dwelling.source_classified_type', ['ASSRTD_DWELLING_TYPE_CD'] if source == 'sgsc' else [], 'source_classification_not_self_report')
    m.raw('dwelling.climate_zone', ['ASSRTD_CLIMATE_ZONE_DESC'] if source == 'sgsc' else [], 'source_climate_classification')

    devices = {name: {'type': name, 'present': None, 'count': None, 'subtype': None,
                      'rated_power_w': None, 'capacity_kw': None, 'capacity_kwh': None} for name in CATALOG}
    for name in CATALOG:
        m.raw('appliances.' + name, [], 'not_collected_for_this_category')

    def device(name, fields, present=None, count=None, subtype=None, rule='direct_answer_or_logical_presence'):
        d = devices[name]
        if present is False and count is None:
            count = 0
        if count is not None and count > 0:
            present = True
        if present is False and count not in (None, 0):
            raise ValueError('Contradictory device presence/count')
        d.update(present=present, count=count, subtype=subtype)
        m.raw('appliances.' + name, fields, rule)

    heating_options = []
    if source == 'sgsc':
        device('refrigerator', ['NUM_REFRIGERATORS'], count=int(raw['NUM_REFRIGERATORS']))
        device('air_conditioner', ['HAS_AIRCON', 'AIRCON_TYPE_CD'],
               present={'Y': True, 'N': False}.get(raw['HAS_AIRCON']), subtype=category(raw['AIRCON_TYPE_CD']))
        device('clothes_dryer', ['DRYER_USAGE_CD'], present=True if raw['DRYER_USAGE_CD'] in ('HI', 'MED', 'LOW') else None,
               rule='reported_use_implies_presence_but_nonuse_does_not_imply_absence')
        device('pool_pump', ['HAS_POOLPUMP'], present={'Y': True, 'N': False}.get(raw['HAS_POOLPUMP']))
    else:
        technologies = [('electric_panel', 'panel_heater'), ('electric_underfloor', 'electric_underfloor_heating'),
                        ('heat_pump', 'heat_pump'), ('geothermal', None), ('wood_fire', 'fireplace_or_wood_stove'),
                        ('oil_paraffin_gas_or_bio', 'fuel_heater'), ('district_or_shared', None), ('other', None)]
        for i, (technology, device_ref) in enumerate(technologies, 1):
            field = 'q9N' + str(i)
            answer = raw[field]
            role = {'Main heat source': 'main', 'Additional heat source': 'additional', 'No': 'not_used'}.get(answer)
            heating_options.append({'technology': technology, 'device_type_ref': device_ref, 'role': role})
            if device_ref:
                device(device_ref, [field], present=True if role in ('main', 'additional') else None,
                       rule='heating_use_not_ownership_survey_no_means_not_used')
        m.raw('energy_services.space_heating.options', [f'q9N{i}' for i in range(1, 9)],
              'geothermal_and_district_supply_are_service_descriptions_not_additional_device_counts')
        water = raw['q14']
        if water == 'Own electric water heater':
            device('electric_water_heater', ['q14'], present=True, subtype='separate')
        elif water == 'Heat pump':
            device('heat_pump', sorted(set(m.evidence['appliances.heat_pump']['source_fields'] + ['q14'])), present=True,
                   rule='heat_pump_reported_for_heating_or_hot_water_do_not_sum_instances')
        device('electric_or_plugin_hybrid_vehicle', ['q16_bil_b', 'q16.1'],
               present=p['vehicles']['electric_or_plugin_hybrid_present'], count=p['vehicles']['electric_or_plugin_hybrid_count'])
        device('solar_pv', ['q17'], present=p['energy_systems']['solar_pv_present'])
        devices['solar_pv']['capacity_kw'] = p['energy_systems']['solar_pv_capacity_kw']
        m.raw('appliances.solar_pv.capacity_kw', ['q17b.1'], 'direct_capacity_kw')
        # PV-linked battery is not a whole-home battery ownership question.
        m.raw('appliances.battery_storage', ['q17c'], 'pv_linked_question_does_not_establish_all_storage_ownership')
        vent = category(p['energy_systems']['ventilation_answers'])
        if vent and any(x in vent for x in ('manual_mechanical_ventilation', 'balanced_heat_recovery_ventilation')):
            device('mechanical_ventilation', ['q15_1', 'q15_2', 'q15_3', 'q15_4'], present=True,
                   rule='reported_mechanical_ventilation_implies_presence_no_unreported_absence')

    services = {}
    for service, gas_path in [('space_heating', 'gas_heating'), ('hot_water', 'gas_hot_water'),
                              ('cooking', 'gas_cooking'), ('other_gas_use', 'gas_other_appliance')]:
        services[service] = {'gas_used': v('energy_services.' + service + '.gas_used', 'energy_systems.' + gas_path)}
    services['space_heating']['options'] = heating_options or None
    services['hot_water']['technology'] = v('energy_services.hot_water.technology', 'energy_systems.hot_water_arrangement', category)
    services['ventilation'] = {'technologies': v('energy_services.ventilation.technologies', 'energy_systems.ventilation_answers', category)}
    services['supply'] = {}
    for key in ('gas_available', 'electricity_contract', 'respondent_receives_bill', 'renewable_electricity_contract',
                'battery_connected_to_pv', 'farm_or_business_shares_meter'):
        services['supply'][key] = v('energy_services.supply.' + key, 'energy_systems.' + key,
                                   category if key == 'electricity_contract' else None)

    habits = []
    for subject, ref, behavior, path, transform, scope in [
        ('household', 'self', 'someone_home', 'daytime_home', None, 'weekday_daytime'),
        ('energy_service', 'space_heating', 'lower_temperature_in_less_used_rooms', 'lower_temperature_in_less_used_rooms', None, 'usual'),
        ('energy_service', 'space_heating', 'reduce_temperature_at_night_or_away', 'reduce_temperature_at_night_or_away', None, 'usual'),
        ('energy_service', 'space_heating', 'control_mode', 'heating_control', category, 'usual'),
        ('energy_service', 'hot_water', 'control_mode', 'water_heater_control', category, 'usual'),
        ('appliance_category', 'clothes_dryer', 'reported_use_level', 'dryer_usage_level', category, 'usual'),
        ('appliance_category', 'fireplace_or_wood_stove', 'reported_use_conditions', 'wood_stove_use_answers', category, 'usual')]:
        dest = 'usage_habits.' + ref + '.' + behavior
        habits.append({'subject_type': subject, 'subject_id': ref, 'behavior': behavior,
                       'value': v(dest, 'usage_habits.' + path, transform), 'unit': None, 'time_scope': scope})
    preferences = {'living_room_comfort_temperature_c': v('preferences.living_room_comfort_temperature_c',
                                                        'preferences.living_room_comfort_temperature_celsius')}
    for key in ('reported_electricity_reduction_effort', 'follows_electricity_use', 'follows_electricity_prices',
                'use_information_channels', 'price_information_channels'):
        preferences[key] = v('preferences.' + key, 'energy_attitudes.' + key,
                             None if key.startswith('follows_') else category)
    vehicle_details = v('vehicle_details', 'vehicles.electric_or_plugin_hybrid_details')
    if vehicle_details is not None:
        for d in vehicle_details:
            d['device_type_ref'] = 'electric_or_plugin_hybrid_vehicle'
            for key in ('usual_charging_location', 'home_charging_method', 'home_charging_frequency',
                        'usual_charging_time', 'charging_control'):
                d[key] = category(d[key])
    # SMS contact permission is administrative. It is explicitly accounted for, not a behavioural preference.
    m.raw('metadata.administrative.agreed_to_sms_contact', ['HAS_AGREED_TO_SMS'] if source == 'sgsc' else [], 'administrative_not_model_input')
    output = {'household': household, 'dwelling': dwelling, 'appliances': list(devices.values()),
              'energy_services': services, 'usage_habits': habits, 'preferences': preferences,
              'vehicle_details': vehicle_details}
    metadata = {'field_evidence': m.evidence,
                'source_profile_provenance': copy.deepcopy(m.provenance),
                'administrative': {'agreed_to_sms_contact': p['preferences']['agreed_to_sms_contact']},
                'known_limits': ['no_measured_appliance_trajectories', 'catalog_is_not_a_complete_source_inventory',
                                 'individual_profile_acquisition_time_unverified',
                                 'device_categories_may_overlap_no_total_appliance_count']}
    return output, metadata
