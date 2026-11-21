"""Offline regression: Arabic technical events, official-news scenarios and dedup."""
import importlib.util,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,timezone
import unittest
spec=importlib.util.spec_from_file_location("arabic_test",Path(__file__).resolve().parents[1]/"backend"/"arabic_event_engine.py")
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
NOW=datetime(2026,11,22,0,5,tzinfo=timezone.utc)
def bars(mode="break_high",n=70):
    start=NOW-timedelta(minutes=n*5)
    a=[]
    for i in range(n):
        x=100+i*.01
        a.append(((start+timedelta(minutes=5*i)).isoformat(),x-.1,x+.2,x-.2,x))
    t,op,hi,lo,c=a[-1]
    a[-1]=(t,op,200 if mode=="sweep_high" else 205,
           95 if mode=="sweep_low" else lo,
           c if mode=="sweep_high" else 200 if mode=="break_high" else 96)
    return a
class ArabicEventTests(unittest.TestCase):
 def test_breakout_confirmed_and_deduplicated(self):
    data=bars("break_high")
    events=engine.technical_events("BITSTAMP:BTCUSD",data,NOW)
    self.assertTrue(any(e["event_type"]=="BREAK_HIGH" for e in events))
    self.assertIn("⚡",engine.technical_message(events[0]))
    c=sqlite3.connect(":memory:")
    try:
     engine.migrate(c)
     one=events[0];key=engine.reserve(c,one)
     self.assertIsNotNone(key)
     self.assertIsNone(engine.reserve(c,one))
     engine.finish(c,key,"sent")
     self.assertIsNone(engine.reserve(c,one))
    finally:c.close()
 def test_sweep_exposes_not_automatic_trade(self):
    events=engine.technical_events("BITSTAMP:BTCUSD",bars("sweep_high"),NOW)
    self.assertTrue(any(e["event_type"]=="SWEEP_HIGH" for e in events))
    self.assertIn("ليس صفقة مؤكدة",events[0]["note"])
 def test_stale_candles_no_events(self):
    self.assertEqual(engine.technical_events("BITSTAMP:BTCUSD",bars(),NOW+timedelta(minutes=11)),[])
 def test_missing_recent_bar_no_events(self):
    data=bars();data.pop(-4)
    self.assertEqual(engine.technical_events("BITSTAMP:BTCUSD",data,NOW),[])
 def test_unverified_news_is_not_invented(self):
    calendar={"calendar":[{"time":(NOW+timedelta(minutes=10)).isoformat(),
                           "title":"Consumer Price Index","currency":"USD",
                           "feed_fresh":True,"feed_state":"CONNECTED",
                           "consensus":None,"actual":None,"impact_verified":False}]}
    news=engine.news_scenarios(calendar,NOW)
    self.assertEqual(len(news),1)
    m=engine.news_message(news[0],NOW)
    self.assertIn("غير متوفر",m)
    self.assertIn("سيناريوهات مشروطة",m)
    self.assertIn("الناسداك",m)
    self.assertNotIn("نتيجة فعلية: شراء مؤكد",m)
 def test_dont_notify_stale_official_calendar(self):
    calendar={"calendar":[{"time":(NOW+timedelta(minutes=10)).isoformat(),
                           "title":"CPI","currency":"USD","feed_fresh":False,
                           "feed_state":"DEGRADED"}]}
    self.assertFalse(engine.news_scenarios(calendar,NOW))
 def test_no_news_without_title_and_matching_timestamp(self):
    self.assertEqual(engine.news_scenarios({"calendar":[]},NOW),[])
if __name__=="__main__":unittest.main()
