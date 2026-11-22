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

    def test_new_backup_preserves_delivery_ledger_and_old_backup_still_restores(self):
        with app.history_connection() as db:telegram.claim(db,plan(),'12345678')
        with app.history_connection() as db:bundle=app._backup.snapshot(db)
        self.assertEqual(bundle['schema'],'bigben.application-backup.v2')
        self.assertIn('native_management_outbox',bundle['tables'])
        original=app.DB
        app.DB=Path(self.temp.name)/'restore.sqlite3';app.init()
        with app.history_connection() as db:app._backup.restore_new_database(db,bundle)
        with app.history_connection() as db:self.assertIsNone(telegram.claim(db,plan(),'12345678'))
        bundle['schema']='bigben.application-backup.v1'
        bundle['tables']={k:v for k,v in bundle['tables'].items() if k in app._backup.LEGACY_TABLES}
        bundle['row_count']=sum(len(t['rows']) for t in bundle['tables'].values())
        app.DB=Path(self.temp.name)/'legacy.sqlite3';app.init()
        with app.history_connection() as db:app._backup.restore_new_database(db,bundle)
        app.DB=original

if __name__=='__main__':unittest.main()
