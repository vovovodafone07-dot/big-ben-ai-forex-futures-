"""Native chart analysis from actual provider M5 OHLC. Never reads TradingView webhook events.

Signal labels are *research setups*, not orders, verified fills, or AI predictions.
Swing bars are aggregated ONLY from complete contiguous M5 source bars.
"""
import math
from datetime import datetime, timezone

def _ema(values, period):
    if len(values)<period:return None
    avg=sum(values[:period])/period
    alpha=2/(period+1)
    for v in values[period:]:avg=alpha*v+(1-alpha)*avg
    return avg

def _atr(bars,period=14):
    if len(bars)<period+1:return None
    values=[max(c[2]-c[3],abs(c[2]-p[4]),abs(c[3]-p[4])) for p,c in zip(bars[:-1],bars[1:])]
    return sum(values[-period:])/period

def _aggregate(rows,minutes):
    """Return only fully covered timeframe buckets; omit partial or gapped buckets."""
    step=minutes//5
    groups={}
    for b in rows:
        key=int(b[0].timestamp())//(minutes*60)
        groups.setdefault(key,[]).append(b)
    out=[]
    for key,items in sorted(groups.items()):
        if len(items)!=step:continue
        start=datetime.fromtimestamp(key*minutes*60,tz=timezone.utc)
        if items[0][0]!=start:continue
        if any((y[0]-x[0]).total_seconds()!=300 for x,y in zip(items,items[1:])):continue
        out.append((start,items[0][1],max(x[2] for x in items),min(x[3] for x in items),items[-1][4]))
    return out

def _setup(bars, mode, rr):
    timeframe="M5" if mode=="scalp" else "H1"
    if len(bars)<(55 if mode=="scalp" else 35):
        return {"state":"INSUFFICIENT_DATA","reason":"not_enough_closed_"+timeframe,"available_bars":len(bars)}
    short=20 if mode=="scalp" else 10
    long=50 if mode=="scalp" else 25
    closes=[b[4] for b in bars]
    fast=_ema(closes,short);slow=_ema(closes,long)
    atr=_atr(bars)
    if not atr or not math.isfinite(atr) or atr<=0:
        return {"state":"INSUFFICIENT_DATA","reason":"atr_unavailable"}
    now,prev=bars[-1],bars[-2]
    high=max(x[2] for x in bars[-9:-1])
    low=min(x[3] for x in bars[-9:-1])
    rising=now[4]>fast>slow
    falling=now[4]<fast<slow
    # Breakout OR momentum-recovery after a real pullback, based on completed bars.
    breakout_up=now[4]>high and now[4]>now[1]
    breakout_down=now[4]<low and now[4]<now[1]
    recover_up=prev[4]<=fast and now[4]>fast and now[4]>prev[4] and now[4]>now[1]
    recover_down=prev[4]>=fast and now[4]<fast and now[4]<prev[4] and now[4]<now[1]
    buy=rising and (breakout_up or recover_up)
    sell=falling and (breakout_down or recover_down)
    bias="BULLISH" if fast>slow else "BEARISH" if fast<slow else "MIXED"
    if not (buy or sell):
        return {"state":"NO_SETUP","reason":"trend_and_price_trigger_not_aligned","bias":bias,
                "indicators":{"ema_fast":round(fast,8),"ema_slow":round(slow,8),"atr":round(atr,8)}}
    side="BUY" if buy else "SELL"
    pattern="BREAKOUT" if (breakout_up if buy else breakout_down) else "PULLBACK_RECOVERY"
    entry=now[4]
    previous_window=bars[-7:]
    stop=min(x[3] for x in previous_window) if buy else max(x[2] for x in previous_window)
    risk=abs(entry-stop)
    if not 0.20*atr<=risk<=4*atr:
        return {"state":"RISK_OUT_OF_RANGE","reason":"stop_distance_outside_atr_range","bias":bias}
    target=entry+(risk*rr if buy else -risk*rr)
    if not (stop<entry<target if buy else target<entry<stop):
        return {"state":"INVALID_GEOMETRY","reason":"invalid_price_levels"}
    return {"state":"CANDIDATE_RESEARCH_ONLY","reason":"native_price_trigger","bias":bias,
            "candidate":{"event":side,"entry":round(entry,8),"sl":round(stop,8),"tp":round(target,8),
                "rr":rr,"timeframe":timeframe,"pattern":pattern,"source_time":now[0].isoformat(),
                "status":"UNCONFIRMED_PLATFORM_SETUP","realtime_feed_verified":False,
                "costs_included":False,"broker_execution":False},
            "indicators":{"ema_fast":round(fast,8),"ema_slow":round(slow,8),"atr":round(atr,8)}}

