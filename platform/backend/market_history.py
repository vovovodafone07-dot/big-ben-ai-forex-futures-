"""Bounded, read-only Twelve Data M5 ingestion. No guessed futures aliases."""
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import importlib.util

FOREX = ("EUR/USD", "GBP/USD", "USD/JPY")
try:
    from . import instruments as _instruments
except ImportError:
    try:
        import instruments as _instruments
    except ImportError:
        _ispec = importlib.util.spec_from_file_location("bigben_instruments", Path(__file__).with_name("instruments.py"))
        _instruments = importlib.util.module_from_spec(_ispec)
        _ispec.loader.exec_module(_instruments)

# Inventory only: catalog presence is not live access or entitlement.
FUTURES = tuple(_instruments.FUTURES)
MAX_BYTES = 2_000_000
ADAPTER_VERSION = 2


class HistoryError(ValueError):
    """Only sanitized machine-readable reasons may leave this adapter."""


def fetch_m5(symbol, key, now=None):
    if symbol not in FOREX:
        raise HistoryError("symbol_not_verified")
    if not key:
        raise HistoryError("not_configured")
    now = now or datetime.now(timezone.utc)
    query = urllib.parse.urlencode({"symbol": symbol, "apikey": key,
        "interval": "5min", "timezone": "UTC", "order": "asc", "outputsize": 1000})
    req = urllib.request.Request("https://api.twelvedata.com/time_series?" + query,
        headers={"User-Agent": "BigBenAIPro-History/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise OverflowError()
        data = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise HistoryError({401: "authentication_failed", 403: "entitlement_denied",
            429: "rate_limited"}.get(error.code, "provider_http_error")) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HistoryError("connection_failure") from None
    except OverflowError:
        raise HistoryError("response_too_large") from None
    except (ValueError, TypeError):
        raise HistoryError("invalid_response") from None
    if not isinstance(data, dict):
        raise HistoryError("invalid_response")
    if data.get("status") == "error" or not isinstance(data.get("values"), list):
        raise HistoryError({"401": "authentication_failed", "403": "entitlement_denied",
            "429": "rate_limited"}.get(str(data.get("code")), "provider_rejected"))
    meta = data.get("meta") or {}
    if (not isinstance(meta, dict) or meta.get("symbol") != symbol
            or meta.get("interval") != "5min" or meta.get("exchange_timezone", "UTC") != "UTC"
            or meta.get("type") != "Physical Currency"):
        raise HistoryError("instrument_metadata_mismatch")
    items = data["values"]
    if not items or len(items) > 1000:
        raise HistoryError("invalid_candle_count")
    rows, gaps = [], []
    previous = None
    incomplete = 0
    for item in items:
        try:
            stamp = datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if stamp.second or stamp.minute % 5:
                raise ValueError()
            if stamp > now:
                raise ValueError()
            if previous is not None:
                distance = int((stamp - previous).total_seconds())
                if distance < 300 or distance % 300:
                    raise ValueError()
                if distance > 300:
                    gaps.append({"after": previous.isoformat(), "before": stamp.isoformat(),
                        "missing_intervals": distance // 300 - 1, "classification": "calendar_unverified"})
            previous = stamp
            prices = {k: float(item[k]) for k in ("open", "high", "low", "close")}
            if any(isinstance(item[k], bool) for k in prices):
                raise ValueError()
            if not all(math.isfinite(v) and v > 0 for v in prices.values()):
                raise ValueError()
            if prices["high"] < max(prices.values()) or prices["low"] > min(prices.values()):
                raise ValueError()
            if (now - stamp).total_seconds() < 300:
                incomplete += 1
                continue
            rows.append({"time": stamp.isoformat(), **prices})
        except (KeyError, TypeError, ValueError, OverflowError):
            raise HistoryError("invalid_candle") from None
    if not rows:
        raise HistoryError("no_closed_candles")
    return rows, {"provider": "Twelve Data", "symbol": symbol, "interval": "5min",
        "adapter_version": ADAPTER_VERSION, "timezone_basis": "explicit_UTC_request_and_documented_forex_UTC",
        "candles_received": len(rows), "incomplete_candles_excluded": incomplete,
        "first_candle": rows[0]["time"], "last_candle": rows[-1]["time"],
        "gaps": gaps, "calendar_verified": False, "synthetic_bars_created": 0,
        "realtime_verified": False, "checked_at": now.isoformat()}


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS market_candles (provider TEXT NOT NULL, symbol TEXT NOT NULL, time TEXT NOT NULL, open DOUBLE PRECISION NOT NULL, high DOUBLE PRECISION NOT NULL, low DOUBLE PRECISION NOT NULL, close DOUBLE PRECISION NOT NULL, received_at TEXT NOT NULL, PRIMARY KEY(provider,symbol,time))")
    connection.execute("CREATE TABLE IF NOT EXISTS market_history_checks (symbol TEXT PRIMARY KEY, checked_at TEXT NOT NULL, payload TEXT NOT NULL)")


def store_check(connection, symbol, result, rows=(), postgres=False):
    marker = "%s" if postgres else "?"
    result = dict(result)
    inserted = 0
    for row in rows:
        values = ("Twelve Data", symbol, row["time"], row["open"], row["high"], row["low"], row["close"], result["checked_at"])
        inserted += connection.execute("INSERT INTO market_candles (provider,symbol,time,open,high,low,close,received_at) VALUES (" + ",".join([marker]*8) + ") ON CONFLICT(provider,symbol,time) DO NOTHING", values).rowcount
    result["candles_inserted"] = inserted
    result["stored_candles"] = connection.execute("SELECT COUNT(*) FROM market_candles WHERE provider=" + marker + " AND symbol=" + marker, ("Twelve Data", symbol)).fetchone()[0]
    connection.execute("INSERT INTO market_history_checks(symbol,checked_at,payload) VALUES (" + ",".join([marker]*3) + ") ON CONFLICT(symbol) DO UPDATE SET checked_at=excluded.checked_at,payload=excluded.payload", (symbol,result["checked_at"],json.dumps(result)))
    return result


def coverage(connection, now=None, postgres=False):
    now = now or datetime.now(timezone.utc)
    checks = {symbol: json.loads(payload) for symbol,payload in connection.execute("SELECT symbol,payload FROM market_history_checks").fetchall()}
    symbols = []
    for symbol in FOREX:
        item = checks.get(symbol, {"symbol": symbol, "state": "UNKNOWN", "reason": "not_checked"}).copy()
        bounds=connection.execute("SELECT COUNT(*),MAX(time) FROM market_candles WHERE provider='Twelve Data' AND symbol=" + ("%s" if postgres else "?"), (symbol,)).fetchone()
        item["stored_candles"] = bounds[0]
        if bounds[1]:item["last_candle"] = bounds[1]
        stamp = item.get("last_candle")
        if stamp:
            item["last_candle_age_seconds"] = max(0, int((now-datetime.fromisoformat(stamp)).total_seconds()))
            # Stale history is not evidence that the exchange is closed.
            item["recent_closed_candle"] = item["last_candle_age_seconds"] <= 900
        symbols.append(item)
    for symbol in FUTURES:
        exchange, name = _instruments.FUTURES[symbol]
        symbols.append({"symbol": symbol, "state": "UNKNOWN", "reason": "licensed_contract_mapping_required",
            "asset_class": "futures", "exchange": exchange, "name": name,
            "provider_tested": False, "realtime_verified": False})
    return {"generated_at": now.isoformat(), "symbols": symbols, "provider": "Twelve Data",
        "mode": "bounded_historical_ingestion", "refresh_interval_hours": 6,
        "requests_per_cycle": 3, "max_candles_per_request": 1000,
        "futures_coverage_verified": False, "realtime_verified": False}
