"""Regression tests for TradingView discovery and Arabic card separation."""
import importlib.util
import pathlib
import sqlite3
import unittest

p=pathlib.Path(__file__).resolve().parents[1]/"backend"/"tradingview_dynamic_sync.py"
spec=importlib.util.spec_from_file_location("tv_sync",p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TradingViewDynamicSyncTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        mod.migrate(self.db)

    def tearDown(self):
        self.db.close()

    def test_authenticated_discovery_dedupes_symbol_and_does_not_enable_feed(self):
        p={"symbol":"CME_MINI:NQZ26","asset_class":"futures"}
        with self.assertRaises(PermissionError):
            mod.record_symbol(self.db,p)
        mod.record_symbol(self.db,p,authenticated=True)
        mod.record_symbol(self.db,p,authenticated=True)
        rows=mod.discovered(self.db)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["event_count"],2)
        self.assertFalse(rows[0]["feed_verified"])
        self.assertFalse(rows[0]["enabled"])

    def test_unsafe_symbol_rejected(self):
        with self.assertRaises(ValueError):
            mod.record_symbol(self.db,{"symbol":"../../bad"},authenticated=True)

    def test_trade_analysis_cards_are_distinct(self):
        p={"status":"READY","confirmation":{"confirmed":True},
           "symbol":"COMEX_MINI:MGCZ26","asset_class":"futures",
           "technical_direction":"SELL","entry":4500,"sl":4501,
           "targets":[{"price":4499},{"price":4498},{"price":4497}]}
        trade=mod.trade_card(p)
        analysis=mod.analysis_card({"symbol":p["symbol"],"trend":"هابط",
                                  "event":"سحب سيولة","zone":"4500-4501"})
        self.assertIn("🔴 توصية بيع",trade)
        self.assertIn("TP3",trade)
        self.assertNotIn("تحديث تحليل فني",trade)
        self.assertIn("📈 تحديث تحليل فني",analysis)
        self.assertNotIn("وقف الخسارة",analysis)

if __name__=="__main__":
    unittest.main()
