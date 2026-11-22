"""Offline delivery ordering, durable claims, management events and old backups."""
import importlib.util
import sqlite3
import tempfile
import unittest
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'backend'
def load(name):
    spec=importlib.util.spec_from_file_location('workflow_'+name,ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
app=load('app')
telegram=app._instant_telegram
journal=app._native_trade_journal
NOW=datetime.now(timezone.utc)
def plan():
    return dict(symbol='BITSTAMP:BTCUSD',provider='Bitstamp',instrument={'asset_class':'crypto'},
        status='READY',mode='scalp',technical_direction='BUY',entry=100,sl=90,
        targets=[{'price':110},{'price':120},{'price':130}],broker_execution=False,
        source_time=(NOW-timedelta(minutes=5)).isoformat(),confirmation={'confirmed':True,'level':100})

class ImmediateThread:
    def __init__(self,target,args=(),**kwargs):self.target,self.args=target,args
    def start(self):self.target(*self.args)

class DeliveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'DATABASE_URL':'','TELEGRAM_BOT_TOKEN':'offline-fixture','BIGBEN_NATIVE_TELEGRAM_ENABLED':'1'})
        self.env.start()
        self.db_patch=patch.object(app,'DB',Path(self.temp.name)/'fixture.sqlite3');self.db_patch.start()
        app.init()
    def tearDown(self):
        self.db_patch.stop();self.env.stop();self.temp.cleanup()

    def test_trade_then_analysis_once_with_separate_receipts(self):
        captured=[]
        def send(p,token,chat,**kw):captured.append(kw.get('category','trade'));return 'sent'
        with patch.object(app,'telegram_destination',return_value='12345678'),patch.object(telegram,'send',side_effect=send),patch.object(app.threading,'Thread',ImmediateThread):
            self.assertEqual(app.trigger_instant_telegram(plan())['status'],'sending')
            self.assertEqual(app.trigger_instant_telegram(plan())['status'],'duplicate')
        self.assertEqual(captured,['trade','analysis'])
        with app.history_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM native_telegram_alerts WHERE delivery='sent'").fetchone()[0],2)
            self.assertEqual(len(journal.recent(db)),1)

    def test_100_concurrent_claims_and_reopen_have_one_winner(self):
        def claim(_):
            with app.history_connection() as db:return telegram.claim(db,plan(),'12345678')
        with ThreadPoolExecutor(max_workers=16) as pool:winners=list(pool.map(claim,range(100)))
        self.assertEqual(sum(x is not None for x in winners),1)
        app.init()
        self.assertIsNone(claim(0))

    def test_uncertain_delivery_cannot_be_claimed_again(self):
        with app.history_connection() as db:
            key=telegram.claim(db,plan(),'12345678');telegram.finish(db,key,'uncertain')
        with app.history_connection() as db:
            self.assertIsNone(telegram.claim(db,plan(),'12345678'))
            self.assertIsNone(telegram.claim_companion(db,plan(),'12345678','12345678'))
        def timeout(*a,**kw):raise TimeoutError()
        self.assertEqual(telegram.send(plan(),'offline-fixture','12345678',opener=timeout),'uncertain')

    def test_unconfirmed_ready_is_not_a_trade(self):
        p=plan();p['confirmation']['confirmed']=False
        self.assertFalse(telegram.eligible(p))
        p=plan();p['status']='CONDITIONAL'
        with patch.object(telegram,'send') as send:
            self.assertEqual(app.trigger_instant_telegram(p)['status'],'not_eligible');send.assert_not_called()

    def test_muted_destination_keeps_analysis_running_without_dispatch(self):
        with app.history_connection() as db:
            db.execute("INSERT INTO telegram_bot_receipts(id,status,created_at) VALUES (?,?,?)",('mute:12345678','muted',NOW.isoformat()))
        app.init()
        with patch.object(app,'telegram_destination',return_value='12345678'),patch.object(telegram,'send') as send:
            self.assertEqual(app.trigger_instant_telegram(plan())['status'],'disabled')
            self.assertEqual(app.send_telegram_message('تحديث سوق',category='market'),'not_configured')
            send.assert_not_called()

    def test_target_jump_enqueues_each_target_in_order_and_never_repeats(self):
        p=plan();bar=(NOW.isoformat(),100,135,99,134)
        later=NOW+timedelta(minutes=5)
        with app.history_connection() as db:
            journal.store(db,p,now=NOW)
            transitions=journal.follow(db,p['symbol'],[bar],now=later)
            self.assertEqual([e['state'] for e in transitions],['الهدف الأول تحقق','الهدف الثاني تحقق','الهدف الثالث تحقق'])
        with app.history_connection() as db:
            self.assertEqual(journal.follow(db,p['symbol'],[bar],now=later),[])
            events=journal.claim_notifications(db)
            self.assertEqual([e['state'] for e in events],[e['state'] for e in transitions])
        with app.history_connection() as db:self.assertEqual(journal.claim_notifications(db),[])

    def test_same_bar_stop_and_target_only_reports_ambiguity(self):
        p=plan()
        with app.history_connection() as db:
            journal.store(db,p,now=NOW)
            events=journal.follow(db,p['symbol'],[(NOW.isoformat(),100,135,85,105)],now=NOW+timedelta(minutes=5))
            self.assertEqual([e['state'] for e in events],['نتيجة غير محسومة'])

    def test_morning_digest_is_durable_once_per_destination_and_day(self):
        now=datetime(2026,11,22,3,0,tzinfo=timezone.utc)
        with patch.object(app,'telegram_destination',return_value='12345678'),patch.object(app,'send_telegram_message',return_value='sent') as send:
            app.deliver_bot_news({},now)
            app.init()
            app.deliver_bot_news({},now)
            self.assertEqual(send.call_count,1)
            self.assertIn('2026-11-22',send.call_args.args[0])

    def test_news_callback_uses_platform_engine_without_trade_dispatch(self):
        asset={'symbol':'COMEX_MINI:MGCZ26','asset_class':'futures'}
        update={'update_id':902,'callback_query':{'from':{'id':12345678},'message':{'chat':{'id':12345678,'type':'private'}},'data':'news_pick:'+app._telegram_interactive.token(asset['symbol'])}}
        with patch.dict(os.environ,{'BIGBEN_TELEGRAM_ALLOWED_USER_IDS':'12345678'}),patch.object(app._connected_market,'connected',return_value=[asset]),patch.object(app,'tracked_asset_catalog',return_value=[]),patch.object(app._news,'snapshot',return_value={}),patch.object(app,'analyze_instant_native',return_value={'symbol':asset['symbol'],'status':'DATA_UNAVAILABLE'}) as engine,patch.object(app,'trigger_instant_telegram') as trade,patch.object(app,'send_bot_payload',return_value='sent') as send:
            app.process_bot_update(update)
            engine.assert_called_once_with(asset['symbol'],'scalp');trade.assert_not_called()
            self.assertIn('تحليل تداول الأخبار المهمة',send.call_args.args[0]['text'])
            app.process_bot_update(update)
            self.assertEqual(send.call_count,1)

    def test_new_backup_preserves_delivery_ledger_and_old_backup_still_restores(self):
        with app.history_connection() as db:telegram.claim(db,plan(),'12345678')
        with app.history_connection() as db:bundle=app._backup.snapshot(db)
        self.assertEqual(bundle['schema'],'bigben.application-backup.v3')
        self.assertIn('native_management_outbox',bundle['tables'])
        original=app.DB
        app.DB=Path(self.temp.name)/'restore.sqlite3';app.init()
        with app.history_connection() as db:app._backup.restore_new_database(db,bundle)
        with app.history_connection() as db:self.assertIsNone(telegram.claim(db,plan(),'12345678'))
        import copy
        version2=copy.deepcopy(bundle)
        version2['schema']='bigben.application-backup.v2'
        version2['tables']={k:v for k,v in version2['tables'].items() if k in app._backup.V2_TABLES}
        version2['row_count']=sum(len(t['rows']) for t in version2['tables'].values())
        app.DB=Path(self.temp.name)/'version2.sqlite3';app.init()
        with app.history_connection() as db:app._backup.restore_new_database(db,version2)
        bundle['schema']='bigben.application-backup.v1'
        bundle['tables']={k:v for k,v in bundle['tables'].items() if k in app._backup.LEGACY_TABLES}
        bundle['row_count']=sum(len(t['rows']) for t in bundle['tables'].values())
        app.DB=Path(self.temp.name)/'legacy.sqlite3';app.init()
        with app.history_connection() as db:app._backup.restore_new_database(db,bundle)
        app.DB=original

if __name__=='__main__':unittest.main()
