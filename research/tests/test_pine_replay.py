"""Hand-computed synthetic rule examples; no profitability/parity claim."""
import importlib.util
import math
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

spec=importlib.util.spec_from_file_location("pine_replay",Path(__file__).resolve().parents[1]/"pine_replay.py")
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
START=datetime(2026,11,10,tzinfo=timezone.utc)
NOW=datetime(2026,11,14,tzinfo=timezone.utc)
ISOLATE={"htf_mode":"Off","use_hybrid":False}

def rows(count=20):
    return [{"time":(START+timedelta(minutes=i*5)).isoformat(),"open":100.,"high":100.2,"low":99.8,"close":100.} for i in range(count)]

def add(data,o,h,l,c):
    data.append({"time":(START+timedelta(minutes=len(data)*5)).isoformat(),"open":o,"high":h,"low":l,"close":c})
    return data

def breakout():return add(rows(),100,101.1,99.9,101)

def run(data,**config):return engine.replay(data,.01,{**ISOLATE,**config},now=NOW)


class ReplayTests(unittest.TestCase):
    def test_atr_wilder_seed_and_recursion(self):
        data=rows(14);add(data,100,102,100,101)
        result=engine.atr_series(data)
        self.assertTrue(all(v is None for v in result[:13]))
        self.assertAlmostEqual(result[13],.4)
        self.assertAlmostEqual(result[14],(.4*13+2)/14)

    def test_breakout_does_not_enter_on_retest_breakout_bar(self):
        result=run(breakout())
        self.assertEqual(result["trades"],[])
        self.assertTrue(result["diagnostics"][-1]["break_up"])
        self.assertIn("trigger",result["diagnostics"][-1]["decisions"]["BUY"]["rejections"])

    def test_later_retest_preserves_rr_and_current_candle_swing_stop(self):
        data=breakout();add(data,100.3,100.9,100.1,100.8)
        result=run(data)
        self.assertEqual(len(result["trades"]),1)
        trade=result["trades"][0]
        self.assertEqual(trade["entry_index"],21)
        self.assertEqual(trade["entry"],100.8)
        self.assertAlmostEqual(trade["sl"],99.8-result["diagnostics"][21]["atr"]*.2)
        self.assertAlmostEqual((trade["tp"]-trade["entry"])/(trade["entry"]-trade["sl"]),2.5)
        self.assertEqual(trade["time"],(START+timedelta(minutes=110)).isoformat())

    def test_retest_timeout_and_rejection_log(self):
        data=breakout()
        for _ in range(3):add(data,100.5,101.,100.5,100.6)
        result=run(data,retest_bars=2)
        self.assertTrue(result["diagnostics"][-1]["pending_expired"])
        self.assertIsNone(result["diagnostics"][-1]["pending"])
        self.assertEqual(len(result["diagnostics"]),len(data))

    def test_confirmed_breakout_and_sell_direction_filter(self):
        accepted=run(breakout(),mode="Confirmed breakout")
        self.assertEqual(accepted["trades"][0]["side"],"BUY")
        rejected=run(breakout(),mode="Confirmed breakout",side="Sell")
        self.assertEqual(rejected["trades"],[])
        self.assertIn("direction",rejected["diagnostics"][-1]["decisions"]["BUY"]["rejections"])

    def test_sell_is_symmetric_and_targets_positive_fixture(self):
        data=rows();add(data,100,100.1,98.9,99)
        result=run(data,mode="Confirmed breakout")
        self.assertEqual(result["trades"][0]["side"],"SELL")
        t=result["trades"][0]
        self.assertTrue(t["tp"]<t["entry"]<t["sl"])
        self.assertAlmostEqual((t["entry"]-t["tp"])/(t["sl"]-t["entry"]),2.5)

    def test_entry_bar_cannot_hit_its_own_stop(self):
        result=run(breakout(),mode="Confirmed breakout")
        self.assertEqual(result["trades"][0]["outcome"],"unresolved")
        self.assertEqual(result["metrics"]["resolved"],0)

    def test_both_hit_is_ambiguous_and_not_a_win(self):
        data=breakout();add(data,101,106,98,100)
        result=run(data,mode="Confirmed breakout")
        self.assertEqual(result["trades"][0]["outcome"],"ambiguous_both")
        self.assertIsNone(result["trades"][0]["gross_r"])
        self.assertEqual(result["metrics"]["wins"],0)
        self.assertEqual(result["metrics"]["conservative_r"],-1)

    def test_open_trade_and_cooldown_rejections_are_distinct(self):
        data=breakout();add(data,100.3,101,100.2,100.8);add(data,100.8,106,100.7,104)
        result=run(data,mode="Confirmed breakout",max_risk_atr=20)
        self.assertIn("no_open_trade",result["diagnostics"][21]["decisions"]["BUY"]["rejections"])
        self.assertNotIn("no_open_trade",result["diagnostics"][22]["decisions"]["BUY"]["rejections"])
        self.assertIn("cooldown",result["diagnostics"][22]["decisions"]["BUY"]["rejections"])
        relaxed=run(data,mode="Confirmed breakout",max_risk_atr=20,cooldown=0)
        self.assertEqual(len(relaxed["trades"]),2)

    def test_pivot_is_published_only_after_right_bars(self):
        values=[1,2,5,3,2,9]
        self.assertIsNone(engine.confirmed_pivot(values,3,2))
        self.assertEqual(engine.confirmed_pivot(values,4,2),5)
        self.assertEqual(engine.confirmed_pivot(values[:5],4,2),5)

    def test_htf_offset_never_uses_current_htf_close(self):
        data=rows(12)
        for i,row in enumerate(data):
            row.update(open=100+i,high=101+i,low=99+i,close=100+i)
        bias=engine.confirmed_biases(data,15)
        self.assertIsNone(bias[2])
        self.assertEqual(bias[3],0)
        self.assertEqual(bias[5],0)
        self.assertEqual(bias[6],1)
        data[5].update(open=1000,high=1001,low=999,close=1000)
        changed=engine.confirmed_biases(data,15)
        self.assertEqual(changed[:6],bias[:6])

    def test_incomplete_initial_htf_bucket_does_not_seed_ema(self):
        data=rows(10)[1:]
        bias=engine.confirmed_biases(data,15)
        self.assertIsNone(bias[2])
        self.assertEqual(bias[5],0)

    def test_no_lookahead_when_future_bars_are_added(self):
        data=rows(200)
        for i,row in enumerate(data):
            c=100+(i%30)*.1;row.update(open=c,high=c+.2,low=c-.1,close=c+.1)
        prefix=engine.replay(data[:150],.01,now=NOW)
        full=engine.replay(data,.01,now=NOW)
        self.assertEqual(prefix["diagnostics"],full["diagnostics"][:150])
        self.assertEqual([(t["entry_index"],t["side"]) for t in prefix["trades"]],
            [(t["entry_index"],t["side"]) for t in full["trades"] if t["entry_index"]<150])

    def test_hybrid_filter_and_smt_are_optional_votes(self):
        data=breakout();data[-1]["low"]=99.7
        peer=rows(21)
        report=engine.replay(data,.01,{"htf_mode":"Off","mode":"Confirmed breakout","enable_smt":True},peer_candles=peer,now=NOW)
        self.assertTrue(report["diagnostics"][-1]["decisions"]["BUY"]["evidence"]["smt"])
        missing=engine.replay(data,.01,{"htf_mode":"Off","mode":"Confirmed breakout","enable_smt":True},now=NOW)
        self.assertFalse(missing["diagnostics"][-1]["decisions"]["BUY"]["evidence"]["smt"])
        strict=run(data,mode="Confirmed breakout",use_hybrid=True,min_evidence=8)
        self.assertEqual(strict["trades"],[])

    def test_costs_are_explicit_and_net_metrics_not_invented(self):
        data=breakout();add(data,101,106,100,105)
        raw=run(data,mode="Confirmed breakout")
        self.assertIsNone(raw["metrics"]["net_r"])
        costs={"spread_price":.05,"slippage_price_per_side":.02,"commission_price_round_trip":.01}
        report=engine.replay(data,.01,{**ISOLATE,"mode":"Confirmed breakout"},costs=costs,now=NOW)
        t=report["trades"][0]
        self.assertAlmostEqual(t["cost_r"],.1/abs(t["entry"]-t["sl"]))
        self.assertAlmostEqual(report["metrics"]["net_r"],2.5-t["cost_r"])

    def test_invalid_configuration_numbers_cadence_and_costs_rejected(self):
        for config in ({"unknown":1},{"rr":True},{"lookback":5.5},{"rr":float("nan")},{"use_ha":1}):
            with self.assertRaises(ValueError):run(rows(),**config)
        for tick in (0,-1,True,float("inf")):
            with self.assertRaises(ValueError):engine.replay(rows(),tick,now=NOW)
        with self.assertRaises(ValueError):engine.replay(rows(),.01,costs={},now=NOW)
        data=rows();data[-1]["time"]=(START+timedelta(minutes=19*5+1)).isoformat()
        with self.assertRaises(ValueError):run(data)

    def test_no_parity_or_promotion_claim(self):
        result=run(rows())
        self.assertFalse(result["pine_parity_verified"])
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["htf_alignment"]["exchange_verified"])

if __name__=="__main__":unittest.main()
