"""Synthetic paired-candle and no-lookahead regressions."""
import importlib.util
import math
from pathlib import Path
import unittest
from datetime import datetime,timezone,timedelta

spec=importlib.util.spec_from_file_location('test_smt_research',Path(__file__).resolve().parents[1]/'backend'/'smt_research.py')
smt=importlib.util.module_from_spec(spec);spec.loader.exec_module(smt)
NOW=datetime(2026,11,14,tzinfo=timezone.utc)

def candles(invert=False):
    rows=[];price=100.
    for n in range(100):
        price*=math.exp((-.001 if invert else .001)*math.sin(n+1))
        rows.append({'time':(NOW-timedelta(minutes=(100-n)*5)).isoformat(),'close':price,'high':price+.1,'low':price-.1})
    return rows

class SMTTests(unittest.TestCase):
    def test_measures_returns_without_claiming_live_pine_confirmation(self):
        result=smt.measure(candles(),candles(),NOW)
        self.assertEqual(result['correlation'],1);self.assertEqual(result['return_samples'],99)
        self.assertTrue(result['candidate_supported']);self.assertFalse(result['live_smt_confirmed'])
        self.assertFalse(result['bullish_divergence']);self.assertFalse(result['bearish_divergence'])

    def test_inverse_market_is_not_approved_by_positive_pair_policy(self):
        result=smt.measure(candles(),candles(True),NOW)
        self.assertEqual(result['correlation'],-1);self.assertFalse(result['candidate_supported'])
        self.assertIsNone(result['bullish_divergence'])

    def test_missing_bars_and_open_future_candles_are_not_filled(self):
        a,b=candles(),candles()
        b=b[::2]
        a.append({'time':(NOW+timedelta(minutes=5)).isoformat(),'close':1,'high':2,'low':.5})
        result=smt.measure(a,b,NOW)
        self.assertEqual(result['return_samples'],0);self.assertEqual(result['state'],'INSUFFICIENT_DATA')

    def test_stale_and_duplicate_data_do_not_become_live_confirmation(self):
        rows=candles();self.assertEqual(smt.measure(rows+rows,rows,NOW)['state'],'INVALID_DATA')
        result=smt.measure(rows,rows,NOW+timedelta(hours=4))
        self.assertFalse(result['fresh_history']);self.assertFalse(result['live_smt_confirmed'])

    def test_bullish_divergence_requires_synchronized_lows(self):
        a,b=candles(),candles();a[-1]['low']=90;b[-1]['low']=min(r['low'] for r in b[-21:-1])
        result=smt.measure(a,b,NOW)
        self.assertTrue(result['bullish_divergence']);self.assertFalse(result['live_smt_confirmed'])
