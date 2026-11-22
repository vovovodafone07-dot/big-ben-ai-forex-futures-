"""Offline bridge validation, strict isolation and durable synthetic transport proof."""
import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]/'backend'
spec=importlib.util.spec_from_file_location('bridge_test_app',ROOT/'app.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
bridge=app._bridge_validation
NOW=datetime(2026,11,20,15,15,tzinfo=timezone.utc)
def payload():
 p=bridge.template(6094187030);p.update(time=NOW.isoformat(),bar_time=(NOW-timedelta(minutes=15)).isoformat(),timeframe='15',entry='100',sl='90',tp='130',close='101');return p
class BridgeTests(unittest.TestCase):
 def test_eight_templates_preserve_symbols_conditions_and_plots(self):
  self.assertEqual(len(bridge.ALERTS),8)
  for ident in bridge.ALERTS:
   p=bridge.template(ident);self.assertEqual(p['alert_id'],ident);self.assertIn('plot("Entry")',p['entry']);self.assertEqual(p['time'],'{{timenow}}')
 def test_string_prices_normalize_and_same_bar_deduplicates(self):
  a=bridge.normalize(payload(),NOW);p=payload();p['time']=(NOW+timedelta(seconds=40)).isoformat()
  b=bridge.normalize(p,NOW+timedelta(seconds=40));self.assertEqual(a['event_id'],b['event_id']);self.assertEqual(a['timeframe'],'15');self.assertFalse(a['source_identity_verified'])
 def test_nan_future_time_wrong_symbol_and_wrong_timeframe_rejected(self):
  for key,value in [('entry','NaN'),('time',(NOW+timedelta(seconds=1)).isoformat()),('symbol','COMEX:GC1!'),('timeframe','5'),('bar_time',NOW.isoformat())]:
   p=payload();p[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):bridge.normalize(p,NOW)
 def test_stale_send_and_inverted_levels_rejected(self):
  with self.assertRaises(ValueError):bridge.normalize(payload(),NOW+timedelta(minutes=4))
  p=payload();p['sl']='110'
  with self.assertRaises(ValueError):bridge.normalize(p,NOW)
class TransportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'DATABASE_URL':''});self.env.start()
  self.db=patch.object(app,'DB',Path(self.tmp.name)/'test.sqlite3');self.db.start();app.init()
 def tearDown(self):self.db.stop();self.env.stop();self.tmp.cleanup()
 def test_two_receipts_replay_and_no_production_trade(self):
  with patch.object(app,'send_transport_card',side_effect=[{'الحالة':'قبله Telegram','معرف_الرسالة':101},{'الحالة':'قبله Telegram','معرف_الرسالة':102}]) as send:
   first=app.execute_transport_fixture('fixture-123','open');app.init();second=app.execute_transport_fixture('fixture-123','open')
   self.assertEqual(len(first['الرسائل']),2);self.assertTrue(second['مكرر']);self.assertEqual(send.call_count,2)
   for call in send.call_args_list:self.assertIn('أسعار مصطنعة',call.args[0]);self.assertNotIn('الأخبار',call.args[0])
  with app.history_connection() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
   self.assertEqual(db.execute('SELECT COUNT(*) FROM native_trade_journal').fetchone()[0],0)
 def test_closed_fixture_sends_nothing(self):
  with patch.object(app,'send_transport_card') as send:
   result=app.execute_transport_fixture('closed-123','closed');self.assertEqual(result['بوابة_السوق_المغلق'],'حجبت الإرسال');send.assert_not_called()
 def test_legacy_signal_cannot_bypass_market_and_native_dedup_gate(self):
  with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'fixture'}),patch.object(app,'telegram_destination',return_value='8996403863'),patch.object(app,'analyze_instant_native',return_value={'status':'DATA_UNAVAILABLE'}),patch.object(app,'trigger_instant_telegram') as send:
   self.assertEqual(app.telegram_notify({'event':'BUY','symbol':'FOREXCOM:XAUUSD'}),'market_closed');send.assert_not_called()

 def test_archived_stale_bbb_is_retained_but_never_replayed_as_fresh(self):
  event=bridge.normalize(payload(),NOW);app.save_event(event)
  with patch.object(app,'analyze_instant_native') as analyze:
   app.process_bbb_event(event);app.process_bbb_event(event);analyze.assert_not_called()
  with app.history_connection() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
   status=db.execute("SELECT status FROM telegram_bot_receipts WHERE id LIKE 'bbb-job:%'").fetchone()[0]
   self.assertIn('انتهت حداثة',status)

 def test_uncertain_delivery_is_not_automatically_repeated(self):
  with patch.object(app,'send_transport_card',return_value={'الحالة':'غير مؤكد'}) as send:
   app.execute_transport_fixture('uncertain-123','open');app.execute_transport_fixture('uncertain-123','open');self.assertEqual(send.call_count,1)
