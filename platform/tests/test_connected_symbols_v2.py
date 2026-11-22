"""Unit tests for connected_symbols_v2; no provider key required."""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone, timedelta

PATH = pathlib.Path(__file__).resolve().parents[1] / "backend" / "connected_symbols_v2.py"
SPEC = importlib.util.spec_from_file_location("connected_symbols_v2", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ConnectedSymbolsTests(unittest.TestCase):
    def test_contract_venue_cannot_be_substituted(self):
        for symbol in ("NYMEX:NQZ26", "COMEX:ESZ26", "CME_MINI:GCZ26", "COMEX:MCLZ26"):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                module.normalize_future(symbol)
        self.assertEqual(module.normalize_future("CME_MINI:MNQ1!")["exchange"], "CME_MINI")
        self.assertEqual(module.normalize_future("CME_MINI:MES1!")["exchange"], "CME_MINI")

    def test_all_supported_contract_roots(self):
        for root in ("NQ", "MNQ", "ES", "MES", "GC", "MGC", "CL", "MCL"):
            with self.subTest(root=root):
                self.assertEqual(module.normalize_future(root)["root"], root)
                self.assertTrue(module.normalize_future(root)["requires_expiry"])

    def test_expiry_vs_continuous(self):
        self.assertEqual(module.normalize_future("CME_MINI:NQZ26")["kind"], "expiry")
        self.assertEqual(module.normalize_future("COMEX_MINI:MGCZ26")["kind"], "expiry")
        self.assertEqual(module.normalize_future("MNQ1!")["kind"], "continuous")
        with self.assertRaises(ValueError):
            module.normalize_future("NAS100")
        with self.assertRaises(ValueError):
            module.normalize_future("NQBAD")

    def test_tick_precision_and_side(self):
        self.assertEqual(module.to_tick("30000.13", "0.25"), "30000.25")
        self.assertTrue(module.valid_levels("BUY", "100.00", "99.75",
                                             ["100.25", "100.5", "101.00"], "0.25"))
        self.assertFalse(module.valid_levels("BUY", "100.01", "99.75",
                                              ["100.25", "100.50", "101"], "0.25"))
        self.assertTrue(module.valid_levels("SELL", "100", "100.25",
                                             ["99.75", "99.5", "99.25"], "0.25"))

    def test_picker_requires_live_evidence(self):
        now = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
        example = dict(symbol="CME_MINI:NQZ26", provider_symbol="NQZ26",
                       provider="licensed_provider", enabled=True, provider_verified=True,
                       feed_status="CONNECTED", interval="5min", licensed=True,
                       asset_class="futures", contract_verified=True, venue_verified=True,
                       verified_contract="NQZ26",
                       last_closed_m5=(now - timedelta(minutes=5)).isoformat())
        ready = module.verified_connected([example], now=now)
        self.assertEqual(len(ready), 1)
        self.assertTrue(ready[0]["trade_ready"])
        stale = dict(example, last_closed_m5=(now - timedelta(hours=1)).isoformat())
        self.assertEqual(module.verified_connected([stale], now=now), [])
        cont = dict(example, symbol="CME_MINI:NQ1!", verified_contract="NQ1!")
        self.assertFalse(module.verified_connected([cont], now=now)[0]["trade_ready"])
        self.assertEqual(module.verified_connected([dict(example, licensed=False)], now=now)[0]["trade_ready"], False)

    def test_closed_market_and_dedup(self):
        asset={"asset_class":"futures","trade_ready":True,"tick_size":"0.25"}
        plan={"symbol":"CME_MINI:NQZ26","mode":"scalp","status":"READY",
              "technical_direction":"BUY","entry":"100","sl":"99.75",
              "targets":[{"price":"100.25"},{"price":"100.5"},{"price":"101"}],
              "confirmation":{"confirmed":True,"level":100}}
        self.assertFalse(module.can_send_trade(asset,False,True,plan)[0])
        self.assertFalse(module.can_send_trade(asset,True,False,plan)[0])
        self.assertTrue(module.can_send_trade(asset,True,True,plan)[0])
        key=module.setup_fingerprint(plan)
        changed=dict(plan, source_time="different_closed_candle")
        self.assertEqual(key,module.setup_fingerprint(changed))
        changed=dict(plan, entry="100.25")
        self.assertNotEqual(key,module.setup_fingerprint(changed))


if __name__ == "__main__":
    unittest.main()
