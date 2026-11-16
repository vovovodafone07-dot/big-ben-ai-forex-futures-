"""Synthetic arithmetic and stale-signal regressions; no live trading."""
import importlib.util
import json
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

spec=importlib.util.spec_from_file_location("scalp",Path(__file__).resolve().parents[1]/"backend"/"scalping.py")
scalp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(scalp)

class ScalpTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,13,12,tzinfo=timezone.utc)
        self.buy={"event":"BUY","entry":100,"sl":98,"tp":106,"rr":3}
        self.sell={"event":"SELL","entry":100,"sl":102,"tp":94,"rr":3}
    def row(self,data=None,minutes=1,event=None,**extra):
        data={**(data or self.buy),**extra}
        return ("EURUSD",event or data["event"],(self.now-timedelta(minutes=minutes)).isoformat(),json.dumps(data))
    def test_full_trade_preserved_and_both_directions_supported(self):
        for data,target in ((self.buy,102),(self.sell,98)):
            pair=scalp.levels(data)
            self.assertEqual(pair["full_trade"]["tp"],data["tp"])
            self.assertEqual(pair["scalp"]["tp"],target)
            self.assertEqual(pair["scalp"]["sl"],data["sl"])
    def test_target_never_exceeds_original_target(self):
        pair=scalp.levels({**self.buy,"tp":101,"rr":.5},3)
        self.assertEqual(pair["scalp"]["tp"],101)
    def test_tick_rounding_toward_entry(self):
        for data,target in ((self.buy,101.6),(self.sell,98.4)):
            pair=scalp.levels({**data,"tick_size":.8},1)
            self.assertAlmostEqual(pair["scalp"]["tp"],target)
    def test_invalid_or_nonfinite_parameters(self):
        for rr in (True,0,-1,4,"nan","inf","bad"):
            with self.subTest(rr=rr),self.assertRaises(ValueError):scalp.levels(self.buy,rr)
        for fields in ({"entry":True},{"entry":"NaN"},{"sl":101},{"tp":99},{"tick_size":0},{"rr":20}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):scalp.levels({**self.buy,**fields})
    def test_no_fabricated_signals_when_empty(self):
        self.assertEqual(scalp.scenarios([],now=self.now)["count"],0)
    def test_old_future_and_malformed_signals_excluded(self):
        rows=[self.row(minutes=15),("GBPUSD","BUY",(self.now+timedelta(minutes=1)).isoformat(),json.dumps(self.buy))]
        self.assertEqual(scalp.scenarios(rows,now=self.now)["count"],0)
    def test_latest_signal_supersedes_older_signal(self):
        rows=[self.row(self.buy,minutes=2),self.row(self.sell,minutes=1)]
        result=scalp.scenarios(rows,now=self.now)["signals"]
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["event"],"SELL")
    def test_observed_full_target_or_stop_excludes_current_scenario(self):
        for close in (97,107):
            rows=[self.row(minutes=2),self.row(minutes=1,event="HEARTBEAT",close=close)]
            report=scalp.scenarios(rows,now=self.now)
            self.assertEqual(report["count"],0)
            self.assertEqual(report["excluded"]["closed_observed"],1)
    def test_scalp_target_observation_does_not_close_full_trade(self):
        rows=[self.row(minutes=2),self.row(minutes=1,event="HEARTBEAT",close=103)]
        result=scalp.scenarios(rows,now=self.now)["signals"][0]
        self.assertEqual(result["scalp_outcome"],"target_close_observed")
        self.assertEqual(result["full_trade"]["tp"],106)

    def test_heartbeat_alone_does_not_create_trade(self):
        self.assertEqual(scalp.scenarios([self.row(event="HEARTBEAT")],now=self.now)["count"],0)
    def test_missing_timeframe_not_claimed_verified(self):
        row=scalp.scenarios([self.row()],now=self.now)["signals"][0]
        self.assertFalse(row["timeframe_verified"])
        self.assertFalse(row["scalp"]["tick_size_verified"])

    def test_unqualified_event_symbol_is_normalized_for_display(self):
        row=self.row()
        row=("EURUSD",row[1],row[2],row[3])
        result=scalp.scenarios([row],now=self.now)["signals"]
        self.assertEqual(result[0]["symbol"],"OANDA:EURUSD")

if __name__=="__main__":unittest.main()
