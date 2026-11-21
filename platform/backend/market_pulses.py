"""Deterministic market pulses from stored closed candles; never creates trades."""
import json
import math
from datetime import datetime, timezone

ADAPTER_VERSION = 1


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS market_analysis_pulses (id TEXT PRIMARY KEY,symbol TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)")


def _ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = alpha * item + (1 - alpha) * value
    return value


def analyze(symbol, rows, now=None):
    now = now or datetime.now(timezone.utc)
    ordered = sorted(rows, key=lambda item: item[0] if isinstance(item, (tuple, list)) else item["time"])
    candles = []
    for item in ordered:
        try:
            stamp, op, high, low, close = item[:5] if isinstance(item, (tuple, list)) else (item["time"], item["open"], item["high"], item["low"], item["close"])
            dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            values = [float(op), float(high), float(low), float(close)]
            if dt.tzinfo is None or not all(math.isfinite(x) and x > 0 for x in values):
                continue
            candles.append((dt.astimezone(timezone.utc), *values))
        except (ValueError, TypeError, KeyError, IndexError):
            continue
    if not candles:
        return {"symbol": symbol, "state": "INSUFFICIENT_DATA", "decision": "DATA_UNAVAILABLE", "reason": "no_closed_candles", "candles": 0, "generated_at": now.isoformat(), "source": "Twelve Data stored closed candles"}
    closes = [x[4] for x in candles]
    last = candles[-1]
    age = max(0, int((now - last[0]).total_seconds()))
    fresh = age <= 900
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    lookback = closes[-13] if len(closes) >= 13 else None
    momentum_pct = ((last[4] / lookback) - 1) * 100 if lookback else None
    atr = None
    if len(candles) >= 15:
        trs = []
        for i in range(1, len(candles)):
            _, _, high, low, _ = candles[i]
            prev_close = candles[i - 1][4]
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        atr = sum(trs[-14:]) / 14 if len(trs) >= 14 else None
    if not fresh:
        state, decision = "STALE", "DATA_STALE"
    elif ema20 is None or ema50 is None or momentum_pct is None:
        state, decision = "INSUFFICIENT_DATA", "INSUFFICIENT_HISTORY"
    elif last[4] > ema20 > ema50 and momentum_pct > 0:
        state, decision = "BULLISH", "MONITOR_LONG_SETUP"
    elif last[4] < ema20 < ema50 and momentum_pct < 0:
        state, decision = "BEARISH", "MONITOR_SHORT_SETUP"
    else:
        state, decision = "MIXED", "NO_CONFIRMED_DIRECTION"
    return {"symbol": symbol, "state": state, "decision": decision, "fresh": fresh, "age_seconds": age,
            "last_closed_candle": last[0].isoformat(), "last_close": last[4],
            "ema20": round(ema20, 8) if ema20 is not None else None,
            "ema50": round(ema50, 8) if ema50 is not None else None,
            "momentum_60m_pct": round(momentum_pct, 5) if momentum_pct is not None else None,
            "atr14": round(atr, 8) if atr is not None else None, "candles": len(candles),
            "entry": None, "sl": None, "tp": None,
            "reason": ("البيانات متأخرة، لا يمكن اعتماد اتجاه الآن" if state=="STALE" else "لا توجد شموع كافية لحساب الاتجاه" if state=="INSUFFICIENT_DATA" else "اتجاه عرضي أو متضارب، لا توجد صفقة مؤكدة" if state=="MIXED" else "اتجاه قيد المراقبة من شموع مغلقة"),
            "source": "Twelve Data stored closed candles", "adapter_version": ADAPTER_VERSION,
            "generated_at": now.isoformat()}


def save(connection, result, postgres=False):
    marker = "%s" if postgres else "?"
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True)
    ident = result["symbol"] + ":" + result["generated_at"]
    connection.execute("INSERT INTO market_analysis_pulses(id,symbol,created_at,payload) VALUES (" + ",".join([marker] * 4) + ") ON CONFLICT(id) DO NOTHING", (ident, result["symbol"], result["generated_at"], raw))
    return result


def latest(connection, limit=30):
    rows = connection.execute("SELECT payload FROM market_analysis_pulses ORDER BY created_at DESC LIMIT " + str(int(limit))).fetchall()
    return [json.loads(row[0]) for row in rows]
