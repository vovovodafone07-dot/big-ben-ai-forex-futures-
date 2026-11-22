"""No-WAIT native engine: deterministic synthetic fixtures, no outside trades."""
import importlib.util
from pathlib import Path
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location("instant_test",Path(__file__).resolve().parents[1]/"backend"/"instant_engine.py")
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
NOW=datetime(2026,11,20,16,5,tzinfo=timezone.utc)
def candles(n=1000):
    # End with closed bar opened at 16:00:00.
    start=NOW-timedelta(minutes=5*n)
    out=[]
    for i in range(n):
        price=20000+i*.45+((i%12)-6)*.13
        out.append(((start+timedelta(minutes=i*5)).isoformat(),price-.15,price+.8,price-.9,price))
    return out
class InstantNativeTests(unittest.TestCase):
 def test_unlicensed_nq_never_issues_levels(self):
    r=engine.evaluate("CME_MINI:NQ1!",candles(),asset_class="futures",tick_size=.25,now=NOW,source_identity_verified=False)
    self.assertEqual(r["status"],"DATA_UNAVAILABLE")
    self.assertEqual(r["reason_code"],"SOURCE_IDENTITY_UNVERIFIED")
    self.assertIsNone(r["entry"]);self.assertFalse(r["broker_execution"])
 def test_history_without_three_unswept_levels_cannot_invent_targets(self):
    r=engine.evaluate("CME_MINI:NQH27",candles(),asset_class="futures",tick_size=.25,now=NOW,
                      provider="Barchart OnDemand",source_identity_verified=True)
    self.assertIn(r["status"],("READY","CONDITIONAL"))
    self.assertEqual(r["status"],'CONDITIONAL')
    self.assertTrue(all(t.get('measured_price') and t.get('source_time') for t in r['targets']))
    self.assertNotIn("WAIT",r["status"])
    self.assertAlmostEqual(r["entry"]/.25,round(r["entry"]/.25))
    self.assertTrue(r["sl"]!=r["entry"])
    self.assertFalse(r["realtime_verified"])
 def test_swing_has_independent_h1_levels_and_targets(self):
    rows=candles()
    scalp=engine.evaluate("BITSTAMP:BTCUSD",rows,asset_class="crypto",tick_size=.01,
                          provider="Bitstamp",now=NOW,source_identity_verified=True,mode="scalp")
    swing=engine.evaluate("BITSTAMP:BTCUSD",rows,asset_class="crypto",tick_size=.01,
                          provider="Bitstamp",now=NOW,source_identity_verified=True,mode="swing")
    self.assertEqual(scalp["execution_timeframe"],"M5")
    self.assertEqual(swing["execution_timeframe"],"H1")
    self.assertEqual(swing["confirmation"]["type"],"H1_CLOSE")
    self.assertEqual(swing['status'],'CONDITIONAL')
    self.assertNotEqual((scalp["entry"],scalp["sl"]),(swing["entry"],swing["sl"]))
    self.assertFalse(swing["broker_execution"])

 def test_measured_pivots_have_provenance_no_future_pivot_and_no_reused_level(self):
    highs=[101,102,140,103,104,105,130,106,107,108,120,109,110]
    rows=[(NOW+timedelta(minutes=5*i),95,h,90,96) for i,h in enumerate(highs)]
    targets=engine.measured_targets(rows,'BUY',100,10,.25)
    self.assertEqual([t['price'] for t in targets],[120,130,140])
    self.assertTrue(all(t['source_time'] and t['confirmed_at'] and t['liquidity_type'] for t in targets))
    touched=rows+[(NOW+timedelta(minutes=65),95,121,90,96)]
    self.assertEqual([t['price'] for t in engine.measured_targets(touched,'BUY',100,10,.25)],[130,140])
    mirrored=[(t,200-o,200-l,200-h,200-c) for t,o,h,l,c in rows]
    self.assertEqual([t['price'] for t in engine.measured_targets(mirrored,'SELL',100,10,.25)],[80,70,60])
    self.assertEqual(engine.measured_targets(rows[:4],'BUY',100,10,.25),[])

 def test_stale_no_targets(self):
    r=engine.evaluate("BITSTAMP:BTCUSD",candles(),asset_class="crypto",tick_size=.01,
                      now=NOW+timedelta(minutes=32),source_identity_verified=True)
    self.assertEqual(r["status"],"DATA_UNAVAILABLE")
    self.assertEqual(r["targets"],[])
 def test_eleven_minute_old_m5_does_not_create_an_actionable_plan(self):
    r=engine.evaluate("BITSTAMP:BTCUSD",candles(),asset_class="crypto",tick_size=.01,
                      now=NOW+timedelta(minutes=6),source_identity_verified=True)
    self.assertEqual(r["status"],"DATA_UNAVAILABLE")
    self.assertEqual(r["reason_code"],"STALE_OR_UNCLOSED_M5")
    self.assertIsNone(r["entry"])
    self.assertEqual(r["targets"],[])

 def test_missing_recent_m5_no_targets(self):
    rows=candles();rows.pop(-3)
    r=engine.evaluate("OANDA:EURUSD",rows,now=NOW,source_identity_verified=True)
    self.assertEqual(r["reason_code"],"MISSING_RECENT_M5")
 def test_no_false_full_h4_bucket(self):
    b=engine._as_bars(candles(100))
    for value in engine.aggregate(b,240):
        start=value[0];chunk=[x for x in b if start<=x[0]<start+timedelta(hours=4)]
        self.assertEqual(len(chunk),48)
 def test_news_blocks_without_fake_direction(self):
    e={"calendar":[{"time":(NOW+timedelta(minutes=10)).isoformat(),"title":"US CPI","currency":"USD",
                    "feed_fresh":True,"feed_state":"CONNECTED","impact_verified":True}]}
    r=engine.evaluate("CME_MINI:NQH27",candles(),asset_class="futures",tick_size=.25,
                      now=NOW,source_identity_verified=True,news=e)
    self.assertEqual(r["status"],"NEWS_CAUTION")
    self.assertEqual(r["news"]["continuation_bias"],"UNVERIFIED")
 def test_unverified_calendar_does_not_claim_high_impact(self):
    e={"calendar":[{"time":(NOW+timedelta(minutes=4)).isoformat(),"title":"BLS upcoming","currency":"USD",
                    "feed_fresh":True,"feed_state":"CONNECTED","impact_verified":False}]}
    r=engine.evaluate("CME_MINI:NQH27",candles(),asset_class="futures",tick_size=.25,
                      now=NOW,source_identity_verified=True,news=e)
    self.assertEqual(r["status"],"NEWS_CAUTION")
    self.assertEqual(r["news"]["state"],"EVENT_UNRATED")
 def test_invalid_candle_price_rejected(self):
    b=candles();x=list(b[-1]);x[2]=0;b[-1]=tuple(x)
    r=engine.evaluate("BITSTAMP:BTCUSD",b,source_identity_verified=True,now=NOW)
    self.assertEqual(r["reason_code"],"INVALID_OHLC")
 def test_reject_duplicate_timestamp(self):
    b=candles();b[-2]=b[-1]
    r=engine.evaluate("BITSTAMP:BTCUSD",b,source_identity_verified=True,now=NOW)
    self.assertEqual(r["status"],"DATA_UNAVAILABLE")
if __name__=="__main__":unittest.main()
