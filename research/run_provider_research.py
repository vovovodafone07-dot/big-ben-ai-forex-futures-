"""Daily licensed-history check and four deterministic research reviewers."""
import json,os,sys,datetime
from pathlib import Path
from barchart_adapter import get_m5,load_requested_symbols,ProviderError
from daily_agents import backtest,agent_quality,agent_risk,agent_validation,agent_reviewer

def generate():
 report={"created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"provider":"Barchart OnDemand","mode":"read_only_research_proxy","status":"awaiting_data_access","symbols":{},"limitations":["Not the exact TradingView Pine v6.4 algorithm","No real fills, commissions, slippage, tick-sequenced TP/SL or strategy auto-updates"]}
 key=os.getenv("BARCHART_API_KEY","").strip()
 try: mapping=load_requested_symbols()
 except ValueError as e:
  report["status"]="invalid_symbol_mapping";report["message"]=str(e);return report
 if not key:
  report["message"]="BARCHART_API_KEY not configured in GitHub Actions secrets; no licensed market data fetched"
  return report
 if not mapping:
  report["message"]="BIGBEN_BARCHART_SYMBOL_MAP not configured; do not guess provider futures symbols"
  return report
 report["status"]="complete";failures=0;success=0
 for label,symbol in mapping.items():
  try:
   candles=get_m5(symbol,key)
   trades=backtest(candles)
   r={"provider_symbol":symbol,"candles":len(candles),"quality":agent_quality(trades),"risk":agent_risk(trades),"validation":agent_validation(candles)}
   r["reviewer"]=agent_reviewer(r)
   r["status"]="research_complete";report["symbols"][label]=r;success+=1
  except (ProviderError,ValueError,KeyError,TypeError) as e:
   report["symbols"][label]={"provider_symbol":symbol,"status":"data_error","error":str(e)[:200]}
   failures+=1
 report["status"]="partial_data_error" if failures and success else "data_unavailable" if failures else "complete"
 report["coverage"]={"requested":len(mapping),"successful":success,"failed":failures}
 return report
if __name__=="__main__":
 output=generate()
 path=Path(os.getenv("BIGBEN_RESEARCH_REPORT","research/reports/latest.json"))
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding="utf-8")
 print("research_status="+output["status"]+" validated_symbols="+str(output.get("coverage",{}).get("successful",0)))
