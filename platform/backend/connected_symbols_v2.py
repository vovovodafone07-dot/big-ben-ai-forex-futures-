"""Safe, read-only symbol registry and futures price precision for Big Ben AI Pro.

An instrument is not connected simply because it is in a watchlist.
All listings require a provider-backed verification record.
No network calls, order routing or fabricated market data.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

# (exchange, minimum tick, USD value per tick). Outright futures only.
CONTRACTS = {
    "NQ": ("CME_MINI", "0.25", "5"),
    "MNQ": ("CME_MINI", "0.25", "0.5"),
    "ES": ("CME_MINI", "0.25", "12.5"),
    "MES": ("CME_MINI", "0.25", "1.25"),
    "GC": ("COMEX", "0.1", "10"),
    "MGC": ("COMEX_MINI", "0.1", "1"),
    "CL": ("NYMEX", "0.01", "10"),
    "MCL": ("NYMEX", "0.01", "1"),
}
MONTHS = "FGHJKMNQUVXZ"
EXPIRY = re.compile(r"^(?P<root>MNQ|MES|MGC|MCL|NQ|ES|GC|CL)(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{1,4})$")
CONTINUOUS = re.compile(r"^(?P<root>MNQ|MES|MGC|MCL|NQ|ES|GC|CL)(?P<num>[12])!$")
ROOTS = tuple(sorted(CONTRACTS, key=len, reverse=True))


def normalize_future(value):
    """Return normalized root/contract metadata; NEVER treat a continuous chart as expiry."""
    if not isinstance(value, str):
        raise ValueError("رمز العقد غير صالح")
    raw = value.strip().upper()
    symbol = raw.split(":", 1)[-1]
    root = next((r for r in ROOTS if symbol.startswith(r)), None)
    if not root:
        raise ValueError("عقد غير مدعوم")
    exchange, tick, tick_usd = CONTRACTS[root]
    if symbol == root:
        kind = "root"
    elif CONTINUOUS.fullmatch(symbol) and CONTINUOUS.fullmatch(symbol).group("root") == root:
        kind = "continuous"
    elif EXPIRY.fullmatch(symbol) and EXPIRY.fullmatch(symbol).group("root") == root:
        kind = "expiry"
    else:
        raise ValueError("صيغة العقد غير معروفة")
    if ":" in raw:
        prefix = raw.split(":", 1)[0]
        # Vendor symbols differ. Do not declare one provider's exchange alias valid for another.
        allowed = ({"CME", "CME_MINI"} if root in ("NQ", "MNQ", "ES", "MES") else
                   {"COMEX", "COMEX_MINI"} if root in ("GC", "MGC") else {"NYMEX"})
        if prefix not in allowed:
            raise ValueError("رمز البورصة غير معروف")
    return {"root": root, "requested": raw, "contract": symbol, "kind": kind,
            "exchange": exchange, "asset_class": "futures",
            "tick_size": tick, "tick_value_usd": tick_usd,
            "requires_expiry": kind != "expiry"}


def to_tick(price, tick):
    """Quantize to the actual tick size using decimal arithmetic, never binary floats."""
    p = Decimal(str(price))
    step = Decimal(str(tick))
    if not p.is_finite() or p <= 0 or not step.is_finite() or step <= 0:
        raise ValueError("سعر أو حجم حركة غير صالح")
    return str((p / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def valid_levels(direction, entry, stop, targets, tick):
    """Strict, tick-aligned, correctly ordered research levels."""
    if direction not in ("BUY", "SELL") or len(targets) != 3:
        return False
    try:
        nums = [Decimal(str(x)) for x in (entry, stop, *targets)]
        step = Decimal(str(tick))
        if step <= 0 or not all(n.is_finite() and n > 0 and n % step == 0 for n in nums):
            return False
        e, sl, a, b, c = nums
        return (sl < e < a < b < c) if direction == "BUY" else (sl > e > a > b > c)
    except (ValueError, TypeError, ArithmeticError):
        return False


def _utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("وقت بلا منطقة زمنية")
    return dt.astimezone(timezone.utc)


def verified_connected(records, now=None, max_age_seconds=630):
    """Picker records: only the asset's actual provider / contract / M5 evidence qualifies.

    'connected' and 'trade_ready' are distinct. A root or continuous future may be
    displayed for diagnostic purposes only after verification, never be trade-ready.
    """
    now = now or datetime.now(timezone.utc)
    selected = []
    for row in records:
        try:
            if row.get("enabled") is not True or row.get("provider_verified") is not True:
                continue
            if row.get("feed_status") != "CONNECTED" or row.get("interval") != "5min":
                continue
            symbol, provider_symbol = row["symbol"], row["provider_symbol"]
            if not isinstance(provider_symbol, str) or not provider_symbol.strip():
                continue
            ts = _utc(row["last_closed_m5"])
            age = (now - ts).total_seconds()
            if age < 300 or age > max_age_seconds:
                continue
            asset = row.get("asset_class")
            result = {"symbol": symbol, "provider_symbol": provider_symbol,
                      "provider": row["provider"], "asset_class": asset,
                      "connected": True, "market_state": "شموع حديثة",
                      "last_closed_m5": ts.isoformat()}
            if asset == "futures":
                meta = normalize_future(symbol)
                # A provider's exact expiry and the licensed exchange must be confirmed.
                result.update(meta)
                result["trade_ready"] = (meta["kind"] == "expiry" and
                    row.get("licensed") is True and row.get("contract_verified") is True and
                    row.get("venue_verified") is True and
                    row.get("verified_contract") == meta["contract"])
            elif asset in ("cfd", "forex"):
                result["trade_ready"] = row.get("licensed") is True
            else:
                continue
            selected.append(result)
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return sorted(selected, key=lambda r:(r["asset_class"], r["symbol"]))


def can_send_trade(asset, market_open, live_feed, plan):
    """Fail closed: status and realtime evidence must be independently verified."""
    if not asset or not asset.get("trade_ready"):
        return False, "مصدر الأصل أو العقد غير موثق"
    if market_open is not True:
        return False, "السوق مغلق أو حالة الجلسة غير مؤكدة"
    if live_feed is not True:
        return False, "لا توجد بيانات سعرية حية موثقة"
    if plan.get("status") != "READY" or not (plan.get("confirmation") or {}).get("confirmed"):
        return False, "شروط الدخول غير مكتملة"
    if asset["asset_class"] == "futures":
        targets = [t.get("price") for t in plan.get("targets", [])]
        if not valid_levels(plan.get("technical_direction"), plan.get("entry"),
                            plan.get("sl"), targets, asset["tick_size"]):
            return False, "مستويات العقود غير صحيحة وفق حجم الحركة"
    return True, "صفقة بحثية مؤكدة الشروط"


def setup_fingerprint(plan):
    """Stable setup key: no candle timestamp or periodic polling timestamp."""
    fields = ("symbol", "technical_direction", "entry", "sl", "mode")
    data = {k: plan.get(k) for k in fields}
    confirmation = plan.get("confirmation") or {}
    data["structural_level"] = confirmation.get("level")
    data["zone_id"] = confirmation.get("zone_id")
    data["sweep_id"] = confirmation.get("sweep_id")
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode()).hexdigest()
