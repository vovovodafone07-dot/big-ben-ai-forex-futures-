"""Independent, read-only M5 setup candidates from actual closed provider candles.

These are research candidates, NEVER authenticated TradingView BUY/SELL signals.
No order execution, notifications, fabricated bars, or promises of profitability.
"""
from datetime import datetime, timezone
import math

def evaluate(rows, *, now=None, mode="scalp", rr=2.5):
    now = now or datetime.now(timezone.utc)
    result = {"state":"INSUFFICIENT_DATA","candidate":None,"source":"Twelve Data stored M5 candles",
              "confirmed_signal":False,"execution_enabled":False,
              "note":"إعداد بحثي مستقل وليس إشارة TradingView مؤكدة أو توصية تنفيذ."}
    if mode != "scalp":
        result["state"]="SWING_ENGINE_NOT_VALIDATED"
        return result
    candles=[]
    for row in sorted(rows, key=lambda item: str(item[0])):
        try:
            stamp,op,hi,lo,cl=row
            dt=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
            vals=list(map(float,(op,hi,lo,cl)))
            if dt.tzinfo is None or not all(math.isfinite(v) and v>0 for v in vals):
                return {**result,"state":"INVALID_CANDLE"}
            if hi is None or vals[1]<max(vals[0],vals[3]) or vals[2]>min(vals[0],vals[3]):
                return {**result,"state":"INVALID_CANDLE"}
            candles.append((dt.astimezone(timezone.utc),*vals))
        except (TypeError,ValueError,IndexError):
            return {**result,"state":"INVALID_CANDLE"}
    if len(candles)<55:
        return {**result,"available_bars":len(candles)}
    newest=candles[-1][0]
    age=(now-newest).total_seconds()
    result.update(last_candle=newest.isoformat(),age_seconds=int(age))
    if age < 300 or age > 900:
        return {**result,"state":"STALE_OR_UNCLOSED"} 
    # Validate actual adjacent bars across all windows used for trend and stops.
    window=candles[-55:]
    if any((b[0]-a[0]).total_seconds()!=300 for a,b in zip(window,window[1:])):
        return {**result,"state":"MISSING_BARS"}
    closes=[c[4] for c in window]
    def ema(values,n):
        value=sum(values[:n])/n
        for x in values[n:]:value=(2/(n+1))*x+(1-2/(n+1))*value
        return value
    fast=ema(closes,20);slow=ema(closes,50)
    previous=window[-2];current=window[-1]
    prev_high=max(x[2] for x in window[-13:-1])
    prev_low=min(x[3] for x in window[-13:-1])
    tr=[max(x[2]-x[3],abs(x[2]-p[4]),abs(x[3]-p[4])) for p,x in zip(window[-16:-1],window[-15:])]
    atr=sum(tr[-14:])/14
    if not math.isfinite(atr) or atr<=0:return {**result,"state":"INVALID_VOLATILITY"}
    buy=current[4]>fast>slow and current[4]>prev_high and current[4]>current[1]
    sell=current[4]<fast<slow and current[4]<prev_low and current[4]<current[1]
    if not (buy or sell):
        return {**result,"state":"NO_SETUP","reason":"trend_and_closed_breakout_not_aligned",
                "market_bias":"UP" if fast>slow else "DOWN" if fast<slow else "FLAT"}
    side="BUY" if buy else "SELL"
    entry=current[4]
    stop=(min(x[3] for x in window[-9:]) if buy else max(x[2] for x in window[-9:]))
    risk=abs(entry-stop)
    if risk<=0 or not .2*atr<=risk<=3*atr:return {**result,"state":"RISK_OUT_OF_RANGE"}
    target=entry+(risk*rr if buy else -risk*rr)
    if not (stop<entry<target if buy else target<entry<stop):
        return {**result,"state":"INVALID_GEOMETRY"}
    result["candidate"]={"event":side,"entry":round(entry,8),"sl":round(stop,8),
                         "tp":round(target,8),"rr":rr,"timeframe":"M5",
                         "status":"UNCONFIRMED_RESEARCH_CANDIDATE",
                         "source_time":newest.isoformat(),"risk_source":"9 real M5 candles",
                         "costs_included":False,"realtime_feed_verified":False}
    result["state"]="CANDIDATE_RESEARCH_ONLY"
    return result
