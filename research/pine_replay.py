"""Research translation of v6.4.1 rules, not a certified Pine runtime or broker.

Input times are M5 OPEN times. HTF values must be closed by that open time,
matching the source's expression[1]/lookahead_on convention. Derived UTC HTF
buckets are an explicit research assumption, not verified exchange sessions.
"""
import hashlib
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("replay_quality", ROOT / "candle_quality.py")
_quality = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_quality)
DEFAULTS = dict(rr=2.5, side="Both", mode="Breakout + Retest", lookback=20,
    retest_bars=6, swing=8, cooldown=8, min_body=.25, break_buffer=.05,
    max_risk_atr=4.0, htf_mode="Balanced", use_hybrid=True, min_evidence=1,
    pivot_len=3, enable_smt=False, use_ha=False, use_atr_floor=False,
    atr_floor_len=50, atr_floor_factor=.6)
ENGINE_SHA256 = hashlib.sha256((Path(__file__).read_text(encoding="utf-8") +
    (ROOT / "candle_quality.py").read_text(encoding="utf-8")).encode()).hexdigest()


def configuration(overrides=None):
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("invalid replay configuration")
    if set(overrides or {}) - set(DEFAULTS):
        raise ValueError("unknown replay parameter")
    result = {**DEFAULTS, **(overrides or {})}
    bounds = {"rr": (.5,20), "lookback": (5,100), "retest_bars": (1,30),
        "swing": (3,30), "cooldown": (0,100), "min_body": (0,3),
        "break_buffer": (0,2), "max_risk_atr": (.5,20), "min_evidence": (1,8),
        "pivot_len": (2,15), "atr_floor_len": (10,200), "atr_floor_factor": (.1,2)}
    for key,(low,high) in bounds.items():
        value=result[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError("invalid replay parameter: "+key)
        if type(DEFAULTS[key]) is int and type(value) is not int:
            raise ValueError("integer replay parameter required: "+key)
    for key in ("use_hybrid","enable_smt","use_ha","use_atr_floor"):
        if type(result[key]) is not bool:raise ValueError("boolean replay parameter required")
    for key,options in {"side":("Both","Buy","Sell"),
        "mode":("Breakout + Retest","Confirmed breakout"),
        "htf_mode":("Balanced","Strict","Off")}.items():
        if result[key] not in options:raise ValueError("invalid replay mode")
    return result


def atr_series(rows, length=14):
    """Wilder RMA, seeded by the first length true ranges."""
    result=[];ranges=[];value=None
    for i,row in enumerate(rows):
        previous=rows[i-1]["close"] if i else row["close"]
        ranges.append(max(row["high"]-row["low"],abs(row["high"]-previous),abs(row["low"]-previous)))
        if i==length-1:value=sum(ranges[:length])/length
        elif i>=length:value=(value*(length-1)+ranges[-1])/length
        result.append(value)
    return result


def confirmed_pivot(values, index, strength, high=True):
    """Confirm only at candidate+strength; rightmost equal extreme wins.

    Equal-extreme tie behavior remains an explicit Pine parity test item.
    """
    candidate=index-strength
    if candidate<strength:return None
    value=values[candidate]
    left=values[candidate-strength:candidate]
    right=values[candidate+1:index+1]
    valid=(all(value>=x for x in left) and all(value>x for x in right)) if high else (
        all(value<=x for x in left) and all(value<x for x in right))
    return value if valid else None


def confirmed_biases(rows, minutes, anchor_minutes=0):
    """Aggregate only COMPLETE UTC buckets, publish after the HTF closes.

    Index selection uses the M5 open, never the current M5 close. A partial
    first bucket or a bucket with missing M5 candles cannot seed the EMA.
    """
    if type(minutes) is not int or minutes not in (15,60,240) or type(anchor_minutes) is not int or not 0<=anchor_minutes<240 or anchor_minutes%5:
        raise ValueError("invalid HTF bucket configuration")
    buckets={}
    for row in rows:
        stamp=datetime.fromisoformat(row["time"])
        seconds=int(stamp.timestamp())
        start=((seconds-anchor_minutes*60)//(minutes*60))*(minutes*60)+anchor_minutes*60
        buckets.setdefault(start,[]).append(row)
    series=[];fast=None;slow=None
    for start,items in sorted(buckets.items()):
        if len(items)!=minutes//5:continue
        expected=[start+i*300 for i in range(minutes//5)]
        if [int(datetime.fromisoformat(r["time"]).timestamp()) for r in items]!=expected:continue
        close=items[-1]["close"]
        fast=close if fast is None else (2/11)*close+(1-2/11)*fast
        slow=close if slow is None else (2/21)*close+(1-2/21)*slow
        bias=1 if fast>slow and close>slow else -1 if fast<slow and close<slow else 0
        series.append((start+minutes*60,bias))
    result=[];cursor=0;current=None
    for row in rows:
        stamp=datetime.fromisoformat(row["time"]).timestamp()
        while cursor<len(series) and series[cursor][0]<=stamp:
            current=series[cursor][1];cursor+=1
        result.append(current)
    return result


def cost_model(costs):
    if costs is None:return None
    keys=("spread_price","slippage_price_per_side","commission_price_round_trip")
    if not isinstance(costs,dict) or set(costs)!=set(keys):raise ValueError("explicit cost assumptions required")
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in costs.values()):
        raise ValueError("invalid execution cost")
    if not math.isfinite(costs["spread_price"]+2*costs["slippage_price_per_side"]+costs["commission_price_round_trip"]):
        raise ValueError("invalid execution cost")
    return dict(costs)


def metrics(trades):
    resolved=[t for t in trades if t["outcome"] in ("tp","sl")]
    gross=[t["gross_r"] for t in resolved]
    conservative=[(-1 if t["outcome"]=="ambiguous_both" else t["gross_r"]) for t in trades if t["outcome"]!="unresolved"]
    equity=peak=drawdown=0;streak=max_streak=0
    for value in conservative:
        equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
        streak=streak+1 if value<0 else 0;max_streak=max(max_streak,streak)
    losses=-sum(x for x in gross if x<0);wins=sum(x for x in gross if x>0)
    net=[t["net_r"] for t in resolved]
    return {"trades":len(trades),"resolved":len(resolved),
        "wins":sum(t["outcome"]=="tp" for t in resolved),
        "losses":sum(t["outcome"]=="sl" for t in resolved),
        "ambiguous":sum(t["outcome"]=="ambiguous_both" for t in trades),
        "unresolved":sum(t["outcome"]=="unresolved" for t in trades),
        "win_rate":sum(t["outcome"]=="tp" for t in resolved)/len(resolved) if resolved else None,
        "gross_r":sum(gross),"profit_factor":wins/losses if losses else None,
        "expectancy_r":sum(gross)/len(gross) if gross else None,
        "net_r":sum(net) if net and all(v is not None for v in net) else None,
        "conservative_r":sum(conservative),"max_drawdown_r_conservative":drawdown,
        "max_consecutive_losses_conservative":max_streak,
        "minimum_review_trades_met":len(resolved)>=30}


def replay(candles, tick_size, config=None, costs=None, peer_candles=None, now=None,
           htf_anchor_minutes=0):
    cfg=configuration(config);costs=cost_model(costs)
    if type(tick_size) not in (int,float) or not math.isfinite(tick_size) or tick_size<=0:
        raise ValueError("verified tick_size required")
    if not 1<=len(candles)<=10000:raise ValueError("candle budget must be 1..10000")
    rows,quality=_quality.validate_candles(candles,now)
    if any(datetime.fromisoformat(r["time"]).timestamp()%300 for r in rows):
        raise ValueError("M5 times must align to 5-minute boundaries")
    peer={}
    if peer_candles:
        peer_rows,_=_quality.validate_candles(peer_candles,now)
        for i,row in enumerate(peer_rows):
            prior=peer_rows[max(0,i-cfg["lookback"]):i]
            if prior:peer[row["time"]]=(row,max(x["high"] for x in prior),min(x["low"] for x in prior))
    highs=[r["high"] for r in rows];lows=[r["low"] for r in rows]
    atrs=atr_series(rows)
    biases={str(m):confirmed_biases(rows,m,htf_anchor_minutes) for m in (15,60,240)}
    last_ph=last_pl=None;pending=None;last_entry=None;active=None;ha_open=None;ha_close=None
    trades=[];diagnostics=[];hi_series=[];lo_series=[];rejections=Counter()
    for i,r in enumerate(rows):
        o,h,l,c=[r[k] for k in ("open","high","low","close")]
        prior=rows[max(0,i-cfg["lookback"]):i]
        hi=max((x["high"] for x in prior),default=None)
        lo=min((x["low"] for x in prior),default=None)
        prev_hi=hi_series[-1] if hi_series else None;prev_lo=lo_series[-1] if lo_series else None
        hi_series.append(hi);lo_series.append(lo)
        prev=rows[i-1] if i else None;atr=atrs[i]
        new_ha_close=(o+h+l+c)/4
        ha_open=(o+c)/2 if ha_open is None else (ha_open+ha_close)/2
        ha_close=new_ha_close
        if not math.isfinite(ha_open) or not math.isfinite(ha_close) or (atr is not None and not math.isfinite(atr)):
            raise ValueError("nonfinite indicator calculation")
        ph=confirmed_pivot(highs,i,cfg["pivot_len"])
        pl=confirmed_pivot(lows,i,cfg["pivot_len"],False)
        if ph is not None:last_ph=ph
        if pl is not None:last_pl=pl
        body=atr is not None and abs(c-o)>=atr*cfg["min_body"]
        break_up=bool(body and hi is not None and prev_hi is not None and c>hi+atr*cfg["break_buffer"] and c>o and prev["close"]<=prev_hi)
        break_dn=bool(body and lo is not None and prev_lo is not None and c<lo-atr*cfg["break_buffer"] and c<o and prev["close"]>=prev_lo)
        bos_up=bool(prev and last_ph is not None and c>last_ph and prev["close"]<=last_ph)
        bos_dn=bool(prev and last_pl is not None and c<last_pl and prev["close"]>=last_pl)
        p=cfg["pivot_len"];old_index=i-2*p
        old_lows=lows[max(0,old_index-4*p+1):old_index+1] if old_index>=0 else []
        old_highs=highs[max(0,old_index-4*p+1):old_index+1] if old_index>=0 else []
        peer_at=peer.get(r["time"])
        buy_votes={"bos":bos_up,"fvg":i>=2 and l>highs[i-2],
            "sweep":last_pl is not None and l<last_pl and c>last_pl,
            "turtle_soup":lo is not None and l<lo and c>lo and c>o,
            "crt":bool(prev and l<prev["low"] and c>prev["low"] and c<prev["high"] and c>o),
            "cisd":bool(prev and c>prev["open"] and prev["close"]<prev["open"] and c>o),
            "qm":bool(bos_up and old_lows and min(lows[max(0,i-2*p+1):i+1])>min(old_lows)),
            "smt":bool(cfg["enable_smt"] and peer_at and lo is not None and l<lo and peer_at[0]["low"]>=peer_at[2])}
        sell_votes={"bos":bos_dn,"fvg":i>=2 and h<lows[i-2],
            "sweep":last_ph is not None and h>last_ph and c<last_ph,
            "turtle_soup":hi is not None and h>hi and c<hi and c<o,
            "crt":bool(prev and h>prev["high"] and c<prev["high"] and c>prev["low"] and c<o),
            "cisd":bool(prev and c<prev["open"] and prev["close"]>prev["open"] and c<o),
            "qm":bool(bos_dn and old_highs and max(highs[max(0,i-2*p+1):i+1])<max(old_highs)),
            "smt":bool(cfg["enable_smt"] and peer_at and hi is not None and h>hi and peer_at[0]["high"]<=peer_at[1])}
        count_buy=sum(buy_votes.values());count_sell=sum(sell_votes.values())
        if cfg["mode"]=="Breakout + Retest":
            if break_up:pending={"side":"BUY","index":i,"level":hi,"votes":count_buy}
            if break_dn:pending={"side":"SELL","index":i,"level":lo,"votes":count_sell}
        expired=bool(pending and i-pending["index"]>cfg["retest_bars"])
        if expired:pending=None
        retest_buy=bool(pending and pending["side"]=="BUY" and i>pending["index"] and atr is not None and l<=pending["level"]+atr*.2 and c>pending["level"] and c>o)
        retest_sell=bool(pending and pending["side"]=="SELL" and i>pending["index"] and atr is not None and h>=pending["level"]-atr*.2 and c<pending["level"] and c<o)
        evidence_buy=count_buy+(pending["votes"] if pending and pending["side"]=="BUY" and i>pending["index"] else 0)
        evidence_sell=count_sell+(pending["votes"] if pending and pending["side"]=="SELL" and i>pending["index"] else 0)
        if active is not None and i>active["entry_index"]:
            buy=active["side"]=="BUY"
            hit_stop=l<=active["sl"] if buy else h>=active["sl"]
            hit_target=h>=active["tp"] if buy else l<=active["tp"]
            if hit_stop or hit_target:
                outcome="ambiguous_both" if hit_stop and hit_target else "sl" if hit_stop else "tp"
                gross=None if outcome=="ambiguous_both" else -1 if outcome=="sl" else cfg["rr"]
                cost=(costs["spread_price"]+2*costs["slippage_price_per_side"]+costs["commission_price_round_trip"])/abs(active["entry"]-active["sl"]) if costs else None
                active.update(outcome=outcome,exit_time=(datetime.fromisoformat(r["time"])+timedelta(minutes=5)).isoformat(),exit_index=i,gross_r=gross,cost_r=cost,net_r=gross-cost if gross is not None and cost is not None else None)
                active=None
        ready=active is None and (last_entry is None or i-last_entry>cfg["cooldown"])
        b15,b60,b240=[biases[str(m)][i] for m in (15,60,240)]
        htf_buy=cfg["htf_mode"]=="Off" or ((b15==b60==b240==1) if cfg["htf_mode"]=="Strict" else b15==1 and b60 is not None and b60!=-1)
        htf_sell=cfg["htf_mode"]=="Off" or ((b15==b60==b240==-1) if cfg["htf_mode"]=="Strict" else b15==-1 and b60 is not None and b60!=1)
        base=atrs[max(0,i-cfg["atr_floor_len"]+1):i+1]
        baseline=sum(base)/len(base) if len(base)==cfg["atr_floor_len"] and all(x is not None for x in base) else None
        volatility=not cfg["use_atr_floor"] or (atr is not None and baseline is not None and atr>=baseline*cfg["atr_floor_factor"])
        stop_buy=min(lows[max(0,i-cfg["swing"]+1):i+1])-atr*.2 if atr is not None else None
        stop_sell=max(highs[max(0,i-cfg["swing"]+1):i+1])+atr*.2 if atr is not None else None
        trigger_buy=break_up if cfg["mode"]=="Confirmed breakout" else retest_buy
        trigger_sell=break_dn if cfg["mode"]=="Confirmed breakout" else retest_sell
        decisions={}
        for side,trigger,htf,ha,stop,votes,details in (
            ("BUY",trigger_buy,htf_buy,ha_close>ha_open,stop_buy,evidence_buy,buy_votes),
            ("SELL",trigger_sell,htf_sell,ha_close<ha_open,stop_sell,evidence_sell,sell_votes)):
            risk=abs(c-stop) if stop is not None else None
            checks={"atr_ready":atr is not None,"no_open_trade":active is None,
                "cooldown":last_entry is None or i-last_entry>cfg["cooldown"],
                "trigger":trigger,"htf":htf,"heikin_ashi":not cfg["use_ha"] or ha,
                "volatility":volatility,"risk_distance":risk is not None and risk>tick_size and risk<=atr*cfg["max_risk_atr"],
                "direction":cfg["side"]!=("Sell" if side=="BUY" else "Buy"),
                "evidence":not cfg["use_hybrid"] or votes>=cfg["min_evidence"]}
            failed=[key for key,value in checks.items() if not value]
            decisions[side]={"accepted":not failed,"rejections":failed,"votes":votes,"evidence":details}
            rejections.update(side+":"+key for key in failed)
        chosen="BUY" if decisions["BUY"]["accepted"] else "SELL" if decisions["SELL"]["accepted"] else None
        diagnostics.append({"bar_index":i,"time":r["time"],"atr":atr,"break_up":break_up,"break_down":break_dn,
            "pending_expired":expired,"pending":dict(pending) if pending else None,
            "htf":{"m15":b15,"h1":b60,"h4":b240},"decisions":decisions})
        if chosen:
            stop=stop_buy if chosen=="BUY" else stop_sell
            sign=1 if chosen=="BUY" else -1
            if not math.isfinite(c+sign*abs(c-stop)*cfg["rr"]):raise ValueError("nonfinite target calculation")
            active={"side":chosen,"entry_index":i,"time":(datetime.fromisoformat(r["time"])+timedelta(minutes=5)).isoformat(),
                "entry":c,"sl":stop,"tp":c+sign*abs(c-stop)*cfg["rr"],"rr":cfg["rr"],
                "evidence":evidence_buy if chosen=="BUY" else evidence_sell,
                "outcome":"unresolved","exit_time":None,"gross_r":None,"net_r":None,"cost_r":None}
            trades.append(active);last_entry=i;pending=None
    return {"engine":"v6.4.1_rules_translation","engine_sha256":ENGINE_SHA256,
        "pine_parity_verified":False,"promotion_allowed":False,"parameters":cfg,
        "tick_size":tick_size,"cost_assumptions":costs,"quality":quality,
        "htf_alignment":{"timezone":"UTC","anchor_minutes":htf_anchor_minutes,"exchange_verified":False},
        "trades":trades,"metrics":metrics(trades),"diagnostics":diagnostics,
        "rejection_counts":dict(rejections),
        "limitations":["Not validated against same-feed TradingView bar-by-bar exports",
            "UTC HTF boundaries, initial EMA/RMA history and equal-pivot ties require parity verification",
            "Source does not model broker fills or intrabar SL/TP order; both-hit bars remain ambiguous",
            "Net metrics require explicit price-equivalent spread/slippage/commission assumptions",
            "No exchange calendar, continuous-contract roll adjustment or independent video-baseline verification"]}


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS pine_replay_runs (id TEXT PRIMARY KEY,symbol TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)")


def save(connection,report,postgres=False):
    marker="%s" if postgres else "?"
    return bool(connection.execute("INSERT INTO pine_replay_runs(id,symbol,created_at,payload) VALUES ("+",".join([marker]*4)+") ON CONFLICT(id) DO NOTHING",
        (report["run_id"],report["symbol"],report["created_at"],json.dumps(report))).rowcount)


def latest(connection,run_id=None,postgres=False):
    if run_id is not None:
        if len(run_id)!=64 or any(c not in "0123456789abcdef" for c in run_id):raise ValueError("run_id")
        row=connection.execute("SELECT payload FROM pine_replay_runs WHERE id="+("%s" if postgres else "?"),(run_id,)).fetchone()
        return json.loads(row[0]) if row else None
    rows=connection.execute("SELECT payload FROM pine_replay_runs ORDER BY created_at DESC LIMIT 3").fetchall()
    reports=[json.loads(row[0]) for row in rows]
    return {"runs":[{key:value for key,value in report.items() if key not in ("diagnostics","trades")} for report in reports],
        "count":len(reports),"pine_parity_verified":False,"promotion_allowed":False}
