"""Instant Native Analysis V2: deterministic research scenarios from VERIFIED M5 OHLC.

Never assumes licensed data, never fabricates candles, fills, liquidity volumes or
news impact. All entry/target levels are conditional unless a close confirms
the trigger. Scenarios are informational; this module has no broker APIs.
"""
from datetime import datetime, timezone, timedelta
from math import isfinite, ceil, floor
from statistics import mean

STATUS = ("READY", "CONDITIONAL", "NEWS_CAUTION", "DATA_UNAVAILABLE")
DEFAULT_RR = (1.0, 2.0, 3.0)

def unavailable(code, symbol, mode="scalp", provider=None, **details):
    return {
        "version": "instant-native-v2", "symbol": symbol, "mode": mode,
        "status": "DATA_UNAVAILABLE", "reason_code": code, "bias": "UNVERIFIED",
        "provider": provider, "entry": None, "entry_zone": None, "sl": None,
        "targets": [], "confirmation": None, "indicators": {},
        "evidence": {"FVG": "NOT_MEASURED", "IFVG": "NOT_MEASURED",
                     "ORDER_BLOCK": "NOT_MEASURED", "CISD": "NOT_MEASURED",
                     "SMT": "NOT_MEASURED"},
        "news": {"state": "NOT_VERIFIED", "related_events": []},
        "broker_execution": False, "model_calibrated": False,
        "extra": details,
    }

def _as_bars(rows):
    bars = []
    for row in rows:
        if isinstance(row, dict):
            stamp = row["time"]
            prices = [row[k] for k in ("open","high","low","close")]
        else:
            stamp = row[0]
            prices = row[1:5]
        t = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
        if not t.tzinfo:raise ValueError("timezone_missing")
        t=t.astimezone(timezone.utc)
        o,h,l,c=map(float,prices)
        if (not all(isfinite(v) and v>0 for v in (o,h,l,c))
                or h<max(o,c) or l>min(o,c) or h<l
                or t.second or t.minute%5):
            raise ValueError("invalid_ohlc")
        bars.append((t,o,h,l,c))
    bars.sort(key=lambda b:b[0])
    if len({b[0] for b in bars})!=len(bars):
        raise ValueError("duplicate_candle")
    return bars

def aggregate(bars, minutes):
    """Only FULL contiguous UTC-aligned timeframe buckets, no forward fill."""
    if minutes not in (15,60,240):raise ValueError("unsupported_timeframe")
    count=minutes//5
    groups={}
    for bar in bars:
        start=int(bar[0].timestamp())//(minutes*60)*(minutes*60)
        groups.setdefault(start,[]).append(bar)
    out=[]
    for start,g in sorted(groups.items()):
        g.sort(key=lambda b:b[0])
        if len(g)!=count or any(int(bar[0].timestamp())!=start+i*300 for i,bar in enumerate(g)):
            continue
        out.append((datetime.fromtimestamp(start,tz=timezone.utc),g[0][1],
                    max(b[2] for b in g),min(b[3] for b in g),g[-1][4]))
    return out

def _atr(bars,period=14):
    if len(bars)<period+1:return None
    tr=[max(b[2]-b[3],abs(b[2]-a[4]),abs(b[3]-a[4])) for a,b in zip(bars[-period-1:-1],bars[-period:])]
    return mean(tr)

def _tick(v,tick,way="near"):
    n=v/tick
    if way=="up":n=ceil(n-1e-10)
    elif way=="down":n=floor(n+1e-10)
    else:n=round(n)
    return round(n*tick,8)

