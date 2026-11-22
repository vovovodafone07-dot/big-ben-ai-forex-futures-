"""Offline private interactions, replay protection, scoped symbols and dated news."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest
from datetime import datetime,timezone,timedelta

def load(name):
 s=importlib.util.spec_from_file_location('bot_test_'+name,Path(__file__).resolve().parents[1]/'backend'/(name+'.py'))
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
bot=load('telegram_interactive');precision=load('precision_setup')
NOW=datetime(2026,11,22,3,0,tzinfo=timezone.utc)
class BotTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');bot.migrate(self.db);bot.migrate(self.db)
  self.assets=[{'symbol':'COMEX_MINI:MGCZ26','asset_class':'futures','label':'الذهب المصغر','market_state':'حالة الجلسة غير مؤكدة'}]
 def tearDown(self):self.db.close()
 def run_update(self,action='home',ident=1,uid=12345678,chat_type='private'):
  update={'update_id':ident,'callback_query':{'id':'cb','from':{'id':uid},'message':{'chat':{'id':uid,'type':chat_type}},'data':action}}
  return bot.handle(self.db,update,allowed_users={'12345678'},connected=lambda:self.assets,news=lambda:{},journal=lambda:[],now=NOW)
 def test_all_main_actions_present_and_callback_size_bounded(self):
  buttons=[b for row in bot.home()['inline_keyboard'] for b in row]
  self.assertEqual(len(buttons),7)
  self.assertTrue(all(len(b['callback_data'].encode())<=64 for b in buttons))
 def test_private_allowlist_rejects_groups_and_others(self):
  with self.assertRaises(PermissionError):self.run_update(uid=99)
  with self.assertRaises(PermissionError):self.run_update(chat_type='group')
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM telegram_bot_receipts').fetchone()[0],0)
 def test_replay_ignored_and_swing_remembered(self):
  r=self.run_update('mode:swing');self.assertIn('السوينغ',r['text'])
  self.assertIsNone(self.run_update('mode:swing'))
  r=self.run_update('pick:'+bot.token(self.assets[0]['symbol']),2)
  self.assertEqual(r['analysis_request'],{'symbol':self.assets[0]['symbol'],'mode':'swing'})
  self.assertEqual(self.run_update('refresh',3)['analysis_request'],r['analysis_request'])
 def test_forged_or_disconnected_symbol_never_triggers_analysis(self):
  self.assertIsNone(self.run_update('pick:forged')['analysis_request'])
  self.assets=[]
  r=self.run_update('symbols:0',2);self.assertIn('لا توجد',r['text']);self.assertIsNone(r['analysis_request'])
 def test_news_opt_in_and_out_persist(self):
  self.run_update('news:on');self.assertEqual(self.db.execute('SELECT news_enabled FROM telegram_bot_state').fetchone()[0],1)
  self.run_update('news:off',2);self.assertEqual(self.db.execute('SELECT news_enabled FROM telegram_bot_state').fetchone()[0],0)
 def test_digest_local_date_freshness_and_missing_numbers(self):
  event={'time':NOW.isoformat(),'feed_fresh':True,'feed_state':'CONNECTED','title':'CPI'}
  snapshot={'calendar':[event,dict(event,time=(NOW+timedelta(days=1)).isoformat()),dict(event,feed_fresh=False)]}
  text=bot.digest(snapshot,NOW)
  self.assertIn('2026-11-22',text);self.assertEqual(text.count('⏰'),1);self.assertIn('غير موثق',text)
  self.assertIn('🔴',text);self.assertIn('🔵',text)
  self.assertIn('لا يعني',bot.digest({},NOW))
 def test_digest_claim_survives_reopen_and_scenarios_do_not_claim_prices(self):
  self.assertTrue(bot.claim(self.db,'digest:123:2026-11-22'))
  self.assertFalse(bot.claim(self.db,'digest:123:2026-11-22'))
  self.assertIn('ليس توصية',bot.scenario('CPI'))
  self.assertIn('البطالة',bot.scenario('NFP'))

class PrecisionTests(unittest.TestCase):
 def bars(self):
  rows=[(NOW+timedelta(minutes=5*i),100,102,98,100) for i in range(30)]
  return rows+[(NOW+timedelta(minutes=150),99,101,97,100),(NOW+timedelta(minutes=155),103,106,103,105),(NOW+timedelta(minutes=160),103.5,105,102.5,104)]
 def test_requires_ordered_sweep_msb_and_retest(self):
  r=precision.inspect(self.bars(),'BUY','BULLISH',2,.25)
  self.assertTrue(r['confirmed']);self.assertEqual(r['zone'],[102,103]);self.assertEqual(r['anchor'],97)
 def test_wrong_context_early_breakout_or_invalidated_zone_cannot_confirm(self):
  self.assertFalse(precision.inspect(self.bars(),'BUY','BEARISH',2,.25)['confirmed'])
  rows=self.bars();rows[-1]=(*rows[-1][:3],104,104.5)
  self.assertFalse(precision.inspect(rows,'BUY','BULLISH',2,.25)['confirmed'])
  rows=self.bars();rows[-2]=(*rows[-2][:1],104,106,103,104.2)
  self.assertFalse(precision.inspect(rows,'BUY','BULLISH',2,.25)['confirmed'])
 def test_mirrored_sell_sequence(self):
  rows=[(t,200-o,200-low,200-high,200-c) for t,o,high,low,c in self.bars()]
  self.assertTrue(precision.inspect(rows,'SELL','BEARISH',2,.25)['confirmed'])
if __name__=='__main__':unittest.main()

class RegistrationTests(unittest.TestCase):
 def opener(self,results,calls):
  class Response:
   status=200
   def __init__(self,result):self.result=result
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):
    import json
    return json.dumps({'ok':True,'result':self.result}).encode()
  def open_request(req,timeout):
   import json
   calls.append(json.loads(req.data) if req.data else None)
   return Response(results.pop(0))
  return open_request
 def test_registration_preserves_other_receiver(self):
  calls=[]
  state=bot.configure_webhook('fixture','s'*40,'https://example.onrender.com',{'123'},self.opener([{'url':'https://existing.example/receiver'}],calls))
  self.assertIn('لم يجر تغييره',state);self.assertEqual(len(calls),1)
 def test_registration_verifies_url_and_preserves_pending_updates(self):
  endpoint='https://example.onrender.com/v1/telegram/updates';calls=[]
  state=bot.configure_webhook('fixture','s'*40,'https://example.onrender.com',{'123'},self.opener([{'url':''},True,{'url':endpoint}],calls))
  self.assertEqual(state,'تم تسجيل المستقبل');self.assertFalse(calls[1]['drop_pending_updates'])
  self.assertEqual(calls[1]['secret_token'],'s'*40)
