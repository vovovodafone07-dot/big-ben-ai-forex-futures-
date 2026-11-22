import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from datetime import datetime,timedelta,timezone

ROOT=Path(__file__).resolve().parents[1]/'backend'
def load(name):
    spec=importlib.util.spec_from_file_location('tv_test_'+name,ROOT/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
t=load('tradingview_candles');h=load('market_history');g=load('connected_market')
NOW=datetime(2026,11,23,12,0,20,tzinfo=timezone.utc)
def payload(symbol='CAPITALCOM:US100'):
    return dict(schema='bigben.candle.v1',symbol=symbol,timeframe='5',time=NOW.isoformat(),
                bar_time='2026-11-23T11:55:00+00:00',open=100,high=103,low=99,close=102,tick_size=.1)

class ChartTransportTests(unittest.TestCase):
    def setUp(self):self.db=sqlite3.connect(':memory:');h.migrate(self.db)
    def tearDown(self):self.db.close()
    def test_any_qualified_asset_is_supported_without_external_feed(self):
        for symbol in ('CAPITALCOM:US100','OANDA:GBPUSD','CME_MINI:MNQ1!','COMEX_MINI:MGC1!','NASDAQ:AAPL','BITSTAMP:BTCUSD'):
            event=t.validate(payload(symbol),NOW)
            self.assertTrue(t.ingest(self.db,event,now=NOW))
            rows,meta=t.read(self.db,symbol)
            self.assertEqual(len(rows),1);self.assertTrue(t.fresh(meta,NOW))
            self.assertFalse(meta['realtime_verified'])
            p=dict(symbol=symbol,source_time=event['bar_time'],provider=t.PROVIDER,source_provenance=meta,asset_class='cfd')
            self.assertTrue(g.gate(p,NOW)['open'])
    def test_duplicates_do_not_extend_watermark_or_change_closed_ohlc(self):
        event=t.validate(payload(),NOW)
        self.assertTrue(t.ingest(self.db,event,now=NOW))
        self.assertFalse(t.ingest(self.db,event,now=NOW+timedelta(minutes=1)))
        rows,meta=t.read(self.db,event['symbol'])
        self.assertEqual(meta['last_received_at'],NOW.isoformat())
        self.assertFalse(t.fresh(meta,NOW+timedelta(minutes=6)))
        event['candle']['high']=104
        with self.assertRaises(ValueError):t.ingest(self.db,event,now=NOW)
        self.assertEqual(t.read(self.db,event['symbol'])[0],rows)
    def test_late_future_naive_and_close_only_events_rejected(self):
        for change in [dict(time=(NOW-timedelta(minutes=4)).isoformat()),dict(time=(NOW+timedelta(seconds=1)).isoformat()),dict(bar_time='2026-11-23T11:55:00'),dict(high=None),dict(open=None),dict(timeframe='15'),dict(symbol='MNQ')]:
            with self.assertRaises(ValueError):t.validate(dict(payload(),**change),NOW)
    def test_closed_weekend_not_overridden_by_fresh_webhook(self):
        sunday=datetime(2026,11,22,12,0,20,tzinfo=timezone.utc)
        d=dict(payload('OANDA:GBPUSD'),time=sunday.isoformat(),bar_time='2026-11-22T11:55:00+00:00')
        event=t.validate(d,sunday);t.ingest(self.db,event,now=sunday)
        rows,meta=t.read(self.db,event['symbol'])
        plan=dict(symbol=event['symbol'],provider=t.PROVIDER,source_time=meta['last_candle'],source_provenance=meta,asset_class='forex')
        self.assertFalse(g.gate(plan,sunday)['open'])
        plan['asset_class']='crypto';self.assertTrue(g.gate(plan,sunday)['open'])
    def test_source_time_cannot_be_replaced_with_receipt_time(self):
        event=t.validate(payload(),NOW);t.ingest(self.db,event,now=NOW)
        _,meta=t.read(self.db,event['symbol'])
        plan=dict(symbol=event['symbol'],provider=t.PROVIDER,source_time=meta['last_received_at'],source_provenance=meta,asset_class='cfd')
        self.assertFalse(g.gate(plan,NOW)['open'])
        plan['source_time']=meta['last_candle'];plan['symbol']='CAPITALCOM:US500'
        self.assertFalse(g.gate(plan,NOW)['open'])

if __name__=='__main__':unittest.main()