def news_filter(snapshot, symbol, asset_class, now):
    """Only verified event timing can restrict. Unknown impact must NOT be 'bullish'."""
    if not isinstance(snapshot,dict):
        return {"state":"NOT_VERIFIED","related_events":[]}
    affected={"futures":{"USD"},"forex":{"USD"},"metals":{"USD"},"cfd":{"USD"},"crypto":{"USD"}}.get(asset_class,set())
    if asset_class=="forex":
        ticker=symbol.split(":")[-1]
        affected={ticker[:3],ticker[3:]} if len(ticker)==6 else set()
    flagged=[]
    for event in snapshot.get("calendar",[]):
        if not isinstance(event,dict) or event.get("currency") not in affected:continue
        if not (event.get("feed_fresh") is True and event.get("feed_state")=="CONNECTED"):continue
        try:when=datetime.fromisoformat(str(event["time"]).replace("Z","+00:00")).astimezone(timezone.utc)
        except (TypeError,ValueError,KeyError):continue
        delta=(when-now).total_seconds()/60
        if -15<=delta<=30:
            flagged.append({"title":str(event.get("title",""))[:150],"time":when.isoformat(),
                            "minutes_until":round(delta,1),"currency":event["currency"],
                            "impact_verified":event.get("impact_verified") is True})
    high=[e for e in flagged if e["impact_verified"]]
    return {"state":"NEWS_CAUTION" if high else "EVENT_UNRATED" if flagged else "NO_VERIFIED_EVENT",
            "related_events":flagged[:5],"continuation_bias":"UNVERIFIED",
            "note":"Official event timing alone does not determine BUY/SELL. Unrated events require manual caution."}

