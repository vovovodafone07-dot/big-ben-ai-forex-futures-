"""Platform-native OHLC strategy safety tests. Fixtures are synthetic and NEVER market data."""
import datetime, pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"backend"))
from native_chart_analysis import evaluate, _aggregate
UTC=datetime.timezone.utc
END=datetime.datetime(2026,11,20,12,0,tzinfo=UTC)
NOW=END+datetime.timedelta(minutes=5)

def m5(count=1000, direction=1):
    start=END-datetime.timedelta(minutes=5*(count-1))
    out=[]
    for i in range(count):
        price=100+direction*i*.01
        op=price-.002*direction
        hi=max(op,price)+.006
        lo=min(op,price)-.006
        out.append(((start+datetime.timedelta(minutes=5*i)).isoformat(),op,hi,lo,price))
    return out

class NativeChartTests(unittest.TestCase):
    def test_never_use_pine_webhook(self):
        x=evaluate(m5(),mode="scalp",now=NOW)
        self.assertFalse(x["uses_tradingview_signals"])
        self.assertFalse(x["broker_execution"])
        self.assertFalse(x["realtime_feed_verified"])
        if x["candidate"]:self.assertEqual(x["candidate"]["status"],"UNCONFIRMED_PLATFORM_SETUP")
    def test_market_closed_is_wait(self):
        x=evaluate(m5(),mode="scalp",now=NOW+datetime.timedelta(days=2))
        self.assertEqual(x["state"],"STALE_OR_UNCLOSED")
        self.assertIsNone(x["candidate"])
    def test_no_fake_future_candle(self):
        x=evaluate(m5(),mode="scalp",now=END)
        self.assertEqual(x["state"],"STALE_OR_UNCLOSED")
    def test_gaps_rejected(self):
        bars=m5()
        bars[-9]=(bars[-8][0],)+bars[-9][1:]
        x=evaluate(bars,mode="scalp",now=NOW)
        self.assertEqual(x["state"],"MISSING_RECENT_M5_BARS")
        self.assertIsNone(x["candidate"])
    def test_swing_independent_uses_aggregated_h1_h4(self):
        x=evaluate(m5(),mode="swing",now=NOW)
        self.assertNotEqual(x["state"],"INVALID_MODE")
        self.assertFalse(x["uses_tradingview_signals"])
        self.assertIn(x["state"],("NO_SETUP","CANDIDATE_RESEARCH_ONLY","HTF_FILTER_REJECTED","INSUFFICIENT_HTF_HISTORY","STALE_HTF_DATA","RISK_OUT_OF_RANGE"))
        if x["candidate"]:self.assertEqual(x["candidate"]["timeframe"],"H1")
    def test_partial_bucket_not_synthesized(self):
        bars=m5(60)
        raw=[]
        for x in bars:
            dt=datetime.datetime.fromisoformat(x[0])
            raw.append((dt,*x[1:]))
        aggregated=_aggregate(raw,60)
        self.assertLessEqual(len(aggregated),5)
    def test_invalid_prices_no_candidate(self):
        bars=m5()
        x=list(bars[-1]);x[2]=1;bars[-1]=tuple(x)
        self.assertEqual(evaluate(bars,now=NOW)["state"],"INVALID_CANDLE")
    def test_short_history_no_trade(self):
        self.assertIsNone(evaluate(m5(10),now=NOW)["candidate"])

if __name__=="__main__":unittest.main()
