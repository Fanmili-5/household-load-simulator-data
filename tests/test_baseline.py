"""Regression tests for lossy or scientifically misleading baseline mappings."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from baseline_profile import map_profile, band, category, CATALOG
from baseline_contract import PROFILE, SAMPLE, validate
from verify_baseline import check_semantics


def original(source):
    file = 'sgsc_single_observation.json' if source == 'sgsc' else 'iflex_observation.json'
    return json.loads((ROOT / 'examples' / file).read_text())


class ProfileTests(unittest.TestCase):
    def test_same_required_categories_despite_missing_inventory(self):
        profiles = [map_profile(original(s))[0] for s in ('sgsc', 'iflex')]
        self.assertEqual(set(profiles[0]), set(profiles[1]))
        for profile in profiles:
            validate(profile, PROFILE)
            self.assertEqual([a['type'] for a in profile['appliances']], list(CATALOG))
        fridge = next(a for a in profiles[1]['appliances'] if a['type'] == 'refrigerator')
        self.assertIsNone(fridge['present'])
        self.assertIsNone(fridge['count'])

    def test_no_dryer_use_is_not_no_dryer(self):
        row = original('sgsc')
        row['metadata']['profile_provenance']['raw_answers']['DRYER_USAGE_CD'] = 'NONE'
        row['input']['profile']['usage_habits']['dryer_usage_level'] = 'NONE'
        p, _ = map_profile(row)
        d = next(x for x in p['appliances'] if x['type'] == 'clothes_dryer')
        self.assertIsNone(d['present'])
        self.assertIsNone(d['count'])
        self.assertEqual(next(x['value'] for x in p['usage_habits'] if x['subject_id'] == 'clothes_dryer'), 'none')

    def test_no_pool_pump_is_explicit_zero(self):
        row = original('sgsc')
        row['metadata']['profile_provenance']['raw_answers']['HAS_POOLPUMP'] = 'N'
        p, _ = map_profile(row)
        d = next(x for x in p['appliances'] if x['type'] == 'pool_pump')
        self.assertEqual((d['present'], d['count']), (False, 0))

    def test_heat_pump_and_geothermal_do_not_create_two_counts(self):
        row = original('iflex')
        raw = row['metadata']['profile_provenance']['raw_answers']
        raw.update(q9N3='Main heat source', q9N4='Additional heat source', q14='Heat pump')
        p, _ = map_profile(row)
        pump = next(x for x in p['appliances'] if x['type'] == 'heat_pump')
        self.assertTrue(pump['present'])
        self.assertIsNone(pump['count'])
        geo = next(x for x in p['energy_services']['space_heating']['options'] if x['technology'] == 'geothermal')
        self.assertIsNone(geo['device_type_ref'])

    def test_income_below_threshold_remains_exclusive(self):
        result = band('Below NOK 300 000', 'income')
        self.assertEqual(result['upper'], 300000)
        self.assertIs(result['upper_inclusive'], False)
        self.assertIsNone(result['lower'])

    def test_open_ended_ranges_do_not_invent_upper_bound(self):
        self.assertEqual(band('160 m2 or larger', 'area')['lower'], 160)
        self.assertIsNone(band('160 m2 or larger', 'area')['upper'])
        self.assertEqual(band('1900 or earlier', 'year')['upper'], 1900)
        self.assertEqual(band('NOK 500 000 -799 999', 'income')['upper'], 799999)

    def test_ventilation_unknown_and_placeholder_are_not_equipment(self):
        self.assertIsNone(category(['0', "What air ventilation system do you have in your home? Don't know"]))

    def test_contact_permission_stays_outside_profile(self):
        p, meta = map_profile(original('sgsc'))
        self.assertNotIn('agreed_to_sms_contact', json.dumps(p))
        self.assertIn('agreed_to_sms_contact', meta['administrative'])

    def test_schema_rejects_missing_field_and_boolean_count(self):
        p, _ = map_profile(original('sgsc'))
        broken = copy.deepcopy(p)
        del broken['dwelling']
        with self.assertRaises(AssertionError): validate(broken, PROFILE)
        p['household']['resident_count'] = True
        with self.assertRaises(AssertionError): validate(p, PROFILE)

    def test_time_shift_and_truncated_curve_are_rejected(self):
        p = json.loads((ROOT / 'baseline/v1/examples/sgsc.json').read_text())
        p['input']['history']['end'] = '2013-01-16T23:30:00'
        with self.assertRaises(AssertionError): check_semantics(p)
        p = json.loads((ROOT / 'baseline/v1/examples/sgsc.json').read_text())
        p['output']['energy_kwh'].pop()
        with self.assertRaises(AssertionError): check_semantics(p)


if __name__ == '__main__': unittest.main()
