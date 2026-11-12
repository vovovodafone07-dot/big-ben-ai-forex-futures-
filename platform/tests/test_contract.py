"""Non-trading contract checks for the Big Ben webhook and observational outcomes."""
import unittest,sys,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import app
from datetime import datetime,timezone
class Contracts(unittest.TestCase):
 def test_heartbeat_contract(self):
  d={"schema":"bigben.v1","event":"HEARTBEAT","event_id":"CME_MINI:MNQ1_-1794400000000-HEARTBEAT","symbol":"CME_MINI:MNQ1!","time":datetime.now(timezone.utc).isoformat(),"close":28208.75,"m15":1,"h1":1,"h4":1}
  self.assertEqual(app.validate(d),d)
 def test_reject_nested_symbol_json(self):
  d={"schema":"bigben.v1","event":"HEARTBEAT","event_id":"CME_MINI:MNQ1_-1794400000000-HEARTBEAT","symbol":'{"adjustment":"default"}',"time":datetime.now(timezone.utc).isoformat()}
  with self.assertRaises(ValueError):app.validate(d)
 def test_buy_sell_rr(self):
  for side,entry,sl,tp in [("BUY",100,98,106),("SELL",100,102,94)]:
   d={"schema":"bigben.v1","event":side,"event_id":"EURUSD-1794400000000-"+side,"symbol":"OANDA:EURUSD","time":datetime.now(timezone.utc).isoformat(),"entry":entry,"sl":sl,"tp":tp,"rr":3}
   self.assertEqual(app.validate(d),d)
 def test_reject_bad_trade_levels(self):
  d={"schema":"bigben.v1","event":"BUY","event_id":"EURUSD-1794400000000-BUY","symbol":"OANDA:EURUSD","time":datetime.now(timezone.utc).isoformat(),"entry":100,"sl":102,"tp":106,"rr":3}
  with self.assertRaises(ValueError):app.validate(d)
 def test_research_requires_sufficient_evidence(self):
  original=app.evaluate_signals
  app.evaluate_signals=lambda limit=100:{"signals":[{"symbol":"OANDA:EURUSD","event":"BUY","outcome":"unresolved"}]}
  try:
   report=app.research_report()
   self.assertEqual(report["status"],"insufficient_evidence")
   self.assertEqual(report["observed_outcomes"],0)
   self.assertEqual(report["by_symbol"]["OANDA:EURUSD"]["unresolved"],1)
  finally:app.evaluate_signals=original
 def test_outcome_is_not_fabricated(self):
  original=app.list_events
  app.list_events=lambda limit=2000,kind="all":[]
  try:
   result=app.evaluate_signals()
   self.assertEqual(result["count"],0)
   self.assertEqual(result["tp_close_observed"],0)
  finally:app.list_events=original
if __name__=="__main__":unittest.main()
