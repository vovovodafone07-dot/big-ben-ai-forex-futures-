import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone

spec=importlib.util.spec_from_file_location('walk_forward_test',Path(__file__).resolve().parents[1]/'walk_forward.py')
wf=importlib.util.module_from_spec(spec);spec.loader.exec_module(wf)
NOW=datetime(2026,11,14,tzinfo=timezone.utc)
SOURCE={'source_sha256':'a'*64}


def rows(count=800):
    start=NOW-timedelta(minutes=(count+1)*5)
    return [{'time':(start+timedelta(minutes=i*5)).isoformat(),'open':100.,'high':101.,'low':99.,'close':100.} for i in range(count)]


class WalkForwardTests(unittest.TestCase):
    def test_small_real_engine_sample_retains_original_and_never_promotes(self):
        report=wf.run(rows(),.01,SOURCE,now=NOW,min_train=360,test_bars=120)
        self.assertEqual(report['status'],'INSUFFICIENT_EVIDENCE')
        self.assertFalse(report['promotion_allowed']);self.assertFalse(report['pine_parity_verified'])
        self.assertTrue(all(f['selected_rr']==2.5 for f in report['folds']))
        self.assertTrue(all(f['test_range'][1]<=report['holdout']['range'][0] for f in report['folds']))

    def test_final_holdout_poison_cannot_change_selection(self):
        def fake(data,tick,config,**kwargs):
            # A mistaken full-dataset training call would see the poisoned tail.
            mean=sum(r['close'] for r in data)/len(data)
            reward=(config['rr'] if mean<200 else 10-config['rr'])
            trades=[{'entry_index':i,'outcome':'tp','gross_r':reward,'net_r':None} for i in range(0,len(data),5)]
            return {'trades':trades}
        original=rows();changed=rows()
        for row in changed[640:]:row.update(open=1000.,high=1001.,low=999.,close=1000.)
        with patch.object(wf.engine,'replay',side_effect=fake):
            first=wf.run(original,.01,SOURCE,now=NOW,min_train=360,test_bars=120)
            second=wf.run(changed,.01,SOURCE,now=NOW,min_train=360,test_bars=120)
        self.assertEqual([f['selected_rr'] for f in first['folds']],[f['selected_rr'] for f in second['folds']])
        self.assertEqual(first['holdout']['frozen_rr'],second['holdout']['frozen_rr'])
        self.assertNotEqual(first['holdout']['candidate_metrics'],second['holdout']['candidate_metrics'])
        self.assertFalse(second['holdout']['selection_uses_holdout'])

    def test_future_bars_and_excessive_fold_budget_rejected(self):
        with self.assertRaises(ValueError):wf.run(rows(),.01,SOURCE,now=NOW,max_folds=5)
        data=rows();data[-1]['time']=(NOW+timedelta(minutes=5)).isoformat()
        with self.assertRaises(ValueError):wf.run(data,.01,SOURCE,now=NOW)

    def test_uncertainty_is_absent_without_resolved_trades(self):
        self.assertIsNone(wf.wilson(0,0))
        low,high=wf.wilson(5,10)
        self.assertLess(low,.5);self.assertGreater(high,.5)

    def test_smt_requires_real_synchronized_peer_history(self):
        with self.assertRaisesRegex(ValueError,'peer_history'):
            wf.run(rows(),.01,SOURCE,now=NOW,config={'enable_smt':True})


if __name__=='__main__':unittest.main()
