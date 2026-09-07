"""Meaningful failure cases for the corrected benchmark and its score contract."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_quality import quality
from benchmark_profile import correct_profile
from benchmark_io import model_input, export
from build_baseline import read
from evaluate_benchmark import metrics, macro, evaluate


class BenchmarkTests(unittest.TestCase):
    def sample(self):return json.loads((ROOT/'baseline/v1/examples/sgsc.json').read_text())

    def test_zero_run_crossing_midnight_is_quarantined(self):
        vals=[1.0]*384;vals[30:78]=[0.0]*48
        self.assertEqual(quality(vals[:336],vals[336:],30)['disposition'],'quarantine')
        vals[30]=.001
        self.assertEqual(quality(vals[:336],vals[336:],30)['disposition'],'retain')

    def test_near_zero_is_not_automatically_excluded(self):
        q=quality([1.0]*168,[.0001]*24,60)
        self.assertEqual(q['disposition'],'retain');self.assertIn('near_zero_day_up_to_0_01_kwh_review_flag',q['flags'])

    def test_no_car_correction_rejects_conflicting_ev_answer(self):
        p=next(r for r in read(ROOT/'baseline/v1/profiles/iflex.jsonl.gz') if r['profile']['household']['car_present'] is False)
        r=correct_profile(p)
        self.assertEqual(r['profile']['household']['car_count'],0)
        p['metadata']['source_profile_provenance']['raw_answers']['q16_bil_b']='Yes'
        with self.assertRaises(AssertionError):correct_profile(p)

    def test_variants_remove_only_intended_information(self):
        r=self.sample();before=copy.deepcopy(r)
        self.assertNotIn('profile',model_input(r,'history_only'))
        self.assertNotIn('events',model_input(r,'history_profile')['context'])
        self.assertNotIn('someone_home',str(model_input(r,'full_without_daytime_home')['profile']['usage_habits']))
        self.assertEqual(model_input(r,'full')['context'],r['input']['context'])
        self.assertEqual(r,before)

    def test_metric_units_and_event_totals(self):
        r=self.sample();r['output']['energy_kwh']=[1.0]*48
        m=metrics(r,[1.5]*48)
        self.assertEqual(m['hourly_mae_kw'],1)
        self.assertEqual(m['hourly_rmse_kw'],1)
        self.assertEqual(m['daily_energy_absolute_error_kwh'],24)
        self.assertEqual(m['hourly_peak_absolute_error_kw'],1)
        self.assertEqual(m['event_energy_absolute_error_kwh'],4)

    def test_invalid_numeric_outputs_fail(self):
        r=self.sample()
        for value in (True,float('nan'),float('inf'),-.1,'1'):
            x=list(r['output']['energy_kwh']);x[0]=value
            with self.assertRaises(ValueError):metrics(r,x)
        with self.assertRaises(ValueError):metrics(r,[])

    def test_equal_households_not_equal_rows(self):
        self.assertEqual(macro([('a',{'x':0}),('a',{'x':0}),('b',{'x':6})])['metrics']['x'],3)

    def test_strict_track_cannot_silently_export_retrospective_data(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'data.gz'
            with self.assertRaises(ValueError):export(ROOT/'benchmark/v1',out,'train','full','strict_prospective')
            self.assertFalse(out.exists())

    def test_duplicate_submission_ids_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pred.jsonl';p.write_text((json.dumps({'sample_id':'a','energy_kwh':[]})+'\n')*2)
            with self.assertRaisesRegex(ValueError,'Duplicate'):evaluate(ROOT/'benchmark/v1',p,'test','full')


if __name__=='__main__':unittest.main()
