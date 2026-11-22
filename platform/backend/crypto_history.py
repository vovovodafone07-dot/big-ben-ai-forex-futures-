"""Read-only, public Bitstamp M5 spot candles.

This is ONLY for actual BITSTAMP exchange-qualified crypto symbols. It does not
represent Binance, Coinbase, a CFD or futures contract, and cannot place orders.
The present/open candle is excluded. Unavailable pairs raise explicit errors.
"""
import json
import math
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

PROVIDER = "Bitstamp"
MAX_BYTES = 2_000_000
ADAPTER_VERSION = 1

class CryptoHistoryError(ValueError):
    pass

def pair_from_symbol(symbol):
    if not isinstance(symbol, str) or not re.fullmatch(r"BITSTAMP:[A-Z0-9]{6,16}", symbol):
        raise CryptoHistoryError("exchange_not_supported")
    return symbol.partition(":")[2].lower()

def fetch_m5(symbol, now=None, opener=None):
    pair = pair_from_symbol(symbol)
    now = now or datetime.now(timezone.utc)
    opener = opener or urllib.request.urlopen
    params = urlencode({"step": 300, "limit": 1000, "exclude_current_candle": "true"})
    url = "https://www.bitstamp.net/api/v2/ohlc/" + pair + "/?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "BigBenAIPro-CryptoHistory/1.0", "Accept": "application/json"})
    try:
        with opener(req, timeout=9) as response:
            raw = response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise CryptoHistoryError("response_too_large")
        data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise CryptoHistoryError("pair_not_listed" if exc.code in (400,404) else "provider_http_error") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CryptoHistoryError("connection_failure") from None
    except (TypeError, ValueError, OverflowError):
        raise CryptoHistoryError("invalid_response") from None
    if not isinstance(data,dict) or not isinstance(data.get("data"),dict):
        raise CryptoHistoryError("invalid_response")
    detail=data["data"]
    # Validate exchange's asserted market identity: never silently substitute a pair.
    name=str(detail.get("pair") or detail.get("market") or "").upper().replace("/","").replace("-","")
    if name!=pair.upper():
        raise CryptoHistoryError("instrument_metadata_mismatch")
    candles=detail.get("ohlc")
    if not isinstance(candles,list) or not 1<=len(candles)<=1000:
        raise CryptoHistoryError("invalid_candle_count")
    rows,duplicate,incomplete=[],0,0
    for bar in candles:
        try:
            stamp=int(bar["timestamp"])
            if stamp%300:raise ValueError()
            dt=datetime.fromtimestamp(stamp,tz=timezone.utc)
            if dt>now:raise ValueError()
            prices={x:float(bar[x]) for x in ("open","high","low","close")}
            if any(type(bar[x]) is bool for x in prices) or not all(math.isfinite(x) and x>0 for x in prices.values()):
                raise ValueError()
            if prices["high"]<max(prices["open"],prices["close"]) or prices["low"]>min(prices["open"],prices["close"]):
                raise ValueError()
            if (now-dt).total_seconds()<300:
                incomplete+=1
                continue
            rows.append({"time":dt.isoformat(),**prices})
        except (KeyError, TypeError, ValueError, OverflowError):
            raise CryptoHistoryError("invalid_candle") from None
    ordered=sorted(rows,key=lambda x:x["time"])
    seen=set()
    out=[]
    for bar in ordered:
        if bar["time"] in seen:
            duplicate+=1
            continue
        seen.add(bar["time"]);out.append(bar)
    if not out:
        raise CryptoHistoryError("no_closed_candles")
    age=(now-datetime.fromisoformat(out[-1]['time'])).total_seconds()
    fresh=300<=age<=630
    return out,{"provider":PROVIDER,"symbol":symbol,"interval":"5min","adapter_version":ADAPTER_VERSION,
      "timezone_basis":"bitstamp_epoch_UTC","checked_at":now.isoformat(),
      "realtime_verified":False,"candles_received":len(out),
      "incomplete_candles_excluded":incomplete,"duplicate_candles_excluded":duplicate,
      "last_candle":out[-1]["time"],"source_age_seconds":round(age),"fresh":fresh,"synthetic_bars_created":0,"state":"CONNECTED" if fresh else "STALE",
      "reason":"bitstamp_closed_m5_public_spot" if fresh else "bitstamp_closed_m5_stale"}

def store_check(connection,symbol,meta,rows=(),postgres=False):
    pair_from_symbol(symbol)
    mark="%s" if postgres else "?"
    meta=dict(meta)
    for bar in rows:
        values=(PROVIDER,symbol,bar["time"],bar["open"],bar["high"],bar["low"],bar["close"],meta["checked_at"])
        connection.execute("INSERT INTO market_candles (provider,symbol,time,open,high,low,close,received_at) VALUES ("+",".join([mark]*8)+") ON CONFLICT(provider,symbol,time) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,received_at=excluded.received_at",values)
    connection.execute("INSERT INTO market_history_checks(symbol,checked_at,payload) VALUES ("+",".join([mark]*3)+") ON CONFLICT(symbol) DO UPDATE SET checked_at=excluded.checked_at,payload=excluded.payload",(symbol,meta["checked_at"],json.dumps(meta)))
    return meta
