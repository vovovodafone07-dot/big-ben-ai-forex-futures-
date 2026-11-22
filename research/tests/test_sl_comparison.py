import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('sl_comparison',Path(__file__).resolve().parents[1]/'sl_comparison.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ComparisonTests(unittest.TestCase):
    def test_small_sample_does_not_claim_improvement_and_keeps_unresolved(self):
        report=m.compare([{'id':'a','baseline':'SL','candidate':'TP'},{'id':'b','baseline':'SL','candidate':'UNRESOLVED'}])
        self.assertEqual(report['الأزواج_المكتملة'],1);self.assertEqual(report['غير_محسومة'],1)
        self.assertIn('غير كافية',report['النتيجة'])
    def test_paired_discordance_and_intervals(self):
        rows=[dict(id=str(i),baseline='SL',candidate='TP') for i in range(40)]
        report=m.compare(rows)
        self.assertEqual(report['نسبة_الوقف_قبل'],100);self.assertEqual(report['نسبة_الوقف_بعد'],0)
        self.assertLess(report['قيمة_احتمال_مقارنة_ماكنيمار_الدقيقة'],.05)
        self.assertLess(report['فاصل_ويلسون_بعد_95'][1],10)
    def test_duplicate_ids_and_arbitrary_outcomes_rejected(self):
        with self.assertRaises(ValueError):m.compare([dict(id='a',baseline='SL',candidate='TP')]*2)
        with self.assertRaises(ValueError):m.compare([dict(id='a',baseline='SL',candidate='SKIPPED')])
