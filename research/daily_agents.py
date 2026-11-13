"""Offline, read-only research agents. CSV: time,open,high,low,close (ascending UTC). No execution."""
import csv,json,sys,statistics
from pathlib import Path

def load(path):
 rows=[]
 with open(path,newline="",encoding="utf-8") as f:
  for r in csv.DictReader(f):
   try:
    d={k:float(r[k]) for k in ("open","high","low","close")}
    if min(d.values())<=0 or d["high"]<max(d["open"],d["close"],d["low"]) or d["low"]>min(d["open"],d["close"]):continue
    d["time"]=r["time"];rows.append(d)
   except (KeyError,ValueError,TypeError):continue
 return rows

def signal(rows,i,lookback=20,rr=3):
 """Research-only breakout baseline, NOT exact TradingView v6.4 parity."""
 r=rows[i];prior=rows[i-lookback:i]
 hi=max(x["high"] for x in prior);lo=min(x["low"] for x in prior)
 if r["close"]>hi and r["close"]>r["open"]:side="BUY";sl=min(x["low"] for x in rows[i-8:i+1])
 elif r["close"]<lo and r["close"]<r["open"]:side="SELL";sl=max(x["high"] for x in rows[i-8:i+1])
 else:return None
 entry=r["close"];risk=abs(entry-sl)
 if risk<=0:return None
 return {"time":r["time"],"side":side,"entry":entry,"sl":sl,"tp":entry+(risk*rr if side=="BUY" else -risk*rr)}

def backtest(rows,lookback=20,rr=3,hold=48):
 trades=[];next_i=lookback
 for i in range(lookback,len(rows)-1):
  if i<next_i:continue
  s=signal(rows,i,lookback,rr)
  if not s:continue
  outcome="unresolved";end=min(i+hold,len(rows)-1)
  for j in range(i+1,end+1):
   b=rows[j];buy=s["side"]=="BUY"
   hit_sl=b["low"]<=s["sl"] if buy else b["high"]>=s["sl"]
   hit_tp=b["high"]>=s["tp"] if buy else b["low"]<=s["tp"]
   if hit_sl and hit_tp:outcome="ambiguous_both";end=j;break
   if hit_sl:outcome="sl";end=j;break
   if hit_tp:outcome="tp";end=j;break
  s["outcome"]=outcome;trades.append(s);next_i=end+1
 return trades

def agent_quality(trades):
 resolved=[t for t in trades if t["outcome"] in ("tp","sl")]
 return {"agent":"quality","total":len(trades),"resolved":len(resolved),"tp":sum(t["outcome"]=="tp" for t in resolved),"sl":sum(t["outcome"]=="sl" for t in resolved),"ambiguous":sum(t["outcome"]=="ambiguous_both" for t in trades),"unresolved":sum(t["outcome"]=="unresolved" for t in trades),"win_rate":round(sum(t["outcome"]=="tp" for t in resolved)/len(resolved),4) if resolved else None}
def agent_risk(trades):
 return {"agent":"risk","notes":["No fills, spreads, commissions or slippage modeled","Same-bar SL and TP is ambiguous; never count as a win","Non-overlapping trades; stop/target only from later candles"],"ambiguous_count":sum(t["outcome"]=="ambiguous_both" for t in trades)}
def agent_validation(rows):
 split=int(len(rows)*0.7)
 if split<100 or len(rows)-split<50:return {"agent":"validation","status":"insufficient_data"}
 train=backtest(rows[:split]);test=backtest(rows[split:])
 return {"agent":"validation","status":"research_only","train":agent_quality(train),"out_of_sample":agent_quality(test),"warning":"A historical holdout is not a forward test"}
def agent_reviewer(report):
 q=report["quality"];v=report["validation"]
 reasons=[]
 if q["resolved"]<30:reasons.append("Fewer than 30 resolved trades")
 if q["ambiguous"]:reasons.append("Ambiguous same-bar outcomes")
 if v["status"]!="research_only" or v["out_of_sample"]["resolved"]<30:reasons.append("Insufficient out-of-sample trades")
 return {"agent":"reviewer","decision":"REJECT_AUTOMATIC_DEPLOY","reasons":reasons or ["Manual review, Pine parity, fees and walk-forward validation required"],"updates_allowed":"proposal_only"}

def run(path):
 rows=load(path)
 if len(rows)<120:raise ValueError("At least 120 valid historical OHLC candles required")
 trades=backtest(rows)
 report={"source_file":Path(path).name,"candles":len(rows),"engine":"research_breakout_proxy_not_pine_v6_4","quality":agent_quality(trades),"risk":agent_risk(trades),"validation":agent_validation(rows)}
 report["reviewer"]=agent_reviewer(report)
 return report
if __name__=="__main__":
 if len(sys.argv)!=2:raise SystemExit("Usage: python research/daily_agents.py path/to/ohlc.csv")
 print(json.dumps(run(sys.argv[1]),ensure_ascii=False,indent=2))
