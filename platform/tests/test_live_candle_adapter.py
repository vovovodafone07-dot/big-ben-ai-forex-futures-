import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

ROOT=Path(__file__).resolve().parents[1]/'backend'
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
a=load('live_candle_adapter');w=load('tv_watchlist');h=load('market_history');b=load('telegram_interactive');s=load('tradingview_dynamic_sync');g=load('connected_market')
NOW=datetime(2026,11,22,18,2,tzinfo=timezone.utc)
SYMBOL='CME_MINI:MNQ1!'
def bars(stamp=None):
    return [dict(time=(stamp or NOW-timedelta(minutes=7)).isoformat(),open=100,high=103,low=99,close=101)]

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');h.migrate(self.db);b.migrate(self.db);s.migrate(self.db)
    def tearDown(self):self.db.close()
    def test_futures_identity_and_no_broker_or_expiry_proxy(self):
        self.assertEqual(a.mapping(SYMBOL)['yahoo'],'MNQ=F')
        self.assertEqual(a.mapping('COMEX_MINI:MGC1!')['yahoo'],'MGC=F')
        self.assertIsNone(a.mapping('CAPITALCOM:US100'))
        self.assertIsNone(a.mapping('FOREXCOM:XAUUSD'))
        self.assertIsNone(a.mapping('CME_MINI:MNQZ26'))
    def test_closed_only_and_utc_alignment(self):
        self.assertEqual(a.normalize(bars(),NOW),bars())
        for item in [dict(bars()[0],time='2026-11-22T18:00:00'),dict(bars()[0],high=True),dict(bars()[0],high=float('inf')),dict(bars()[0],time='2026-11-22T17:56:00+00:00')]:
            with self.assertRaises(a.CandleError):a.normalize([item],NOW)
        with self.assertRaises(a.CandleError):a.normalize(bars(NOW-timedelta(minutes=2)),NOW)
        with self.assertRaises(a.CandleError):a.normalize(bars()+bars(),NOW)
    def test_fallback_on_primary_failure_is_reference_not_live(self):
        def denied(*args):raise a.CandleError('entitlement')
        rows,meta=a.fetch(SYMBOL,'fixture',NOW,primary=denied,fallback=lambda *x:(bars(),'yfinance / Yahoo Finance','MNQ=F'))
        self.assertTrue(meta['fresh']);self.assertFalse(meta['realtime_verified'])
        self.assertFalse(meta['exact_feed_verified']);self.assertTrue(meta['reference_only'])
        self.assertEqual(len(meta['errors']),1)
        self.assertFalse(g.gate(dict(meta,source_time=rows[-1]['time']),NOW)['open'])
        a.store(self.db,SYMBOL,rows,meta)
        saved,record=a.read(self.db,SYMBOL)
        self.assertEqual(record,meta);self.assertEqual(saved[0][0],rows[0]['time'])
    def test_stale_primary_tries_fallback_without_faking_freshness(self):
        old=bars(NOW.replace(hour=15,minute=0))
        def failed(*x):raise a.CandleError('rate_limit')
        rows,meta=a.fetch('OANDA:GBPUSD','fixture',NOW,primary=lambda *x:(old,'Twelve Data','GBP/USD'),fallback=failed)
        self.assertEqual(meta['state'],'STALE');self.assertFalse(meta['fresh']);self.assertEqual(rows,old)
        self.assertEqual(len(meta['errors']),2)
    def test_twelve_rejects_wrong_symbol_even_with_valid_ohlc(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*x):pass
            def read(self,*x):return json.dumps({'meta':{'symbol':'EUR/USD','interval':'5min','type':'Physical Currency'},'values':[]}).encode()
        with self.assertRaisesRegex(a.CandleError,'identity'):
            a.twelve('OANDA:GBPUSD','private-key',NOW,opener=lambda *x,**kw:Response())
    def test_yahoo_rejects_full_contract_for_micro_and_bad_interval(self):
        class Ticker:
            def history(self,**kw):return None
            def get_history_metadata(self):return {'symbol':'NQ=F','instrumentType':'FUTURE','exchangeName':'CME','dataGranularity':'5m'}
        with self.assertRaisesRegex(a.CandleError,'identity'):a.yahoo(SYMBOL,NOW,factory=lambda x:Ticker())
    def test_budget_survives_commit_and_rejects_per_minute_overflow(self):
        for i in range(6):self.assertTrue(a.reserve(self.db,'twelve',NOW))
        self.db.commit();self.assertFalse(a.reserve(self.db,'twelve',NOW))
        self.assertTrue(a.reserve(self.db,'twelve',NOW+timedelta(minutes=2)))
        # The same receipt namespace is reused after startup/migration.
        b.migrate(self.db);self.assertEqual(self.db.execute("SELECT COUNT(*) FROM telegram_bot_receipts").fetchone()[0],7)
        for i in range(7,400):self.db.execute('INSERT INTO telegram_bot_receipts VALUES (?,?,?)',('candles:twelve:2026-11-22:'+str(i),'reserved',NOW.isoformat()))
        self.assertFalse(a.reserve(self.db,'twelve',NOW+timedelta(hours=1)))
    def test_snapshot_authority_revision_replay_and_empty_preservation(self):
        payload=dict(schema='bigben.watchlist.v1',revision=1,watchlist_id='207266246',symbols=[SYMBOL])
        first=w.sync(self.db,payload,now=NOW)
        self.assertEqual(w.sync(self.db,payload,now=NOW+timedelta(seconds=2)),first)
        self.assertEqual(w.members(self.db,['OANDA:EURUSD']),{SYMBOL})
        for bad in [dict(payload,symbols=[]),dict(payload,symbols=['NQ']),dict(payload,revision=0),dict(payload,symbols=['OANDA:EURUSD'])]:
            with self.assertRaises(ValueError):w.sync(self.db,bad)
        self.assertEqual(w.members(self.db),{SYMBOL})
    def test_alerts_do_not_expand_watchlist_without_a_new_authorized_snapshot(self):
        s.record_symbol(self.db,{'symbol':'OANDA:EURUSD'},authenticated=True,now=NOW-timedelta(days=2))
        w.sync(self.db,dict(schema='bigben.watchlist.v1',revision=1,watchlist_id='207266246',symbols=[SYMBOL]),now=NOW)
        self.assertNotIn('OANDA:EURUSD',w.members(self.db))
        s.record_symbol(self.db,{'symbol':'OANDA:USDJPY'},authenticated=True,now=NOW+timedelta(seconds=2))
        self.assertEqual(w.members(self.db),{SYMBOL})
        w.sync(self.db,dict(schema='bigben.watchlist.v1',revision=2,watchlist_id='207266246',symbols=[SYMBOL,'OANDA:USDJPY']),now=NOW+timedelta(seconds=3))
        self.assertEqual(w.members(self.db),{SYMBOL,'OANDA:USDJPY'})
    def test_weekend_open_is_dst_aware_not_stale_quote_override(self):
        self.assertTrue(g.forex_weekly_closed(NOW))
        self.assertEqual(g.next_forex_open(NOW),'2026-11-23T02:00:00+04:00')
        summer=datetime(2026,7,5,12,tzinfo=timezone.utc)
        self.assertEqual(g.next_forex_open(summer),'2026-07-06T01:00:00+04:00')

if __name__=='__main__':unittest.main()
