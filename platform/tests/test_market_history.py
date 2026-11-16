"""Synthetic provider fixtures; no live network or credentials."""
import importlib.util
import io
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

spec = importlib.util.spec_from_file_location("market_history", Path(__file__).resolve().parents[1]/"backend"/"market_history.py")
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
instrument_spec = importlib.util.spec_from_file_location("instruments", Path(__file__).resolve().parents[1]/"backend"/"instruments.py")
instruments = importlib.util.module_from_spec(instrument_spec)
instrument_spec.loader.exec_module(instruments)
NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def payload():
    return {"meta": {"symbol": "EUR/USD", "interval": "5min", "exchange_timezone": "UTC", "type": "Physical Currency"},
        "values": [{"datetime": "2026-11-13 17:50:00", "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15"},
                   {"datetime": "2026-11-13 17:55:00", "open": "1.15", "high": "1.2", "low": "1.0", "close": "1.1"}]}


class HistoryTests(unittest.TestCase):
    def fetch(self, data):
        with patch.object(history.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as request:
            rows, result = history.fetch_m5("EUR/USD", "synthetic-secret", NOW)
        self.assertEqual(request.call_count, 1)
        self.assertNotIn("synthetic-secret", json.dumps(result))
        return rows, result

    def test_valid_closed_utc_history(self):
        rows, result = self.fetch(payload())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["time"], "2026-11-13T17:55:00+00:00")
        self.assertFalse(result["realtime_verified"])

    def test_forex_metadata_can_omit_exchange_timezone_as_in_live_api(self):
        data=payload();data["meta"].pop("exchange_timezone")
        rows,result=self.fetch(data)
        self.assertEqual(len(rows),2)
        self.assertIn("documented_forex_UTC",result["timezone_basis"])

    def test_unclosed_last_bar_excluded(self):
        data = payload()
        data["values"][-1]["datetime"] = "2026-11-13 18:00:00"
        rows, result = self.fetch(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(result["incomplete_candles_excluded"], 1)

    def test_invalid_bars_reject_whole_batch(self):
        for field, value in (("high", "0.5"), ("close", "NaN"), ("low", True), ("datetime", "2026-11-13 18:05:00"), ("datetime", "2026-11-13 17:51:00")):
            data = payload()
            data["values"][-1][field] = value
            with self.subTest(field=field,value=value), self.assertRaisesRegex(history.HistoryError,"invalid_candle"):
                self.fetch(data)

    def test_duplicate_and_reverse_order_rejected(self):
        for mode in ("duplicate", "reverse"):
            data = payload()
            if mode == "duplicate":data["values"][1] = data["values"][0]
            else:data["values"].reverse()
            with self.assertRaises(history.HistoryError):self.fetch(data)

    def test_wrong_instrument_or_timezone_rejected(self):
        for field,value in (("symbol","GBP/USD"),("interval","1min"),("exchange_timezone","America/New_York"),("type","Common Stock")):
            data=payload();data["meta"][field]=value
            with self.assertRaisesRegex(history.HistoryError,"instrument_metadata_mismatch"):self.fetch(data)

    def test_gaps_reported_without_synthetic_prices(self):
        data=payload();data["values"][0]["datetime"]="2026-11-13 17:40:00"
        rows,result=self.fetch(data)
        self.assertEqual(len(rows),2)
        self.assertEqual(result["gaps"][0]["missing_intervals"],2)
        self.assertFalse(result["calendar_verified"])

    def test_errors_never_echo_provider_message_or_retry(self):
        for error in (HTTPError("private",429,"synthetic-secret",{},None),URLError("synthetic-secret")):
            with patch.object(history.urllib.request,"urlopen",side_effect=error) as request:
                with self.assertRaises(history.HistoryError) as caught:history.fetch_m5("EUR/USD","synthetic-secret",NOW)
            self.assertNotIn("synthetic-secret",str(caught.exception))
            self.assertEqual(request.call_count,1)
        with self.assertRaisesRegex(history.HistoryError,"authentication_failed"):
            self.fetch({"status":"error","code":401,"message":"synthetic-secret"})

    def test_no_guessed_futures_or_network_without_key(self):
        with patch.object(history.urllib.request,"urlopen") as request:
            for symbol,key in (("MES","fixture"),("EUR/USD","")):
                with self.assertRaises(history.HistoryError):history.fetch_m5(symbol,key,NOW)
        request.assert_not_called()

    def test_storage_is_idempotent_and_migration_preserves_rows(self):
        rows,result=self.fetch(payload());result.update(state="CONNECTED",reason="validated_closed_m5_history")
        with sqlite3.connect(":memory:") as c:
            history.migrate(c)
            first=history.store_check(c,"EUR/USD",result,rows)
            history.migrate(c)
            second=history.store_check(c,"EUR/USD",result,rows)
            self.assertEqual(first["candles_inserted"],2)
            self.assertEqual(second["candles_inserted"],0)
            self.assertEqual(second["stored_candles"],2)
            view=history.coverage(c,NOW)
            self.assertTrue(view["symbols"][0]["recent_closed_candle"])
            self.assertFalse(view["symbols"][3]["provider_tested"])
            stale=history.coverage(c,datetime(2026,11,14,18,tzinfo=timezone.utc))
            self.assertFalse(stale["symbols"][0]["recent_closed_candle"])

    def test_every_catalogued_future_is_visible_but_unverified(self):
        with sqlite3.connect(":memory:") as c:
            history.migrate(c)
            view = history.coverage(c, NOW)
        futures = {item["symbol"]: item for item in view["symbols"] if item.get("asset_class") == "futures"}
        self.assertEqual(set(futures), set(instruments.FUTURES))
        self.assertFalse(view["futures_coverage_verified"])
        self.assertTrue(all(item["state"] == "UNKNOWN" for item in futures.values()))
        self.assertTrue(all(item["provider_tested"] is False for item in futures.values()))


if __name__ == "__main__":unittest.main()
