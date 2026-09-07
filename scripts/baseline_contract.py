"""Frozen JSON Schema contract and dependency-free validation of its used keywords."""
import math
from baseline_profile import VERSION, CATALOG, AGE_BANDS, LIFE_STATES


def scalar(kind, description, nullable=True, **extra):
    return dict(type=[kind, 'null'] if nullable else kind, description=description, **extra)


def obj(properties, description=''):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False, description=description)


def array(items, description='', nullable=False, **extra):
    return dict(type=['array', 'null'] if nullable else 'array', items=items, description=description, **extra)


def string(desc): return scalar('string', desc)
def boolean(desc): return scalar('boolean', desc)
def count(desc): return scalar('integer', desc, minimum=0)
def number(desc): return scalar('number', desc, minimum=0)
def rng(desc): return obj({'lower': count('Lower boundary printed in source category; null if unknown/unbounded'),
                           'upper': count('Upper boundary printed in source category; null if unknown/unbounded'),
                           'lower_inclusive': boolean('Inclusion of recorded lower boundary'),
                           'upper_inclusive': boolean('Inclusion of upper boundary; below a threshold is exclusive')}, desc)


DEVICE = obj({'type': scalar('string', 'Device category; categories may overlap, never sum to a household total', False, enum=list(CATALOG)),
              'present': boolean('Reported ownership or presence logically implied by use; nonuse is not absence'),
              'count': count('Physical count within category; 0 may be derived from explicit absence'),
              'subtype': string('Recorded subtype'), 'rated_power_w': number('Recorded rated power, watts'),
              'capacity_kw': number('Recorded generation capacity, kW'),
              'capacity_kwh': number('Recorded storage capacity, kWh')})
VEHICLE = obj({'vehicle_number': scalar('integer', 'Within-household source vehicle number', False, minimum=1, maximum=3),
               'device_type_ref': scalar('string', 'Device category reference', False, const='electric_or_plugin_hybrid_vehicle'),
               'electric_range_km': number('Reported range, km'),
               'usual_charging_location': string('Reported usual location and relationship to household meter'),
               'home_charging_method': string('Reported charger category; encoded source specification, not corrected or estimated power'),
               'home_charging_frequency': string('Reported frequency category, not a synthesized number of sessions'),
               'usual_charging_time': string('Usual time band, not event-day schedule'),
               'charging_control': string('Reported control mode'),
               'distance_before_charging_km': number('Reported distance driven between charging, km')})
HABIT = obj({'subject_type': scalar('string', 'Type of subject', False, enum=['household', 'energy_service', 'appliance_category']),
             'subject_id': scalar('string', 'Self, service key or device category', False),
             'behavior': scalar('string', 'Defined behavior identifier', False),
             'value': {'type': ['boolean', 'string', 'array', 'null'], 'items': {'type': 'string'},
                       'description': 'Reported state/category/categories; null unknown'},
             'unit': string('Unit if present; categorical and boolean habits use null'),
             'time_scope': scalar('string', 'Scope of general habit', False, enum=['usual', 'weekday_daytime'])})
PROFILE = obj({
    'household': obj({
        'resident_count': count('Number of household residents'), 'composition': string('Household composition category'),
        'respondent_sex': string('Questionnaire respondent sex; not all household members'),
        'highest_household_education': string('Highest completed education in the household'),
        'gross_income_band': obj({**rng('')['properties'], 'currency': string('Source currency'),
                                 'period': string('Income period; source question does not establish it here')}, 'Gross pretax household income band'),
        'age_group_counts': obj({x: count('Residents in source age band ' + x) for x in AGE_BANDS}, 'Invalid age distribution is all null'),
        'life_status_counts': obj({x: count('Residents reporting status ' + x) for x in LIFE_STATES}, 'Statuses can overlap; do not sum as resident count'),
        'car_present': boolean('Any car, not only electric'), 'car_count': count('All cars'), 'internet_access': boolean('Household internet access')}),
    'dwelling': obj({
        'type': string('Self-reported dwelling type'), 'owner_occupied': boolean('Owner-occupied dwelling'),
        'energy_renovation_reported': boolean('Energy renovation reported'),
        'rental_unit_present': boolean('Rental unit in dwelling'), 'rental_unit_separate_meter': boolean('Rental unit has separate meter'),
        'shared_flat': boolean('Shared flat reported'), 'heated_room_count': count('Heated rooms; never an appliance count'),
        'floor_area_m2': rng('Source floor-area band, square metres'), 'construction_year': rng('Source construction-year band'),
        'source_classified_type': string('Source-assigned broad type; distinct from respondent answer'),
        'climate_zone': string('Source climate classification')}),
    'appliances': array(DEVICE, 'One entry per fixed category in catalog order', minItems=len(CATALOG), maxItems=len(CATALOG)),
    'energy_services': obj({
        'space_heating': obj({'gas_used': boolean('Gas used for space heating'),
            'options': array(obj({'technology': scalar('string', 'Heating technology', False),
                                  'device_type_ref': string('Associated category when known; geothermal/shared systems do not add device counts'),
                                  'role': string('main, additional or not_used; not_used does not mean not_owned')}), nullable=True)}),
        'hot_water': obj({'gas_used': boolean('Gas used for water heating'), 'technology': string('Reported hot-water arrangement')}),
        'cooking': obj({'gas_used': boolean('Gas used for cooking')}),
        'other_gas_use': obj({'gas_used': boolean('Other gas appliance use; no inferred device count')}),
        'ventilation': obj({'technologies': array({'type': 'string'}, 'Reported technologies; null unknown', nullable=True)}),
        'supply': obj({'gas_available': boolean('Gas available'), 'electricity_contract': string('Retail contract category'),
                       'respondent_receives_bill': boolean('Respondent receives household electricity bill'),
                       'renewable_electricity_contract': boolean('Renewable electricity contract'),
                       'battery_connected_to_pv': boolean('Battery linked to PV only; not all storage ownership'),
                       'farm_or_business_shares_meter': boolean('Farm/business on same meter')})}),
    'usage_habits': array(HABIT, 'Fixed seven household/device/service habit definitions', minItems=7, maxItems=7),
    'preferences': obj({
        'living_room_comfort_temperature_c': scalar('number', 'Reported comfortable living-room temperature, not measured temperature or control bound'),
        'reported_electricity_reduction_effort': string('Reported effort category'),
        'follows_electricity_use': boolean('Reports following electricity consumption'),
        'follows_electricity_prices': boolean('Reports following electricity prices'),
        'use_information_channels': array({'type': 'string'}, 'Consumption information channels', nullable=True),
        'price_information_channels': array({'type': 'string'}, 'Price information channels', nullable=True)}),
    'vehicle_details': array(VEHICLE, 'Reported electric/plugin-hybrid vehicles; null unestablished, [] confirmed no such vehicles', nullable=True)
}, 'Semantic household profile. Every named field is required; source gaps are null, never invented.')

