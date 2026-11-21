"""Offline validation of independent research candidates, with synthetic candles only in tests."""
import datetime
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"backend"))
from analysis_opportunities import evaluate

UTC=datetime.timezone.utc
NOW=datetime.datetime(2026,11,23,12,5,tzinfo=UTC)

def candles(n=60):
    base=NOW-datetime.timedelta(minutes=5*n)
    output=[]
    for i in range(n):
        close=100+i*.02
        output.append((base+datetime.timedelta(minutes=5*i),close-.02,close+.03,close-.05,close))
    return [tuple((c[0].isoformat(),*c[1:])) for c in output]

class OpportunitySafetyTests(unittest.TestCase):
    def test_stale_candles_cannot_create_trades(self):
        rows=candles()
        self.assertEqual(evaluate(rows,now=NOW+datetime.timedelta(days=1))["state"],"STALE_OR_UNCLOSED")

    def test_missing_market_history_is_not_a_signal(self):
        result=evaluate([],now=NOW)
        self.assertEqual(result["state"],"INSUFFICIENT_DATA")
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["execution_enabled"])

    def test_swing_never_relabels_m5(self):
        result=evaluate(candles(),now=NOW,mode="swing")
        self.assertEqual(result["state"],"SWING_ENGINE_NOT_VALIDATED")
        self.assertIsNone(result["candidate"])

    def test_gap_in_last_window_is_rejected(self):
        rows=candles()
        row=list(rows[-4])
        row[0]=(datetime.datetime.fromisoformat(row[0])+datetime.timedelta(minutes=5)).isoformat()
        rows[-4]=tuple(row)
        self.assertEqual(evaluate(rows,now=NOW)["state"],"MISSING_BARS")

    def test_current_sample_never_claims_authenticated_signal(self):
        result=evaluate(candles(),now=NOW)
        self.assertFalse(result["confirmed_signal"])
        self.assertFalse(result["execution_enabled"])
        if result["candidate"]:
            self.assertEqual(result["candidate"]["status"],"UNCONFIRMED_RESEARCH_CANDIDATE")
            self.assertFalse(result["candidate"]["costs_included"])

if __name__=="__main__":
    unittest.main()
