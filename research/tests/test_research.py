"""Offline unit tests: never use external market data or trade execution."""
import io,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from barchart_adapter import get_m5,validated_symbol,load_requested_symbols
from run_provider_research import generate
from daily_agents import agent_quality,backtest

class ResearchTests(unittest.TestCase):
 def test_missing_license_is_explicit(self):
  with patch.dict(os.environ,{"BARCHART_API_KEY":"","BIGBEN_BARCHART_SYMBOL_MAP":""}):
   r=generate()
  self.assertEqual(r["status"],"awaiting_data_access")
  self.assertFalse(r["symbols"])
 def test_invalid_symbol_rejected(self):
  for bad in ("../secret","NQ;rm -rf","",None):
   with self.assertRaises(ValueError):validated_symbol(bad)
 def test_mapping_must_be_explicit(self):
  with patch.dict(os.environ,{"BIGBEN_BARCHART_SYMBOL_MAP":'{"EURUSD":"^EURUSD"}'}):
   self.assertEqual(load_requested_symbols(),{"EURUSD":"^EURUSD"})
 def test_historical_response_is_validated(self):
  start=datetime(2026,11,10,tzinfo=timezone.utc)
  candles=[{"timestamp":(start+timedelta(minutes=5*i)).isoformat(),"open":100,"high":101,"low":99,"close":100} for i in range(130)]
  body=json.dumps({"status":{"code":200,"message":"Success"},"results":candles}).encode()
  with patch("barchart_adapter.urllib.request.urlopen",return_value=io.BytesIO(body)):
   rows=get_m5("^EURUSD","fake-test-only",days=3)
  self.assertEqual(len(rows),130)
  self.assertEqual(rows[0]["close"],100.0)
 def test_no_fabricated_trades(self):
  rows=[{"time":str(i),"open":100.0,"high":100.1,"low":99.9,"close":100.0} for i in range(140)]
  trades=backtest(rows)
  self.assertEqual(len(trades),0)
  self.assertIsNone(agent_quality(trades)["win_rate"])

if __name__=="__main__":unittest.main()
