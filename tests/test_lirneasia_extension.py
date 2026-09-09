"""Failure-path and evaluator-contract checks for the separate real-household extension."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_lirneasia_extension import validate_run, split_households
from lirneasia_io import metrics, model_input, evaluate


class LirneasiaTests(unittest.TestCase):
    def run_fixture(self):
        return {'start':'2024-04-01T00:00:00','days':8,'interval_minutes':15,
                'import_register_kwh':[i*.1 for i in range(769)],'export_register_kwh':[0.]*769}

    def test_cumulative_endpoint_required(self):
        r=self.run_fixture();r['import_register_kwh'].pop()
        with self.assertRaises(ValueError):validate_run(r)

    def test_resets_export_and_nonfinite_rejected(self):
        for field,value in [('import_register_kwh',-1.),('import_register_kwh',float('nan')),('export_register_kwh',1.)]:
            r=self.run_fixture();r[field][20]=value
            with self.assertRaises(ValueError):validate_run(r)

    def test_power_energy_conversion(self):
        actual=[.25]*96
        self.assertTrue(all(v==0 for v in metrics(actual,actual).values()))
        out=metrics(actual,[.5]*96)
        for key in ['hourly_mae_kw','hourly_rmse_kw','hourly_peak_absolute_error_kw','native_15min_mae_kw']:
            self.assertEqual(out[key],1.)
        self.assertEqual(out['daily_energy_absolute_error_kwh'],24.)

    def test_invalid_values_rejected(self):
        for value in [True,-1.,float('nan'),float('inf'),'0.2']:
            pred=[.25]*96;pred[0]=value
            with self.assertRaises(ValueError):metrics([.25]*96,pred)
        with self.assertRaises(ValueError):metrics([.25]*96,[.25]*95)

    def test_profile_ablation_does_not_mutate_or_expose_metadata(self):
        s={'input':{'profile':{'count':4},'history':[1],'context':{'calendar':1}},'metadata':{'household_id':'ID1234'},'output':[2]}
        old=copy.deepcopy(s);result=model_input(s,'history_only')
        self.assertNotIn('profile',result);self.assertNotIn('metadata',result);self.assertNotIn('output',result)
        self.assertEqual(s,old)
        self.assertEqual(model_input(s,'history_profile'),s['input'])

    def test_household_assignment_independent_of_input_order(self):
        ids=['ID'+str(i) for i in range(422)]
        a=split_households(ids);self.assertEqual(a,split_households(list(reversed(ids))))
        self.assertEqual([list(a.values()).count(k) for k in ['train','validation','test']],[295,63,64])

    def test_duplicate_prediction_fails_before_reading_samples(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pred.jsonl';r=json.dumps({'sample_id':'duplicate','energy_kwh':[0.]*96})
            p.write_text(r+'\n'+r+'\n')
            with self.assertRaisesRegex(ValueError,'Duplicate'):evaluate(p,'test','history_only',Path(d)/'missing')


if __name__=='__main__':unittest.main()
