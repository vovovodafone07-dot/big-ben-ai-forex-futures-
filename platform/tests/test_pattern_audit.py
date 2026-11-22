import importlib.util
from pathlib import Path
from datetime import datetime,timezone,timedelta
import unittest
s=importlib.util.spec_from_file_location('patterns',Path(__file__).resolve().parents[1]/'backend/pattern_audit.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
NOW=datetime(2026,11,22,18,0,tzinfo=timezone.utc)
def bars(n=35):return [[(NOW-timedelta(minutes=5*(n-i))).isoformat(),100,102,98,100] for i in range(n)]
class PatternAuditTests(unittest.TestCase):
 def test_short_history_returns_seven_explicit_data_states(self):
  r=m.inspect('TEST:X','fixture',bars(1),NOW)
  self.assertEqual(len(r['checks']),7)
  self.assertTrue(all(c['state']=='requires_data' for c in r['checks']))
 def test_fvg_and_cisd_and_sweep_are_evaluated_from_closed_bars(self):
  b=bars();b[-2][1:]=[101,102,98,99];b[-1][1:]=[99,103,97,101.5]
  r=m.inspect('TEST:X','fixture',b,NOW);checks={c['name']:c for c in r['checks']}
  self.assertEqual(checks['CISD']['state'],'observed')
  self.assertEqual(checks['Turtle Soup']['state'],'observed')
  self.assertEqual(checks['SMT']['state'],'requires_data')
  self.assertTrue(r['fresh']);self.assertNotIn('entry',r)
 def test_future_open_gaps_and_invalid_geometry_not_used(self):
  b=bars();b.append([NOW.isoformat(),100,102,98,100])
  self.assertEqual(m.inspect('TEST:X','fixture',b,NOW)['candles'],35)
  b=bars();b.pop(-3)
  self.assertEqual(m.inspect('TEST:X','fixture',b,NOW)['candles'],2)
  b=bars();b[-1][2]=1
  self.assertEqual(m.inspect('TEST:X','fixture',b,NOW)['candles'],0)
 def test_old_history_is_analyzed_but_explicitly_not_fresh(self):
  r=m.inspect('TEST:X','fixture',bars(),NOW+timedelta(days=1))
  self.assertFalse(r['fresh']);self.assertEqual(r['checks'][1]['state'],'not_observed')
