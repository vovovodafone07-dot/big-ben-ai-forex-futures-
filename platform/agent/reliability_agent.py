"""Read-only Big Ben reliability agent. Never trades or modifies production."""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone
BASE=os.getenv("BIGBEN_BASE_URL","https://bigben-ai-pro-api.onrender.com").rstrip("/")
def fetch(path,auth=None):
 req=urllib.request.Request(BASE+path,headers={"Accept":"application/json","User-Agent":"BigBenReliabilityAgent/1.0",**({"Authorization":auth} if auth else {})})
 with urllib.request.urlopen(req,timeout=25) as r:return r.status,json.load(r)
def main():
 errors=[];warnings=[];report={"checked_at":datetime.now(timezone.utc).isoformat(),"service":BASE}
 for name,path in [("health","/healthz"),("integrations","/healthz/integrations"),("storage","/healthz/storage")]:
  try:
   status,data=fetch(path);report[name]=data
   if status!=200 or data.get("status")!="ok":errors.append(name+" unhealthy")
  except (urllib.error.URLError,ValueError,TimeoutError) as e:errors.append(name+" unreachable: "+type(e).__name__)
 integ=report.get("integrations",{})
 if integ:
  for k,v in [("TradingView webhook",integ.get("tradingview",{}).get("webhook_token_configured")),("Telegram bot",integ.get("telegram",{}).get("bot_token_configured")),("Telegram chat",integ.get("telegram",{}).get("chat_id_configured"))]:
   if not v:warnings.append(k+" not configured")
  if integ.get("database",{}).get("storage")=="ephemeral":warnings.append("Ephemeral database: event history may be lost after restart")
 user=os.getenv("BIGBEN_DASHBOARD_USER","bigben");password=os.getenv("BIGBEN_DASHBOARD_PASSWORD","")
 if password:
  import base64
  auth="Basic "+base64.b64encode((user+":"+password).encode()).decode()
  try:
   _,d=fetch("/api/diagnostics",auth);report["diagnostics"]=d
   hb=d.get("last_heartbeat")
   if not hb:warnings.append("No heartbeat recorded")
   elif not hb.get("fresh"):warnings.append("Last heartbeat stale: "+str(hb.get("time")))
   if not d.get("market_provider_configured"):warnings.append("Twelve Data key not configured")
   # Verify the dashboard's connected agent and research APIs too.
   for name,path in [("agent","/api/agent"),("research","/api/research"),("outcomes","/api/outcomes")]:
    try:
     status,payload=fetch(path,auth)
     report[name]={"status":status,"available":True}
     if status!=200:errors.append(name+" HTTP "+str(status))
     if name=="agent":
      report[name]["mode"]=payload.get("mode")
      report[name]["tracked_symbols"]=len(payload.get("tracked_symbols",[]))
      if payload.get("mode")!="read_only":errors.append("agent mode unexpected")
     if name=="research":report[name]["signals_examined"]=payload.get("signals_examined")
     if name=="outcomes":report[name]["count"]=payload.get("count")
    except (urllib.error.URLError,ValueError,TimeoutError) as e:
     errors.append(name+" API unavailable: "+type(e).__name__)
  except (urllib.error.URLError,ValueError,TimeoutError) as e:warnings.append("Authenticated diagnostics unavailable: "+type(e).__name__)
 else:warnings.append("GitHub Actions secret BIGBEN_DASHBOARD_PASSWORD is missing; add it under repository Settings > Secrets and variables > Actions to enable private freshness checks")
 report["errors"]=errors;report["warnings"]=warnings
 print(json.dumps(report,ensure_ascii=False,indent=2))
 if errors:sys.exit(1)
if __name__=="__main__":main()
