"""Bitstamp public spot OHLC adapter regression tests, offline synthetic fixtures only."""
import importlib.util
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
import sqlite3

spec=importlib.util.spec_from_file_location("crypto_test",Path(__file__).resolve().parents[1]/"backend"/"crypto_history.py")
crypto=importlib.util.module_from_spec(spec);spec.loader.exec_module(crypto)
NOW=datetime(2026,11,22,0,15,tzinfo=timezone.utc)

class Reply:
    def __init__(self,body):self.body=json.dumps(body).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.body[:n]

def data(symbol="BTC/USD",count=1000):
    t0=int((NOW-timedelta(minutes=5*(count+2))).timestamp())
    return {"data":{"pair":symbol,"ohlc":[{"timestamp":str(t0+i*300),"open":str(100+i),"high":str(101+i),"low":str(99+i),"close":str(100+i)} for i in range(count)]}}

class CryptoHistoryTests(unittest.TestCase):
    def test_parse_bitstamp_real_symbol_and_closed_bars(self):
        urls=[]
        def open_fixture(req,timeout):urls.append(req.full_url);return Reply(data())
        bars,meta=crypto.fetch_m5("BITSTAMP:BTCUSD",NOW,open_fixture)
        self.assertEqual(len(bars),1000)
        self.assertEqual(meta["provider"],"Bitstamp")
        self.assertEqual(meta["symbol"],"BITSTAMP:BTCUSD")
        self.assertFalse(meta["realtime_verified"])
        self.assertIn("exclude_current_candle=true",urls[0])
        self.assertIn("/ohlc/btcusd/",urls[0])
    def test_filter_current_unclosed_candle(self):
        d=data(count=2)
        d["data"]["ohlc"][-1]["timestamp"]=str(int(NOW.timestamp()))
        bars,meta=crypto.fetch_m5("BITSTAMP:BTCUSD",NOW,lambda req,timeout:Reply(d))
        self.assertEqual(len(bars),1)
        self.assertEqual(meta["incomplete_candles_excluded"],1)
    def test_provider_identity_mismatch_never_relabels(self):
        with self.assertRaisesRegex(crypto.CryptoHistoryError,"instrument_metadata_mismatch"):
            crypto.fetch_m5("BITSTAMP:BTCUSD",NOW,lambda req,timeout:Reply(data("ETH/USD")))
    def test_no_proxy_exchange(self):
        for x in ("BINANCE:BTCUSDT","CME:MBT1!","OANDA:EURUSD","BITSTAMP:../../etc","BITSTAMP:btcUSD"):
            with self.assertRaises(crypto.CryptoHistoryError):crypto.pair_from_symbol(x)
    def test_invalid_high_low_rejected(self):
        d=data(count=10);d["data"]["ohlc"][0]["low"]="105"
        with self.assertRaisesRegex(crypto.CryptoHistoryError,"invalid_candle"):
            crypto.fetch_m5("BITSTAMP:BTCUSD",NOW,lambda req,timeout:Reply(d))
    def test_persists_with_true_exchange_identity(self):
        c=sqlite3.connect(":memory:")
        try:
            c.execute("CREATE TABLE market_candles (provider TEXT,symbol TEXT,time TEXT,open FLOAT,high FLOAT,low FLOAT,close FLOAT,received_at TEXT,PRIMARY KEY(provider,symbol,time))")
            c.execute("CREATE TABLE market_history_checks (symbol TEXT PRIMARY KEY,checked_at TEXT,payload TEXT)")
            rows,meta=crypto.fetch_m5("BITSTAMP:BTCUSD",NOW,lambda req,timeout:Reply(data(count=10)))
            crypto.store_check(c,"BITSTAMP:BTCUSD",meta,rows)
            self.assertEqual(c.execute("SELECT DISTINCT provider,symbol FROM market_candles").fetchone(),("Bitstamp","BITSTAMP:BTCUSD"))
        finally:c.close()

if __name__=="__main__":unittest.main()