SERIES = array(scalar('number', 'Interval energy', False, minimum=0))
HISTORY = obj({'start': scalar('string', 'First interval start on source clock', False),
               'end': scalar('string', 'Last interval end = forecast origin', False),
               'interval_minutes': scalar('integer', 'Native interval duration', False, enum=[30, 60]),
               'unit': scalar('string', 'Interval energy unit', False, const='kWh'), 'energy_kwh': SERIES})
EVENT = obj({'start': scalar('string', 'Event start', False), 'end': scalar('string', 'Event end', False),
             'type': scalar('string', 'Meaning of source event', False, enum=['peak_price_penalty', 'reduction_reward', 'experimental_price_for_reward_calculation']),
             'currency': scalar('string', 'Signal currency', False, enum=['AUD', 'NOK']),
             'price_per_kwh': array(scalar('number', 'Source price, may be negative', False), nullable=True),
             'price_interval_minutes': count('Price signal interval minutes'), 'rate_per_reduced_kwh': number('Verified reduction reward, unknown if not verified')})
CONTEXT = obj({'forecast_origin': scalar('string', 'Prediction time on source clock', False),
               'target_window': obj({'start': scalar('string', 'Inclusive first interval start', False),
                                      'end': scalar('string', 'Exclusive end', False),
                                      'horizon_hours': scalar('integer', 'Source-clock day', False, const=24),
                                      'interval_minutes': scalar('integer', 'Native interval duration', False, enum=[30, 60])}),
               'country': scalar('string', 'Source country', False, enum=['AU', 'NO']), 'region': string('Source region, if available'),
               'time_basis': scalar('string', 'Clock semantics; no unverified timezone conversion', False, const='source_clock_intervals_no_utc_conversion'),
               'measurement_scope': scalar('string', 'Meter coverage of both history and answer', False),
               'events': array(EVENT, 'All retained same-household events on target day', minItems=1)})
SAMPLE = obj({'schema_version': scalar('string', 'Frozen baseline version', False, const=VERSION),
              'sample_id': scalar('string', 'Household-day key; not model input', False),
              'input': obj({'profile': PROFILE, 'history': HISTORY, 'context': CONTEXT}),
              'output': obj({'energy_kwh': SERIES}),
              'metadata': {'type': 'object', 'description': 'Traceability and readiness outside model input'}})


def validate(value, schema, path='$'):
    """Validate exactly the JSON Schema keywords emitted above; fail closed on input values."""
    types = schema.get('type', [])
    types = [types] if isinstance(types, str) else types
    actual = ('null' if value is None else 'boolean' if isinstance(value, bool) else
              'integer' if isinstance(value, int) else 'number' if isinstance(value, float) else
              'string' if isinstance(value, str) else 'array' if isinstance(value, list) else
              'object' if isinstance(value, dict) else 'unsupported')
    assert not types or actual in types or (actual == 'integer' and 'number' in types), (path, actual, types)
    if 'const' in schema: assert value == schema['const'], path
    if 'enum' in schema: assert value in schema['enum'], path
    if actual in ('number', 'integer'):
        assert math.isfinite(value), path
        if 'minimum' in schema: assert value >= schema['minimum'], path
        if 'maximum' in schema: assert value <= schema['maximum'], path
    if actual == 'object':
        assert set(schema.get('required', [])) <= value.keys(), path
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False: assert value.keys() <= props.keys(), path
        for k, v in value.items():
            if k in props: validate(v, props[k], path + '.' + k)
    if actual == 'array':
        assert len(value) >= schema.get('minItems', 0), path
        assert len(value) <= schema.get('maxItems', float('inf')), path
        for i, v in enumerate(value): validate(v, schema.get('items', {}), path + '[' + str(i) + ']')


def document(schema, name):
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            '$id': 'https://github.com/Fanmili-5/household-load-simulator-data/baseline/v1/schema/' + name,
            'title': VERSION + ' ' + name, **schema}
