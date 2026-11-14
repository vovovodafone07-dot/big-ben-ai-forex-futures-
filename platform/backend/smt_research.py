"""Historical paired-candle evidence. Never changes Pine's SMT filter or votes."""
import math
from datetime import datetime, timezone


def measure(primary, peer, now=None):
    now=now or datetime.now(timezone.utc)
    result={"state":"INSUFFICIENT_DATA","provider":"Twelve Data historical candles",
        "correlation":None,"return_samples":0,"candidate_supported":False,
        "bullish_divergence":None,"bearish_divergence":None,"fresh_history":False,
        "live_smt_confirmed":False,"pine_filter_override_allowed":False,
        "note":"Historical research from a separate feed; not confirmation of current TradingView SMT."}
    def clean(rows):
        cleaned={}
        for row in rows:
            try:
                stamp=datetime.fromisoformat(row["time"].replace("Z","+00:00"))
                if stamp.tzinfo is None or (now-stamp).total_seconds()<300:continue
                values={key:row[key] for key in ("high","low","close")}
                if any(type(v) not in (float,int) or not math.isfinite(v) or v<=0 for v in values.values()):continue
                if not values["low"]<=values["close"]<=values["high"]:continue
                if stamp in cleaned:raise ValueError("duplicate_candle")
                cleaned[stamp]=values
            except (KeyError,TypeError,AttributeError,OverflowError):continue
        return cleaned
    try:a,b=clean(primary),clean(peer)
    except ValueError:return {**result,"state":"INVALID_DATA"}
    times=sorted(set(a)&set(b))[-121:]
    if times:
        age=(now-times[-1]).total_seconds()
        result.update(last_candle=times[-1].isoformat(),last_candle_age_seconds=int(age),fresh_history=300<=age<900,aligned_candles=len(times))
    returns=[]
    for before,after in zip(times,times[1:]):
        # Skip missing bars and session gaps; never bridge them with made-up data.
        if (after-before).total_seconds()!=300:continue
        returns.append((math.log(a[after]["close"]/a[before]["close"]),math.log(b[after]["close"]/b[before]["close"])))
    result["return_samples"]=len(returns)
    if len(returns)<60:return result
    x=[p[0] for p in returns];y=[p[1] for p in returns]
    mx=sum(x)/len(x);my=sum(y)/len(y)
    xx=sum((v-mx)**2 for v in x);yy=sum((v-my)**2 for v in y)
    if xx<=0 or yy<=0:return {**result,"state":"ZERO_VARIANCE"}
    r=max(-1.,min(1.,sum((u-mx)*(v-my) for u,v in returns)/math.sqrt(xx*yy)))
    result.update(state="MEASURED_HISTORICAL",correlation=round(r,6),candidate_supported=r>=.6)
    recent=times[-21:]
    contiguous=len(recent)==21 and (recent[-1]-recent[0]).total_seconds()==6000
    if contiguous and r>=.6:
        current,previous=recent[-1],recent[:-1]
        result["bullish_divergence"]=a[current]["low"]<min(a[t]["low"] for t in previous) and b[current]["low"]>=min(b[t]["low"] for t in previous)
        result["bearish_divergence"]=a[current]["high"]>max(a[t]["high"] for t in previous) and b[current]["high"]<=max(b[t]["high"] for t in previous)
    return result


def from_storage(connection,symbol,candidate,postgres=False,now=None):
    def forex_key(value):
        if not isinstance(value,str) or not value.startswith('OANDA:'):return None
        ticker=value.split(':',1)[1]
        if len(ticker)!=6 or not ticker.isalpha() or ticker[:3] in ('XAU','XAG'):return None
        return ticker[:3]+'/'+ticker[3:]
    primary,peer=forex_key(symbol),forex_key(candidate)
    if not primary or not peer:return {"state":"NO_MATCHING_HISTORY","live_smt_confirmed":False,"pine_filter_override_allowed":False}
    marker='%s' if postgres else '?'
    def load(key):
        rows=connection.execute("SELECT time,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker+" ORDER BY time DESC LIMIT 500",(key,)).fetchall()
        return [dict(zip(('time','high','low','close'),r)) for r in rows]
    return {"primary_symbol":symbol,"comparison_symbol":candidate,**measure(load(primary),load(peer),now)}
