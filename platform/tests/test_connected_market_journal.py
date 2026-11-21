"""Offline regression for connected-only picker, contract specs and research lifecycle."""
import importlib.util, sqlite3, json, unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1]/"backend"
def load(name):
 spec=importlib.util.spec_from_file_location("test_"+name,ROOT/(name+".py"))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module
connected=load("connected_market")
journal=load("native_trade_journal")
instruments=load("instruments")
NOW=datetime(2026,11,22,3,10,tzinfo=timezone.utc)
def plan():
 return {"status":"READY","symbol":"BITSTAMP:BTCUSD","mode":"scalp",
         "technical_direction":"BUY","entry":60000,"sl":59900,
         "source_time":(NOW-timedelta(minutes=10)).isoformat(),
         "provider":"Bitstamp","confirmation":{"confirmed":True,"level":60000},
         "targets":[{"price":60100},{"price":60200},{"price":60300}]}
class ConnectedMarketJournalTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(":memory:")
  self.db.execute("CREATE TABLE market_history_checks(symbol TEXT PRIMARY KEY,payload TEXT)")
  self.db.execute("CREATE TABLE market_candles(provider TEXT,symbol TEXT,time TEXT)")
  connected.migrate(self.db);journal.migrate(self.db)
 def tearDown(self):self.db.close()
 def test_no_futures_from_watchlist_or_unverified_feed(self):
  self.assertEqual(connected.connected(self.db,NOW),[])
  self.assertFalse(connected.gate({"symbol":"CME_MINI:NQ1!","status":"READY","provider":"Barchart OnDemand","source_time":NOW.isoformat()},NOW)["open"])
 def test_verified_data_is_connected_even_when_closed_but_not_live(self):
  latest=NOW-timedelta(minutes=10)
  source={"symbol":"EUR/USD","interval":"5min","adapter_version":"v1","state":"CONNECTED"}
  self.db.execute("INSERT INTO market_history_checks VALUES (?,?)",("EUR/USD",json.dumps(source)))
  self.db.executemany("INSERT INTO market_candles VALUES (?,?,?)",
      [("Twelve Data","EUR/USD",(latest-timedelta(minutes=5*i)).isoformat()) for i in range(110)])
  symbols=connected.connected(self.db,NOW)
  self.assertEqual(len(symbols),1)
  self.assertEqual(symbols[0]["symbol"],"OANDA:EURUSD")
  self.assertFalse(symbols[0]["fresh"])
 def test_gate_prevents_closed_market_and_allows_recent_spot(self):
  p=plan()
  self.assertTrue(connected.gate(p,NOW)["open"])
  self.assertFalse(connected.gate(p,NOW+timedelta(hours=1))["open"])
 def test_market_open_alert_only_on_transition(self):
  self.assertIsNone(connected.record_open_state(self.db,"BITSTAMP:BTCUSD",False))
  self.assertEqual(connected.record_open_state(self.db,"BITSTAMP:BTCUSD",True),"opened")
  self.assertIsNone(connected.record_open_state(self.db,"BITSTAMP:BTCUSD",True))
 def test_contract_month_and_tick_metadata_do_not_claim_feed(self):
  self.assertEqual(instruments.normalize("NQZ26"),"CME_MINI:NQZ26")
  self.assertEqual(instruments.normalize("MGCZ26"),"COMEX_MINI:MGCZ26")
  self.assertEqual(instruments.futures_tick("NQZ26")["price_tick"],.25)
  self.assertEqual(instruments.futures_tick("MGC")["price_tick"],.1)
  self.assertFalse(instruments.futures_tick("NQ")["entitlement_verified"])
 def test_journal_deduplicates_and_tracks_future_closed_target(self):
  p=plan();ident=journal.store(self.db,p,now=NOW)
  self.assertIsNotNone(ident)
  self.assertIsNone(journal.store(self.db,p,now=NOW))
  btime=NOW-timedelta(minutes=5)
  events=journal.follow(self.db,"BITSTAMP:BTCUSD",
     [(btime.isoformat(),59990,60120,59980,60105)],now=NOW)
  self.assertTrue(any(e["state"]=="الهدف الأول تحقق" for e in events))
  self.assertEqual(journal.follow(self.db,"BITSTAMP:BTCUSD",
     [(btime.isoformat(),59990,60120,59980,60105)],now=NOW),[])
  self.assertEqual(journal.recent(self.db)[0]["tp_count"],1)
 def test_simultaneous_tp_and_sl_marks_ambiguous(self):
  p=plan();journal.store(self.db,p,now=NOW)
  btime=NOW-timedelta(minutes=5)
  events=journal.follow(self.db,"BITSTAMP:BTCUSD",
     [(btime.isoformat(),60000,60150,59850,60001)],now=NOW)
  self.assertTrue(any(e["state"]=="نتيجة غير محسومة" for e in events))
if __name__=="__main__":unittest.main()
