"""Offline native Telegram tests. No network, no actual Telegram message."""
import importlib.util
import json
import sqlite3
from pathlib import Path
from datetime import datetime,timezone
import unittest
from unittest.mock import Mock

spec=importlib.util.spec_from_file_location("instant_telegram_test",Path(__file__).resolve().parents[1]/"backend"/"instant_telegram.py")
telegram=importlib.util.module_from_spec(spec);spec.loader.exec_module(telegram)
def plan(symbol="BITSTAMP:BTCUSD",mode="scalp",status="CONDITIONAL"):
 return {"symbol":symbol,"instrument":{"asset_class":"crypto"},"mode":mode,"status":status,
  "technical_direction":"BUY","bias":"BULLISH","provider":"Bitstamp",
  "source_time":"2026-11-21T21:00:00+00:00","broker_execution":False,
  "entry":60000.0,"sl":59900.0,"targets":[
    {"name":"TP1","price":60100,"reason":"1R target"},
    {"name":"TP2","price":60200,"reason":"2R target"},
    {"name":"TP3","price":60300,"reason":"3R target"}],
  "confirmation":{"type":"M5_CLOSE","level":60000,"confirmed":False},
  "evidence":{"LIQUIDITY_SWEEP":"LOW","FVG":"NOT_DETECTED"},
  "news":{"state":"NO_VERIFIED_EVENT"}}
class R:
 status=200
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self,size):return b'{"ok":true,"result":{"message_id":42}}'
class TelegramNativeTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(":memory:")
  telegram.migrate(self.db)
 def tearDown(self):self.db.close()
 def test_format_arabic_and_all_3_targets(self):
  m=telegram.message(plan(),now=datetime(2026,11,21,21,tzinfo=timezone.utc))
  for word in ("🔵","شراء","سيناريو مشروط","TP1","TP2","TP3","60000","59900",
               "BITSTAMP" if False else "Bitstamp","مسقط","ليس دخولاً الآن"):
   self.assertIn(word,m)
  self.assertLess(len(m),4000)
 def test_sell_red_and_labels(self):
  p=plan(status="READY");p.update(technical_direction="SELL",entry=60000,sl=60100,
            targets=[{"name":"TP1","price":59900},{"name":"TP2","price":59800},{"name":"TP3","price":59700}])
  p["confirmation"]["confirmed"]=True
  text=telegram.message(p)
  self.assertIn("🔴",text);self.assertIn("بيع",text);self.assertNotIn("سيناريو مشروط",text)
 def test_html_is_escaped(self):
  p=plan();p["targets"][0]["reason"]="<script>x</script>"
  self.assertIn("&lt;script&gt;",telegram.message(p))
  self.assertNotIn("<script>",telegram.message(p))
 def test_duplicate_does_not_send_twice_on_same_trade_or_candle(self):
  p=plan();first=telegram.claim(self.db,p,"12345678")
  self.assertIsNotNone(first)
  self.assertIsNone(telegram.claim(self.db,p,"12345678"))
  telegram.finish(self.db,first,"sent")
  p["source_time"]="2026-11-21T21:05:00+00:00"
  self.assertIsNone(telegram.claim(self.db,p,"12345678"))
  self.assertEqual(self.db.execute("SELECT COUNT(*) FROM native_telegram_alerts").fetchone()[0],1)
 def test_updated_trade_or_new_symbol_can_send(self):
  p=plan();one=telegram.claim(self.db,p,"12345678")
  telegram.finish(self.db,one,"sent")
  changed=plan();changed["entry"]=60001;changed["targets"][0]["price"]=60101
  self.assertIsNotNone(telegram.claim(self.db,changed,"12345678"))
  another=plan("BITSTAMP:ETHUSD")
  self.assertIsNotNone(telegram.claim(self.db,another,"12345678"))
 def test_failed_delivery_may_retry_immediately_on_new_analysis(self):
  p=plan();one=telegram.claim(self.db,p,"12345678")
  telegram.finish(self.db,one,"failed")
  self.assertEqual(one,telegram.claim(self.db,p,"12345678"))
 def test_never_notify_when_unverified_or_no_targets(self):
  for status in ("DATA_UNAVAILABLE","WAIT"):
   p=plan(status=status);self.assertFalse(telegram.eligible(p));self.assertIsNone(telegram.claim(self.db,p,"12345678"))
  p=plan();p["targets"]=[]
  self.assertFalse(telegram.eligible(p))
  p=plan();p["provider"]="unverified"
  self.assertFalse(telegram.eligible(p))
 def test_actual_send_message_uses_html_and_correct_chat(self):
  captured={}
  def fake_open(req,timeout):
   captured["url"]=req.full_url
   captured["payload"]=json.loads(req.data)
   captured["timeout"]=timeout
   return R()
  r=telegram.send(plan(),"test_fake_bot_token","12345678",opener=fake_open)
  self.assertEqual(r,"sent")
  self.assertEqual(captured["payload"]["chat_id"],"12345678")
  self.assertEqual(captured["payload"]["parse_mode"],"HTML")
  self.assertIn("sendMessage",captured["url"])
  self.assertEqual(captured["timeout"],5)
 def test_successful_telegram_large_response_not_truncated(self):
  class LongReply:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):raise AssertionError("Do not read and truncate a successful Telegram body")
  self.assertEqual(telegram.send(plan(),"fake_token","12345678",
                   opener=lambda req,timeout:LongReply()),"sent")

 def test_ready_trade_only_telegram_template_excludes_news_and_bias(self):
  p=plan(status="READY")
  p["confirmation"]["confirmed"]=True
  result=telegram.trade_only_message(p)
  self.assertIn("🔵 شراء",result)
  self.assertIn("الدخول:",result)
  self.assertIn("وقف الخسارة:",result)
  self.assertIn("الهدف 1",result)
  self.assertIn("الهدف 3",result)
  self.assertNotIn("الأخبار",result)
  self.assertNotIn("الباياس",result)
  self.assertNotIn("سيناريو مشروط",result)
 def test_ready_structural_fingerprint_ignores_target_only_drift(self):
  p=plan(status="READY");p["confirmation"]["confirmed"]=True
  x=telegram.fingerprint(p,"12345678")
  p["targets"][2]["price"]=60400
  self.assertEqual(x,telegram.fingerprint(p,"12345678"))
  p["entry"]=60001
  self.assertNotEqual(x,telegram.fingerprint(p,"12345678"))
 def test_telegram_http_failure_is_safely_categorized(self):
  import urllib.error
  import io
  from unittest.mock import patch
  def fake_open(req,timeout):
   raise urllib.error.HTTPError(req.full_url,400,"Bad Request",{},
        io.BytesIO(b'{"ok":false,"description":"Bad Request: parse entities"}'))
  with patch("builtins.print") as out:
   result=telegram.send(plan(),"test_fake_bot_token","12345678",opener=fake_open)
  self.assertEqual(result,"failed")
  self.assertTrue(any("HTML_ENTITIES" in str(arg) for call in out.call_args_list for arg in call.args))
  self.assertFalse(any("test_fake_bot_token" in str(arg) for call in out.call_args_list for arg in call.args))

 def test_isolated_from_broker_orders_and_no_fake_barchart_futures(self):
  p=plan("CME_MINI:NQ1!");p["provider"]="Barchart OnDemand"
  self.assertFalse(telegram.eligible(p))
  p=plan();p["broker_execution"]=True
  self.assertFalse(telegram.eligible(p))
if __name__=="__main__":unittest.main()
