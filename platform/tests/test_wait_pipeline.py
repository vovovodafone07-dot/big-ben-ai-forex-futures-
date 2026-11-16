"""Local-only regressions for WAIT caused by old windows or skipped analyses."""
import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("wait_pipeline_app", Path(__file__).resolve().parents[1] / "backend" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class WaitPipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = Path(self.directory.name) / "local.sqlite3"
        self.env = patch.dict(os.environ, {"DATABASE_URL": "", "BIGBEN_ANALYSIS_KILL_SWITCH": "0", "BIGBEN_SIGNAL_ANALYSIS_ENABLED": "1"})
        self.env.start()
        app.init()

    def tearDown(self):
        self.env.stop()
        app.DB = self.old_db
        self.directory.cleanup()

    def test_pulse_selects_newest_thousand_not_oldest(self):
        now = datetime.now(timezone.utc)
        rows = []
        for i in range(1100):
            stamp = (now - timedelta(minutes=5 * (1100 - i))).isoformat()
            price = 100 + i * .01
            rows.append(("Twelve Data", "EUR/USD", stamp, price, price + .02, price - .02, price, now.isoformat()))
        with app.history_connection() as connection:
            connection.executemany("INSERT INTO market_candles VALUES (?,?,?,?,?,?,?,?)", rows)
        with patch.object(app._history, "coverage", return_value={"symbols": [{"symbol": "EUR/USD"}]}), patch.object(app.time, "sleep", side_effect=RuntimeError("stop_local_loop")):
            with self.assertRaisesRegex(RuntimeError, "stop_local_loop"):
                app.market_pulse_worker()
        with app.history_connection() as connection:
            result = app._market_pulses.latest(connection)[0]
        self.assertEqual(result["candles"], 1000)
        self.assertEqual(result["last_closed_candle"], rows[-1][2])
        self.assertTrue(result["fresh"])
        self.assertEqual(app.list_events(), [])

    def test_analysis_failure_returns_false_and_releases_slot(self):
        with patch.object(app, "SIGNAL_ANALYSIS_SLOTS") as slots, patch.object(app, "analyze_instrument", side_effect=RuntimeError("fixture_error")):
            slots.acquire.return_value = True
            self.assertFalse(app.run_signal_analysis("OANDA:EURUSD"))
            slots.release.assert_called_once()

    def test_capacity_timeout_does_not_report_success(self):
        with patch.object(app, "SIGNAL_ANALYSIS_SLOTS") as slots, patch.object(app, "analyze_instrument") as analyze:
            slots.acquire.return_value = False
            self.assertFalse(app.run_signal_analysis("OANDA:EURUSD"))
            slots.acquire.assert_called_once_with(timeout=10)
            slots.release.assert_not_called()
            analyze.assert_not_called()

    def test_failed_analysis_retries_without_duplicate_notification(self):
        data = {"event": "BUY", "event_id": "local-fixture-event"}
        with patch.object(app, "telegram_notify", return_value="sent") as telegram, patch.object(app, "whatsapp_notify", return_value="disabled"), patch.object(app, "run_signal_analysis", side_effect=[False, False, True]) as analyze, patch.object(app.time, "sleep"):
            app.process_signal_event("OANDA:EURUSD", data)
        self.assertEqual(analyze.call_count, 3)
        telegram.assert_called_once()
        with app.history_connection() as connection:
            receipts = app._destinations.recent(connection)
        self.assertEqual(len(receipts), 1)

    def test_exhausted_analysis_is_a_pipeline_failure(self):
        with patch.object(app, "telegram_notify", return_value="sent") as telegram, patch.object(app, "whatsapp_notify", return_value="disabled"), patch.object(app, "run_signal_analysis", return_value=False) as analyze, patch.object(app.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "analysis_retries_exhausted"):
                app.process_signal_event("OANDA:EURUSD", {"event": "BUY", "event_id": "local-exhausted-event"})
        self.assertEqual(analyze.call_count, 3)
        telegram.assert_called_once()

    def test_analysis_kill_switch_stops_all_notifications_and_review(self):
        with patch.dict(os.environ, {"BIGBEN_ANALYSIS_KILL_SWITCH": "1"}), patch.object(app, "telegram_notify") as telegram, patch.object(app, "run_signal_analysis") as analyze:
            app.process_signal_event("OANDA:EURUSD", {"event": "BUY"})
        telegram.assert_not_called()
        analyze.assert_not_called()

    def test_heartbeat_never_notifies_or_reviews_as_trade(self):
        with patch.object(app, "telegram_notify") as telegram, patch.object(app, "run_signal_analysis") as analyze:
            app.process_signal_event("OANDA:EURUSD", {"event": "HEARTBEAT"})
        telegram.assert_not_called()
        analyze.assert_not_called()

    def test_configuration_only_broker_status_does_not_connect(self):
        with patch.object(app._demo.DemoReadOnlyClient, "verify") as verify:
            result = app.integration_status()
        verify.assert_not_called()
        self.assertEqual(result["broker_execution"], "disabled")
        self.assertEqual(result["broker_demo"]["execution_allowlist"], [])
        self.assertFalse(result["broker_demo"]["connection_verified"])


if __name__ == "__main__":
    unittest.main()
