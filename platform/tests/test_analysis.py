"""Evidence analysis tests use synthetic events, never invented market claims."""
import importlib.util
import json
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

spec=importlib.util.spec_from_file_location("analysis_under_test",Path(__file__).resolve().parents[1]/"backend"/"analysis.py")
analysis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)

class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,13,12,tzinfo=timezone.utc)
    def row(self, minutes=5, kind="HEARTBEAT", **data):
        stamp=(self.now-timedelta(minutes=minutes)).isoformat()
        return ("EURUSD",kind,stamp,json.dumps({"close":100,"m15":1,"h1":1,"h4":1,**data}))
    def test_fresh_aligned_bias_explains_observation(self):
        report=analysis.analyze_events([self.row()],self.now)
        item=report["symbols"][0]
        self.assertEqual(item["current_bias"],"BULLISH")
        self.assertEqual(item["market_state"],"UNKNOWN")
        self.assertIsNone(item["new_signal"])
        self.assertIsNone(item["evidence_score"])
    def test_stale_or_future_has_no_current_bias(self):
        for minutes in (20,-1):
            item=analysis.analyze_events([self.row(minutes)],self.now)["symbols"][0]
            self.assertEqual(item["current_bias"],"UNKNOWN")
            self.assertEqual(item["state"],"UNKNOWN")
    def test_mixed_bias(self):
        item=analysis.analyze_events([self.row(h1=-1)],self.now)["symbols"][0]
        self.assertEqual(item["current_bias"],"MIXED")
    def test_missing_or_boolean_bias_is_not_alignment(self):
        for value in (None,True,"1"):
            item=analysis.analyze_events([self.row(h1=value)],self.now)["symbols"][0]
            self.assertEqual(item["current_bias"],"UNKNOWN")
    def test_latest_by_timestamp_not_query_order(self):
        rows=[self.row(5,h1=-1),self.row(10,h1=1)]
        self.assertEqual(analysis.analyze_events(rows,self.now)["symbols"][0]["current_bias"],"MIXED")
    def test_trade_is_not_a_heartbeat(self):
        self.assertEqual(analysis.analyze_events([self.row(kind="BUY")],self.now)["count"],0)
    def test_nonfinite_close_not_exposed(self):
        item=analysis.analyze_events([self.row(close=float("nan"))],self.now)["symbols"][0]
        self.assertIsNone(item["observed_m5_close"])
    def test_actual_source_version_is_reported_without_inventing_one(self):
        item=analysis.analyze_events([self.row(strategy_version="v6.4.1-sync")],self.now)["symbols"][0]
        self.assertEqual(item["strategy_version"],"v6.4.1-sync")
        for value in (None,{},"x"*81):
            item=analysis.analyze_events([self.row(strategy_version=value)],self.now)["symbols"][0]
            self.assertIsNone(item["strategy_version"])

if __name__=="__main__":unittest.main()
