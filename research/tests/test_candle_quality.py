"""Historical fixtures are synthetic and are not market-performance evidence."""
import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from candle_quality import validate_candles, DataQualityError
from barchart_adapter import get_m5, ProviderError

class CandleQualityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        self.rows = [{"time": (self.now - timedelta(minutes=15 - 5*i)).isoformat(),
                      "open":100, "high":102, "low":98, "close":101} for i in range(3)]
    def test_valid_data_is_normalized(self):
        rows, quality = validate_candles(self.rows, self.now)
        self.assertEqual(len(rows), 3)
        self.assertEqual(quality["synthetic_bars_created"], 0)
    def test_nonfinite_prices_rejected(self):
        for value in (float("nan"), float("inf"), 0, -1, True):
            with self.subTest(value=value):
                rows = [dict(row) for row in self.rows]
                rows[0]["open"] = value
                with self.assertRaises(DataQualityError):
                    validate_candles(rows, self.now)
    def test_naive_time_rejected(self):
        self.rows[0]["time"] = "2026-11-13T11:45:00"
        with self.assertRaises(DataQualityError): validate_candles(self.rows, self.now)
    def test_future_and_open_bar_rejected(self):
        for minutes in (-10, 0, 4):
            self.rows[-1]["time"] = (self.now - timedelta(minutes=minutes)).isoformat()
            with self.assertRaises(DataQualityError): validate_candles(self.rows, self.now)
    def test_duplicate_and_reversed_time_rejected(self):
        for rows in ([self.rows[0], self.rows[0]], self.rows[::-1]):
            with self.assertRaises(DataQualityError): validate_candles(rows, self.now)
    def test_non_m5_cadence_rejected(self):
        self.rows[1]["time"] = (self.now - timedelta(minutes=9)).isoformat()
        with self.assertRaises(DataQualityError): validate_candles(self.rows, self.now)
    def test_gaps_are_reported_without_invented_bars(self):
        rows, quality = validate_candles([self.rows[0], self.rows[2]], self.now)
        self.assertEqual(len(rows), 2)
        self.assertEqual(quality["gaps"][0]["missing_intervals"], 1)
        self.assertFalse(quality["calendar_verified"])
    def test_invalid_ohlc_bounds_rejected(self):
        self.rows[0]["high"] = 99
        with self.assertRaises(DataQualityError): validate_candles(self.rows, self.now)
    def test_provider_message_cannot_leak_credential(self):
        body = json.dumps({"status":{"code":401,"message":"secret-test-credential"}}).encode()
        with patch("barchart_adapter.urllib.request.urlopen", return_value=io.BytesIO(body)):
            with self.assertRaises(ProviderError) as caught: get_m5("NQ*0", "secret-test-credential")
        self.assertNotIn("secret-test-credential", str(caught.exception))
if __name__ == "__main__": unittest.main()
