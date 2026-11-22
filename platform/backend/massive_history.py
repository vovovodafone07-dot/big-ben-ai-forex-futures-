"""Private, historical OHLC for explicitly dated futures contracts."""
import json
import math
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOTS = {
    "MNQ": ("CME_MINI:MNQ1!", "XCME", "CME"),
    "MES": ("CME_MINI:MES1!", "XCME", "CME"),
    "MBT": ("CME:MBT1!", "XCME", "CME"),
    "MGC": ("COMEX_MINI:MGC1!", "XCEC", "COMEX"),
    "MYM": ("CBOT_MINI:MYM1!", "XCBT", "CBOT"),
    "CL": ("NYMEX:CL1!", "XNYM", "NYMEX"),
}
FRAMES = {"M1": ("1min", 60), "M5": ("5min", 300), "M15": ("15min", 900),
          "M30": ("30min", 1800), "H1": ("1hour", 3600), "H4": ("4hour", 14400)}
MESSAGES = {
    "invalid": "اختر رمز عقد بتاريخ استحقاق محدد وإطارًا متاحًا، مثل MNQZ6 M5.",
    "not_tracked": "عائلة هذا العقد خارج قائمة المتابعة.",
    "not_configured": "مفتاح Massive Futures غير مهيأ على خادم Big Ben.",
    "entitlement": "صلاحية بيانات العقود التاريخية غير متاحة لهذا المفتاح.",
    "rate_limit": "بلغت طلبات Massive حد الجلب مؤقتًا. حاول بعد دقيقة.",
    "identity": "تعذر مطابقة رمز العقد والبورصة لدى Massive.",
    "no_data": "لا توجد شموع تاريخية مغلقة للعقد في النطاق المطلوب.",
    "provider_failure": "تعذر قراءة الشموع التاريخية من Massive.",
}
LOCK = threading.Lock()
REQUESTS = deque()
CACHE = {}


class HistoryError(ValueError):
    pass


def _request(path, params, key):
    now = time.monotonic()
    with LOCK:
        while REQUESTS and now - REQUESTS[0] >= 60:
            REQUESTS.popleft()
        if len(REQUESTS) >= 5:
            raise HistoryError("rate_limit")
        REQUESTS.append(now)
    request = Request("https://api.massive.com" + path + "?" + urlencode(params),
                      headers={"Accept": "application/json"})
    request.add_unredirected_header("Authorization", "Bearer " + key)
    try:
        with urlopen(request, timeout=7) as response:
            body = response.read(500_001)
        if len(body) > 500_000:
            raise ValueError()
        result = json.loads(body)
        if result.get("status") != "OK" or not isinstance(result.get("results", []), list):
            raise ValueError()
        return result.get("results", [])
    except HTTPError as error:
        code = {401: "entitlement", 403: "entitlement", 429: "rate_limit"}.get(error.code, "provider_failure")
        raise HistoryError(code) from None
    except (URLError, TimeoutError, ValueError, AttributeError):
        raise HistoryError("provider_failure") from None


def read(ticker, frame, watched, key, now=None):
    ticker = ticker.strip().upper()
    frame = frame.strip().upper()
    match = re.fullmatch(r"(MNQ|MES|MBT|MGC|MYM|CL)[FGHJKMNQUVXZ][0-9]{1,2}", ticker)
    if not match or frame not in FRAMES:
        raise HistoryError("invalid")
    root = match[1]
    watch_symbol, venue, exchange = ROOTS[root]
    if watch_symbol not in watched:
        raise HistoryError("not_tracked")
    if not key:
        raise HistoryError("not_configured")

    now = now or datetime.now(timezone.utc)
    cutoff = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cache_id = (ticker, frame, cutoff.date())
    clock = time.monotonic()
    with LOCK:
        cached = CACHE.get(cache_id)
        if cached and clock - cached[0] < 900:
            return cached[1]

    definitions = _request("/futures/v1/contracts", {"ticker": ticker, "type": "single", "limit": 1}, key)
    if len(definitions) != 1 or any(definitions[0].get(k) != v for k, v in
                                   {"ticker": ticker, "product_code": root, "trading_venue": venue, "type": "single"}.items()):
        raise HistoryError("identity")

    resolution, seconds = FRAMES[frame]
    rows = _request("/futures/v1/aggs/" + ticker, {
        "resolution": resolution, "window_start.gte": (cutoff - timedelta(days=90)).date().isoformat(),
        "window_start.lt": cutoff.date().isoformat(), "sort": "window_start.desc", "limit": 300,
    }, key)
    candles = []
    seen = set()
    try:
        for row in rows:
            if row.get("ticker") != ticker:
                raise HistoryError("identity")
            stamp = row["window_start"]
            if type(stamp) is not int or stamp % 1_000_000_000:
                raise ValueError()
            start = datetime.fromtimestamp(stamp // 1_000_000_000, tz=timezone.utc)
            closed = start + timedelta(seconds=seconds)
            if start in seen or closed > cutoff:
                raise ValueError()
            prices = {name: row[name] for name in ("open", "high", "low", "close")}
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in prices.values()):
                raise ValueError()
            if prices["low"] > min(prices.values()) or prices["high"] < max(prices.values()):
                raise ValueError()
            seen.add(start)
            candles.append({"time": start.isoformat(), "closed_at": closed.isoformat(), **prices})
    except HistoryError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, OSError, AttributeError):
        raise HistoryError("provider_failure") from None
    if not candles:
        raise HistoryError("no_data")
    candles.sort(key=lambda row: row["time"])
    payload = {"provider": "Massive", "ticker": ticker, "exchange": exchange, "frame": frame,
               "historical_only": True, "candles": candles, "last_closed_at": candles[-1]["closed_at"]}
    with LOCK:
        if len(CACHE) >= 32:
            CACHE.pop(next(iter(CACHE)))
        CACHE[cache_id] = (clock, payload)
    return payload
