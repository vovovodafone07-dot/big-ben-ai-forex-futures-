"""Licensed Barchart quote adapter. No synthetic quotes and no broker/order endpoints."""
import datetime
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request

QUOTE_URL = "https://ondemand.websol.barchart.com/getQuote.json"

class MarketDataError(RuntimeError):
    def __init__(self, code, status=502):
        super().__init__(code)
        self.code = code
        self.status = status

def validate_symbol(value, provider=False):
    pattern = r"[A-Za-z0-9^*:.!/_-]{2,60}" if provider else r"[A-Za-z0-9:.!/_-]{2,60}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value) or ".." in value or value[0] in "./-":
        raise MarketDataError("invalid_symbol", 400)
    return value

def load_symbol_map():
    raw = os.getenv("BIGBEN_BARCHART_SYMBOL_MAP", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise MarketDataError("invalid_barchart_symbol_map", 503) from exc
    if not isinstance(parsed, dict) or len(parsed) > 100:
        raise MarketDataError("invalid_barchart_symbol_map", 503)
    mapping = {}
    for key, value in parsed.items():
        try:
            validated_key = validate_symbol(key).upper()
            validated_value = validate_symbol(value, provider=True)
        except MarketDataError as exc:
            raise MarketDataError("invalid_barchart_symbol_map", 503) from exc
        if validated_key in mapping:
            raise MarketDataError("duplicate_barchart_symbol_mapping", 503)
        mapping[validated_key] = validated_value
    return mapping

def parse_trade_time(value):
    if not isinstance(value, str) or len(value) > 60:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(datetime.timezone.utc)

def fetch_barchart_quote(symbol, *, now=None):
    """Return a real provider quote or a structured error, never a guessed contract."""
    symbol = validate_symbol(symbol).upper()
    api_key = os.getenv("BARCHART_API_KEY", "").strip()
    if not api_key:
        raise MarketDataError("barchart_api_key_missing", 503)
    mapping = load_symbol_map()
    if not mapping:
        raise MarketDataError("barchart_symbol_map_missing", 503)
    if symbol not in mapping:
        raise MarketDataError("symbol_not_mapped_to_licensed_provider", 422)
    provider_symbol = mapping[symbol]
    params = urllib.parse.urlencode({"apikey": api_key, "symbols": provider_symbol}).encode("utf-8")
    request = urllib.request.Request(
        QUOTE_URL, data=params, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "BigBenAI/market-probe"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise MarketDataError("barchart_request_failed") from exc
    if not isinstance(result, dict) or not isinstance(result.get("status"), dict):
        raise MarketDataError("barchart_invalid_response")
    if str(result["status"].get("code")) != "200":
        raise MarketDataError("barchart_rejected_symbol_or_entitlement", 502)
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise MarketDataError("barchart_missing_or_ambiguous_quote")
    row = rows[0]
    try:
        price = float(row["lastPrice"])
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        raise MarketDataError("barchart_invalid_price") from exc
    if not math.isfinite(price) or price <= 0:
        raise MarketDataError("barchart_invalid_price")
    mode = str(row.get("mode", "")).lower()
    mode_name = {"r": "provider_reported_realtime", "i": "delayed", "d": "end_of_day"}.get(mode, "unknown")
    trade_time = parse_trade_time(row.get("tradeTimestamp"))
    clock = now or datetime.datetime.now(datetime.timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    age = round((clock.astimezone(datetime.timezone.utc) - trade_time).total_seconds()) if trade_time else None
    fresh = age is not None and -60 <= age <= 180
    return {
        "symbol": symbol,
        "provider_symbol_requested": provider_symbol,
        "provider_symbol_returned": str(row.get("symbol", ""))[:60],
        "provider": "Barchart OnDemand",
        "price": price,
        "quote_timestamp": trade_time.isoformat() if trade_time else None,
        "quote_age_seconds": age,
        "quote_mode": mode_name,
        "provider_reported_realtime": mode == "r",
        "fresh_quote": fresh,
        "realtime_verified": mode == "r" and fresh,
        "usable_for_live_analysis": mode == "r" and fresh,
        "entitlement_independently_verified": False,
        "note": "Quote time and real-time flag are provider-reported; independently confirm exchange entitlements, sessions and symbol mapping.",
    }
