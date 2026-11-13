"""Offline quote-adapter tests; no Barchart subscription or network calls required."""
import datetime
import io
import json
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from market_data import MarketDataError, fetch_barchart_quote, load_symbol_map

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 13, 10, 5, tzinfo=UTC)
MAP = '{"CME_MINI:NQ1!":"NQ*0","FX:EURUSD":"^EURUSD"}'

def fake_response(price=21000.0, mode="r", minutes_old=1):
    trade_time = NOW - datetime.timedelta(minutes=minutes_old)
    return io.BytesIO(json.dumps({
        "status": {"code": 200, "message": "Success."},
        "results": [{"symbol": "NQZ26", "lastPrice": price, "mode": mode,
                     "tradeTimestamp": trade_time.isoformat()}]
    }).encode())

class QuoteTests(unittest.TestCase):
    def options(self, key="test-only", symbol_map=MAP):
        return patch.dict(os.environ, {
            "BARCHART_API_KEY": key,
            "BIGBEN_BARCHART_SYMBOL_MAP": symbol_map,
        })

    def test_provider_reported_realtime_fresh(self):
        with self.options(), patch("market_data.urllib.request.urlopen", return_value=fake_response()):
            result = fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)
        self.assertTrue(result["realtime_verified"])
        self.assertTrue(result["usable_for_live_analysis"])
        self.assertFalse(result["entitlement_independently_verified"])
        self.assertEqual(result["quote_mode"], "provider_reported_realtime")
        self.assertEqual(result["provider_symbol_requested"], "NQ*0")

    def test_delayed_quote_is_never_called_realtime(self):
        with self.options(), patch("market_data.urllib.request.urlopen", return_value=fake_response(mode="i")):
            result = fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)
        self.assertFalse(result["realtime_verified"])
        self.assertFalse(result["usable_for_live_analysis"])
        self.assertEqual(result["quote_mode"], "delayed")

    def test_stale_realtime_mode_is_not_usable(self):
        with self.options(), patch("market_data.urllib.request.urlopen", return_value=fake_response(minutes_old=12)):
            result = fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)
        self.assertFalse(result["realtime_verified"])
        self.assertFalse(result["fresh_quote"])

    def test_unmapped_contract_is_rejected_not_guessed(self):
        with self.options():
            with self.assertRaises(MarketDataError) as ctx:
                fetch_barchart_quote("CME:6E1!", now=NOW)
        self.assertEqual(ctx.exception.status, 422)

    def test_no_key_or_map_requires_configuration(self):
        with self.options(key=""):
            with self.assertRaises(MarketDataError):
                fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)
        with self.options(symbol_map=""):
            with self.assertRaises(MarketDataError):
                fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)

    def test_bad_mapping_rejected(self):
        with self.options(symbol_map='{"../secret":"NQ*0"}'):
            with self.assertRaises(MarketDataError):
                load_symbol_map()

    def test_invalid_prices_rejected(self):
        for bad in (-1, 0, "NaN"):
            with self.subTest(price=bad):
                with self.options(), patch("market_data.urllib.request.urlopen", return_value=fake_response(price=bad)):
                    with self.assertRaises(MarketDataError):
                        fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)

    def test_provider_entitlement_error_is_explicit(self):
        body = io.BytesIO(json.dumps({"status": {"code": 403, "message": "Not licensed"}, "results": []}).encode())
        with self.options(), patch("market_data.urllib.request.urlopen", return_value=body):
            with self.assertRaises(MarketDataError) as ctx:
                fetch_barchart_quote("CME_MINI:NQ1!", now=NOW)
        self.assertEqual(ctx.exception.code, "barchart_rejected_symbol_or_entitlement")

if __name__ == "__main__":
    unittest.main()
