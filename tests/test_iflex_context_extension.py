"""Check forecast-time boundaries and post-survey separation."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_iflex_context_extension as ext


class ContextExtensionTests(unittest.TestCase):
    def setUp(self):
        self.sample = json.loads((ROOT / 'benchmark/v1/examples/iflex.json').read_text())
        self.sources = ext.DEFAULT / 'sources'
        self.dictionary = json.loads((self.sources / 'survey2_change_dictionary.json').read_text())

    def test_history_rejects_overlap_with_forecast(self):
        self.sample['input']['history']['end'] = '2020-02-11T01:00:00'
        with self.assertRaisesRegex(ValueError, 'history boundary'):
            ext.history_slots(self.sample)

    def test_missing_followup_is_not_no_change(self):
        self.assertEqual(ext.classify_followup(None, self.dictionary), ('followup_unavailable', []))
        row = dict.fromkeys(ext.FIELDS, 'NA')
        self.assertEqual(ext.classify_followup(row, self.dictionary), ('no_change_details_recorded', []))

    def test_ambiguous_no_checkbox_does_not_override_explicit_detail(self):
        row = dict.fromkeys(ext.FIELDS, '-')
        row['Aq1_1'] = 'No'
        row['Aq1_8'] = self.dictionary['Aq1_8']['answers'][0]
        self.assertEqual(ext.classify_followup(row, self.dictionary),
                         ('reported_change_detail', ['resident_count_change']))

    def test_unknown_answer_is_not_silently_accepted(self):
        row = dict.fromkeys(ext.FIELDS, 'NA')
        row['Aq1_3'] = 'unknown category'
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            ext.classify_followup(row, self.dictionary)

    def test_target_weather_and_followup_do_not_enter_input(self):
        before = copy.deepcopy(self.sample)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            sources = base / 'sources'
            sources.mkdir()
            for f in self.sources.iterdir():
                (sources / f.name).write_bytes(f.read_bytes())
            weather = ext.read_jsonl(sources / 'regional_temperature.jsonl.gz')
            # A target-day observation must remain inaccessible to the history.
            weather = [r for r in weather if (r['region'], r['timestamp']) !=
                       ('Bergen', '2020-02-11T00:00:00')]
            weather.append({'region': 'Bergen', 'timestamp': '2020-02-11T00:00:00',
                            'temperature_c': 999, 'source_from_numeric': 999,
                            'source_csv_record': 999})
            ext.write_jsonl(sources / 'regional_temperature.jsonl.gz', weather)
            ext.build([self.sample], sources, base)
            actual = ext.read_jsonl(base / 'inputs/history_weather.jsonl.gz')[0]
            self.assertEqual(set(actual), {'sample_id', 'history_weather'})
            self.assertEqual(len(actual['history_weather']['temperature_c']), 168)
            self.assertNotIn(999, actual['history_weather']['temperature_c'])
            self.assertEqual(actual['history_weather']['end'], '2020-02-11T00:00:00')
            self.assertNotIn('Aq1', json.dumps(actual))
            review = ext.read_jsonl(base / 'review/household_changes.jsonl')[0]
            self.assertFalse(review['eligible_as_model_input'])
        self.assertEqual(self.sample, before)

    def test_missing_weather_fails_without_imputation(self):
        self.sample['input']['context']['region'] = 'unknown_region'
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(KeyError):
                ext.build([self.sample], self.sources, Path(d))


if __name__ == '__main__':
    unittest.main()