def evaluate(rows, mode="scalp", now=None, rr=2.5):
    now=now or datetime.now(timezone.utc)
    result={"state":"INSUFFICIENT_DATA","candidate":None,"analysis_origin":"platform_native",
            "source":"Twelve Data M5 OHLC","uses_tradingview_signals":False,
            "realtime_feed_verified":False,"broker_execution":False,"mode":mode,
            "note":"دراسة فنية آلية من شموع حقيقية؛ ليست توصية تنفيذ أو إشارة TradingView."}
    if mode not in ("scalp","swing") or not (0.5<=rr<=5):
        return {**result,"state":"INVALID_MODE"}
    candles=[]
    try:
        for raw in sorted(rows,key=lambda r:str(r[0])):
            if len(raw)<5:raise ValueError()
            dt=datetime.fromisoformat(str(raw[0]).replace("Z","+00:00"))
            v=[float(z) for z in raw[1:5]]
            if dt.tzinfo is None or not all(math.isfinite(z) and z>0 for z in v):
                raise ValueError()
            if v[1]<max(v[0],v[3]) or v[2]>min(v[0],v[3]):raise ValueError()
            candles.append((dt.astimezone(timezone.utc),*v))
    except (ValueError,TypeError,OverflowError,IndexError):
        return {**result,"state":"INVALID_CANDLE"}
    if len(candles)<55:
        return {**result,"state":"INSUFFICIENT_DATA","available_bars":len(candles)}
    close_time=candles[-1][0]
    age=(now-close_time).total_seconds()
    result.update(source_time=close_time.isoformat(),age_seconds=int(age),
                  available_bars=len(candles))
    if not 300<=age<=900:
        return {**result,"state":"STALE_OR_UNCLOSED"}
    # Recent M5 observations must be consecutive; no fake gaps/weekend fill.
    if any((b[0]-a[0]).total_seconds()!=300 for a,b in zip(candles[-55:-1],candles[-54:])):
        return {**result,"state":"MISSING_RECENT_M5_BARS"}
    if mode=="scalp":
        setup=_setup(candles[-100:],"scalp",rr)
    else:
        hourly=_aggregate(candles,60)
        four_hourly=_aggregate(candles,240)
        # Must end with the most recently completed H1/H4 bars, not old buckets.
        latest_hour_bucket=int(close_time.timestamp())//3600
        latest_h4_bucket=int(close_time.timestamp())//14400
        if len(hourly)<35 or len(four_hourly)<12:
            return {**result,"state":"INSUFFICIENT_HTF_HISTORY","h1_bars":len(hourly),"h4_bars":len(four_hourly)}
        if int(hourly[-1][0].timestamp())//3600<latest_hour_bucket-1 or int(four_hourly[-1][0].timestamp())//14400<latest_h4_bucket-1:
            return {**result,"state":"STALE_HTF_DATA"}
        trend4=_ema([x[4] for x in four_hourly],10)
        trend4_prev=_ema([x[4] for x in four_hourly[:-1]],10)
        setup=_setup(hourly,"swing",rr)
        if setup.get("candidate"):
            side=setup["candidate"]["event"]
            if trend4 is None or trend4_prev is None or not (four_hourly[-1][4]>trend4 and trend4>=trend4_prev if side=="BUY" else four_hourly[-1][4]<trend4 and trend4<=trend4_prev):
                setup={"state":"HTF_FILTER_REJECTED","reason":"H4_direction_not_confirmed"}
        setup["timeframes"]={"H1_bars":len(hourly),"H4_bars":len(four_hourly),
                              "H4_ema10":round(trend4,8) if trend4 else None}
    return {**result,**setup,"candidate":setup.get("candidate")}
