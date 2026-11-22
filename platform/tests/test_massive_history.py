import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "massive_history_test", Path(__file__).resolve().parents[1] / "backend" / "massive_history.py"
)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)

NOW = datetime(2026, 11, 22, 23, 30, tzinfo=timezone.utc)
WATCHED = {"CME_MINI:MNQ1!"}
CONTRACT = {"ticker": "MNQZ6", "product_code": "MNQ", "trading_venue": "XCME", "type": "single"}
BAR = {"ticker": "MNQZ6", "window_start": 1795211700000000000,
       "open": 25301.25, "high": 25312.0, "low": 25276.0, "close": 25288.25}


class MassiveHistoryTests(unittest.TestCase):
    def setUp(self):
        history.CACHE.clear()

    def test_dated_contract_is_explicitly_historical_and_cached(self):
        with patch.object(history, "_request", side_effect=[[CONTRACT], [BAR]]) as request:
            data = history.read("mnqz6", "m5", WATCHED, "key", NOW)
            self.assertEqual(data["ticker"], "MNQZ6")
            self.assertEqual(data["exchange"], "CME")
            self.assertTrue(data["historical_only"])
            self.assertEqual(data["last_closed_at"], "2026-11-20T22:00:00+00:00")
            self.assertEqual(request.call_args.args[1]["resolution"], "5min")
            self.assertEqual(history.read("MNQZ6", "M5", WATCHED, "key", NOW), data)
            self.assertEqual(request.call_count, 2)

    def test_disallows_continuous_untracked_and_unconfigured_requests(self):
        with patch.object(history, "_request") as request:
            for ticker, tracked, key, error in (
                ("MNQ1!", WATCHED, "key", "invalid"),
                ("MNQZ6", set(), "key", "not_tracked"),
                ("MNQZ6", WATCHED, "", "not_configured"),
            ):
                with self.subTest(error=error), self.assertRaisesRegex(history.HistoryError, error):
                    history.read(ticker, "M5", tracked, key, NOW)
            request.assert_not_called()

    def test_rejects_other_exchange_or_aggregate_symbol(self):
        for responses in (
            [[dict(CONTRACT, trading_venue="XCBT")]],
            [[CONTRACT], [dict(BAR, ticker="NQZ6")]],
        ):
            with self.subTest(responses=responses):
                with patch.object(history, "_request", side_effect=responses):
                    with self.assertRaisesRegex(history.HistoryError, "identity"):
                        history.read("MNQZ6", "M5", WATCHED, "key", NOW)
