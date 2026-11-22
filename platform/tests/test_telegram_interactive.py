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
  self.assertEqual(len(buttons),9)
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
 def test_watchlist_catalog_never_promotes_disconnected_futures(self):
  symbol='CME_MINI:NQ1!'
  update={'update_id':1,'callback_query':{'from':{'id':12345678},'message':{'chat':{'id':12345678,'type':'private'}},'data':'tracked:0'}}
  def run(data):
   return bot.handle(self.db,data,allowed_users={'12345678'},connected=lambda:self.assets,news=lambda:{},journal=lambda:[],tracked=lambda:[{'symbol':symbol,'connected':False,'market_state':'مصدر غير متصل'}],now=NOW)
  reply=run(update)
  buttons=[b for row in reply['reply_markup']['inline_keyboard'] for b in row]
  self.assertTrue(any(b['callback_data']=='info:'+bot.token(symbol) for b in buttons))
  update['update_id']=2;update['callback_query']['data']='info:'+bot.token(symbol)
  self.assertIn('مصدر غير متصل',run(update)['text'])

 def test_news_opt_in_and_out_persist(self):
  self.run_update('news:on');self.assertEqual(self.db.execute('SELECT news_enabled FROM telegram_bot_state').fetchone()[0],1)
  self.run_update('news:off',2);self.assertEqual(self.db.execute('SELECT news_enabled FROM telegram_bot_state').fetchone()[0],0)
 def test_mute_is_durable_scoped_and_duplicate_does_not_toggle(self):
  self.run_update('notifications')
  self.assertTrue(bot.muted(self.db,'12345678'));self.assertFalse(bot.muted(self.db,'other'))
  self.assertIsNone(self.run_update('notifications'))
  self.assertTrue(bot.muted(self.db,'12345678'))
  self.run_update('notifications',2);self.assertFalse(bot.muted(self.db,'12345678'))
 def test_trade_buttons_are_bound_to_unique_journal_record(self):
  ident='a'*64;record={'id':ident,'symbol':self.assets[0]['symbol'],'mode':'swing','state':'الهدف الأول تحقق','updated_at':NOW.isoformat()}
  def run(action,identnum,records):
   update={'update_id':identnum,'callback_query':{'from':{'id':12345678},'message':{'chat':{'id':12345678,'type':'private'}},'data':action}}
   return bot.handle(self.db,update,allowed_users={'12345678'},connected=lambda:self.assets,news=lambda:{},journal=lambda:records,now=NOW)
  action='trade:view:'+ident[:24]
  self.assertTrue(run(action,1,[record])['analysis_request']['read_only'])
  self.assertNotIn('read_only',run('trade:new:'+ident[:24],2,[record])['analysis_request'])
  r=run('trade:state:'+ident[:24],3,[record]);self.assertIsNone(r['analysis_request']);self.assertIn('الهدف الأول تحقق',r['text'])
  self.assertIsNone(run(action,4,[record,dict(record,id='a'*24+'b'*40)])['analysis_request'])
  self.assertIsNone(run('trade:new:forged',5,[record])['analysis_request'])
 def test_news_picker_separate_from_trade_and_rechecks_connection(self):
  self.assets.append({'symbol':'BITSTAMP:BTCUSD','asset_class':'crypto'})
  reply=self.run_update('news_symbols:0')
  data=[b['callback_data'] for row in reply['reply_markup']['inline_keyboard'] for b in row]
  self.assertNotIn('news_pick:'+bot.token('BITSTAMP:BTCUSD'),data)
  reply=self.run_update('news_pick:'+bot.token(self.assets[0]['symbol']),2)
  self.assertIsNone(reply['analysis_request']);self.assertEqual(reply['news_request']['symbol'],self.assets[0]['symbol'])
  self.assets=[]
  reply=self.run_update('news_pick:'+bot.token('COMEX_MINI:MGCZ26'),3)
  self.assertIsNone(reply['news_request'])
 def test_news_view_excludes_stale_foreign_events_and_unverified_prices(self):
  event={'time':NOW.isoformat(),'feed_fresh':True,'feed_state':'CONNECTED','title':'CPI','currency':'USD'}
  snapshot={'calendar':[event,dict(event,currency='EUR',title_ar='خبر أجنبي'),dict(event,feed_fresh=False,title_ar='خبر قديم')]}
  plan={'symbol':'COMEX_MINI:MGCZ26','status':'READY','realtime_verified':False,'source_age_seconds':0,'indicators':{'PDH_UTC':987654}}
  text=bot.important_news_analysis(plan['symbol'],snapshot,plan,NOW)
  self.assertNotIn('987654',text);self.assertNotIn('خبر أجنبي',text);self.assertNotIn('خبر قديم',text)
  self.assertIn('🔵',text);self.assertIn('🔴',text);self.assertIn('غير موثق',text)
  plan.update(realtime_verified=True,source_age_seconds=30)
  self.assertIn('987654',bot.important_news_analysis(plan['symbol'],snapshot,plan,NOW))
  plan['source_age_seconds']=181
  self.assertNotIn('987654',bot.important_news_analysis(plan['symbol'],snapshot,plan,NOW))
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