def evaluate(symbol,rows,*,mode="scalp",asset_class="forex",provider=None,
             tick_size=0.0001,now=None,news=None,source_identity_verified=False,
             realtime_verified=False):
    now=now or datetime.now(timezone.utc)
    if mode not in ("scalp","swing") or not isinstance(tick_size,(int,float)) or not isfinite(tick_size) or tick_size<=0:
        return unavailable("INVALID_SETTINGS",symbol,mode,provider)
    if not source_identity_verified:
        return unavailable("SOURCE_IDENTITY_UNVERIFIED",symbol,mode,provider)
    try:bars=_as_bars(rows)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError):
        return unavailable("INVALID_OHLC",symbol,mode,provider)
    if len(bars)<300:
        return unavailable("NOT_ENOUGH_M5_HISTORY",symbol,mode,provider,received=len(bars),minimum=300)
    stamp=bars[-1][0];age=(now-stamp).total_seconds()
    # 5m candle is stamped at OPEN, so >=300s means it has fully closed.
    if not 300<=age<=900:
        return unavailable("STALE_OR_UNCLOSED_M5",symbol,mode,provider,age_seconds=round(age))
    if any((b[0]-a[0]).total_seconds()!=300 for a,b in zip(bars[-60:-1],bars[-59:])):
        return unavailable("MISSING_RECENT_M5",symbol,mode,provider)
    m15=aggregate(bars,15);hourly=aggregate(bars,60);four=aggregate(bars,240)
    if len(hourly)<12 or len(four)<3 or len(m15)<20:
        return unavailable("INCOMPLETE_MULTITIMEFRAME_HISTORY",symbol,mode,provider,
                           counts={"M15":len(m15),"H1":len(hourly),"H4":len(four)})
    # Partial latest H1/H4 buckets are NOT treated as closed. Verify current coverage.
    current=int(stamp.timestamp())
    if int(hourly[-1][0].timestamp())//3600 < current//3600-1:
        return unavailable("STALE_H1",symbol,mode,provider)
    if int(four[-1][0].timestamp())//14400 < current//14400-1:
        return unavailable("STALE_H4",symbol,mode,provider)
    h1close=hourly[-1][4];h1prev=hourly[-2][4]
    h4close=four[-1][4];h4prev=four[-2][4]
    bias=("BULLISH" if h1close>h1prev and h4close>=h4prev else
          "BEARISH" if h1close<h1prev and h4close<=h4prev else "RANGING")
    # Previous UTC day levels are references, NOT guaranteed session PDH/PDL.
    last_date=stamp.date()
    prior_days=sorted({b[0].date() for b in bars if b[0].date()<last_date})
    previous=prior_days[-1] if prior_days else None
    daybars=[b for b in bars if b[0].date()==previous] if previous else []
    pdh=max((x[2] for x in daybars),default=None)
    pdl=min((x[3] for x in daybars),default=None)
    atr=_atr(bars)
    if atr is None or atr<=0:
        return unavailable("ATR_UNAVAILABLE",symbol,mode,provider)
    lookback=12 if mode=="scalp" else 36
    recent=bars[-lookback-1:-1]
    recent_high=max(b[2] for b in recent);recent_low=min(b[3] for b in recent)
    curr=bars[-1]
    sweep_high=curr[2]>recent_high and curr[4]<recent_high
    sweep_low=curr[3]<recent_low and curr[4]>recent_low
    # FVG only when a real 3-bar wick gap exists; return zone not confirmation.
    fvg_up=bars[-3][2]<bars[-1][3]
    fvg_down=bars[-3][3]>bars[-1][2]
    fvg={"type":"BULLISH","zone":[bars[-3][2],bars[-1][3]]} if fvg_up else (
        {"type":"BEARISH","zone":[bars[-1][2],bars[-3][3]]} if fvg_down else None)
    side="SELL" if sweep_high else "BUY" if sweep_low else ("BUY" if bias!="BEARISH" else "SELL")
    if bias=="RANGING" and not (sweep_low or sweep_high):
        side="BUY" if curr[4]<(recent_high+recent_low)/2 else "SELL"
    sign=1 if side=="BUY" else -1
    trigger=_tick(recent_high+tick_size,tick_size,"up") if sign==1 else _tick(recent_low-tick_size,tick_size,"down")
    # Opposite wick side is idea invalidation; ATR buffer >=1 tick.
    buffer=max(tick_size,atr*.15)
    anchor=min(b[3] for b in recent[-8:]+[curr]) if sign==1 else max(b[2] for b in recent[-8:]+[curr])
    stop=_tick(anchor-buffer,tick_size,"down") if sign==1 else _tick(anchor+buffer,tick_size,"up")
    risk=(trigger-stop)*sign
    if risk<=tick_size*.9 or risk>atr*8:
        return unavailable("RISK_GEOMETRY_UNSAFE",symbol,mode,provider)
    confirmed=(curr[4]>=trigger if sign==1 else curr[4]<=trigger)
    nr=news_filter(news,symbol,asset_class,now)
    status="NEWS_CAUTION" if nr["state"]=="NEWS_CAUTION" else "READY" if confirmed else "CONDITIONAL"
    targets=[{"name":f"TP{i}","price":_tick(trigger+sign*risk*i,tick_size,
             "up" if sign>0 else "down"),"rr_nominal":float(i),
              "reason":"Risk multiple benchmark; validate against actual external liquidity"} for i in (1,2,3)]
    evidence={"LIQUIDITY_SWEEP":"HIGH" if sweep_high else "LOW" if sweep_low else "NOT_DETECTED",
              "TURTLE_SOUP":"POTENTIAL" if sweep_high or sweep_low else "NOT_DETECTED",
              "FVG":fvg or "NOT_DETECTED","IFVG":"NOT_MEASURED",
              "ORDER_BLOCK":"NOT_MEASURED","CISD":"NOT_MEASURED","SMT":"NOT_MEASURED"}
    return {"version":"instant-native-v2","symbol":symbol,"mode":mode,
            "status":status,"reason_code":"NEWS_RESTRICTION" if status=="NEWS_CAUTION"
               else "M5_BREAKOUT_CONFIRMED" if confirmed else "AWAIT_M5_CLOSE_ABOVE_OR_BELOW_TRIGGER",
            "bias":bias,"bias_reason":"Last two completed H1 and H4 candle closes; not a calibrated probability",
            "provider":provider,"source_time":stamp.isoformat(),"source_age_seconds":round(age),
            "realtime_verified":bool(realtime_verified),"entry":trigger,"entry_zone":[trigger,trigger],
            "sl":stop,"targets":targets,"confirmation":{"type":"M5_CLOSE",
                "direction":side,"level":trigger,"confirmed":confirmed},
            "invalidated_if":"Price breaches stop level before confirmation",
            "indicators":{"ATR_M5":round(atr,8),"PDH_UTC":pdh,"PDL_UTC":pdl,
                          "M15_close":m15[-1][4],"H1_close":h1close,"H4_close":h4close,
                          "tick_size":tick_size},
            "evidence":evidence,"news":nr,"technical_direction":side,
            "broker_execution":False,"model_calibrated":False,
            "disclaimer":"Research plan only. Spread/slippage/fees and liquidity execution not verified."}
