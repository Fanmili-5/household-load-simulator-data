"""Source-grounded corrections on top of the immutable 1.0 observation mapping."""
import copy

VERSION = 'household-benchmark/1.0.0'


def correct_profile(record):
    result = copy.deepcopy(record)
    result['schema_version'] = VERSION
    p, meta = result['profile'], result['metadata']
    raw = meta['source_profile_provenance']['raw_answers']
    corrections = []
    if result['source'] == 'iflex' and raw['q16_bil'] == 'No':
        # A skipped branch is not new evidence of an unknown vehicle. Fail on conflicts.
        assert raw['q16_bil_a.1'] in ('NA', '', '0')
        assert raw['q16_bil_b'] in ('NA', '', 'No')
        assert raw['q16.1'] in ('NA', '', '0')
        for k, value in raw.items():
            if k.startswith('q16b'): assert value in ('NA', '', '-')
        p['household']['car_count'] = 0
        d = next(d for d in p['appliances'] if d['type'] == 'electric_or_plugin_hybrid_vehicle')
        d.update(present=False, count=0)
        p['vehicle_details'] = []
        for path in ('household.car_count', 'appliances.electric_or_plugin_hybrid_vehicle', 'vehicle_details'):
            meta['field_evidence'][path] = {
                'source_fields': ['q16_bil', 'q16_bil_a.1', 'q16_bil_b', 'q16.1'],
                'transformation': 'explicit_no_household_car_and_empty_vehicle_branch_implies_zero_cars_including_electric_cars',
                'value_state': 'logically_derived_from_same_household_answer',
                'availability': 'survey1_recruitment_protocol_individual_timestamp_unavailable'}
            corrections.append(path)
    meta['benchmark_corrections'] = corrections
    return result
