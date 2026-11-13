"""Big Ben AI Pro: read-only webhook receiver. No broker/order endpoints."""
import os,json,hmac,math,re,sqlite3,time,base64,urllib.request,urllib.error
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
DB=Path(os.getenv("BIGBEN_DB_PATH","/tmp/bigben-dev.sqlite3"))
LAST_TEST_SENT=0
# Load the sibling migration module also when imported through a test spec.
import importlib.util
_mspec=importlib.util.spec_from_file_location("bigben_migrations",Path(__file__).with_name("migrations.py"))
_migrations=importlib.util.module_from_spec(_mspec)
_mspec.loader.exec_module(_migrations)
_aspec=importlib.util.spec_from_file_location("bigben_analysis",Path(__file__).with_name("analysis.py"))
_analysis=importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(_analysis)
_sspec=importlib.util.spec_from_file_location("bigben_scalping",Path(__file__).with_name("scalping.py"))
_scalping=importlib.util.module_from_spec(_sspec)
_sspec.loader.exec_module(_scalping)

def secure_equal(supplied, expected):
 return isinstance(supplied,str) and hmac.compare_digest(supplied.encode("utf-8"),expected.encode("utf-8"))
def twelve_data_key():
 # Both spellings already appear in the legacy and Pro services.
 return os.getenv("TWELVE_DATA_API_KEY","").strip() or os.getenv("TWELVEDATA_API_KEY","").strip()

def postgres_enabled():
 return bool(os.getenv("DATABASE_URL", "").strip())
def storage_kind():
 return "postgres" if postgres_enabled() else "ephemeral"
def pg_connect():
 # psycopg is installed at build time from platform/backend/requirements.txt.
 # Never attempt a pip installation while processing a TradingView webhook.
 import psycopg
 return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3)
@contextmanager
def sqlite_connection():
 # sqlite3 context managers commit/rollback but do not close the handle.
 connection=sqlite3.connect(DB)
 try:
  with connection:
   yield connection
 finally:
  connection.close()

def init():
 if postgres_enabled():
  with pg_connect() as c:
   c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, symbol TEXT NOT NULL, event TEXT NOT NULL, time TEXT NOT NULL, payload TEXT NOT NULL)")
   _migrations.migrate_events(c,postgres=True)
 else:
  DB.parent.mkdir(parents=True,exist_ok=True)
  with sqlite_connection() as c:
   c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,symbol TEXT,event TEXT,time TEXT,payload TEXT)")
   _migrations.migrate_events(c)
def list_events(limit=500, kind="all"):
 if postgres_enabled():
  with pg_connect() as c:
   return c.execute("SELECT symbol,event,time,payload FROM events WHERE (%s = 'all' OR (%s = 'trades' AND event IN ('BUY','SELL')) OR (%s = 'heartbeat' AND event = 'HEARTBEAT')) ORDER BY time DESC LIMIT %s",(kind,kind,kind,limit)).fetchall()
 with sqlite_connection() as c:
  return c.execute("SELECT symbol,event,time,payload FROM events WHERE (? = 'all' OR (? = 'trades' AND event IN ('BUY','SELL')) OR (? = 'heartbeat' AND event = 'HEARTBEAT')) ORDER BY time DESC LIMIT ?",(kind,kind,kind,limit)).fetchall()
def save_event(d):
 received_at=datetime.now(timezone.utc).isoformat()
 stored={**d,"received_at":received_at}
 vals=(d["event_id"],d["symbol"],d["event"],d["time"],json.dumps(stored),received_at)
 if postgres_enabled():
  with pg_connect() as c:
   return c.execute("INSERT INTO events (id,symbol,event,time,payload,received_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",vals).rowcount==0
 with sqlite_connection() as c:
  return c.execute("INSERT OR IGNORE INTO events (id,symbol,event,time,payload,received_at) VALUES (?,?,?,?,?,?)",vals).rowcount==0
def evaluate_signals(limit=100):
 # Observational outcomes only: a M5 close beyond SL/TP is NOT proof of an
 # actual fill or the first intrabar level touched. Never backfill fake trades.
 rows=list_events(2000,"all")
 parsed=[]
 for symbol,event,t,payload in rows:
  try:
   d=json.loads(payload)
   stamp=datetime.fromisoformat(t.replace("Z","+00:00"))
   parsed.append((stamp,symbol,event,d))
  except (ValueError,TypeError,KeyError,AttributeError):continue
 parsed.sort(key=lambda x:x[0])
 signals=[]
 for i,(t,symbol,event,d) in enumerate(parsed):
  if event not in ("BUY","SELL"):continue
  try:entry,sl,tp=[float(d[k]) for k in ("entry","sl","tp")]
  except (ValueError,TypeError,KeyError):continue
  if not all(math.isfinite(v) and v>0 for v in (entry,sl,tp)):continue
  if not (sl<entry<tp if event=="BUY" else tp<entry<sl):continue
  result="unresolved";at=None;observations=0
  for ht,hs,he,hd in parsed[i+1:]:
   if hs!=symbol or he!="HEARTBEAT":continue
   try:close=float(hd["close"])
   except (ValueError,TypeError,KeyError):continue
   if not math.isfinite(close) or close<=0:continue
   observations+=1
   if (close>=tp if event=="BUY" else close<=tp):result="tp_close_observed"
   elif (close<=sl if event=="BUY" else close>=sl):result="sl_close_observed"
   else:continue
   at=ht.isoformat();break
  signals.append({"symbol":symbol,"event":event,"time":t.isoformat(),"entry":entry,"sl":sl,"tp":tp,"outcome":result,"observed_at":at,"m5_closes_checked":observations})
 signals=signals[-limit:][::-1]
 return {"signals":signals,"count":len(signals),"tp_close_observed":sum(s["outcome"]=="tp_close_observed" for s in signals),"sl_close_observed":sum(s["outcome"]=="sl_close_observed" for s in signals),"unresolved":sum(s["outcome"]=="unresolved" for s in signals),"method":"M5 close observations only; not broker fills, intrabar first-touch, or verified trade performance","source":"TradingView webhook event history"}
def research_report():
 """Read-only evidence audit; no model training, strategy mutation or trade execution."""
 data=evaluate_signals(limit=100)
 rows=data["signals"]
 observed=[s for s in rows if s["outcome"] in ("tp_close_observed","sl_close_observed")]
 groups={}
 for s in rows:
  g=groups.setdefault(s["symbol"],{"signals":0,"tp_close_observed":0,"sl_close_observed":0,"unresolved":0})
  g["signals"]+=1;g[s["outcome"]]+=1
 return {"status":"insufficient_evidence" if len(observed)<30 else "descriptive_only",
         "minimum_observed_outcomes_for_review":30,
         "observed_outcomes":len(observed),"signals_examined":len(rows),
         "by_symbol":groups,
         "cautions":["M5 closing prices do not prove fills or intrabar SL/TP order",
                     "Only the most recent 2000 stored events are sampled",
                     "Missing heartbeat data can bias outcomes",
                     "No automatic strategy changes or claims of profitability"],
         "next_step":"Collect continuous M5 data, validate first-touch on OHLC history and evaluate out-of-sample before proposing parameter changes"}
def learning_audit():
 """Evidence-based learning audit; suggestions require review, never auto-edit Pine."""
 rows=list_events(2000,"all")
 trades=[];heartbeat_by_symbol={}
 for symbol,event,t,payload in rows:
  try:
   d=json.loads(payload)
   stamp=datetime.fromisoformat(t.replace("Z","+00:00"))
  except (ValueError,TypeError,AttributeError,KeyError):continue
  if event=="HEARTBEAT":
   heartbeat_by_symbol.setdefault(symbol,[]).append((stamp,d))
  elif event in ("BUY","SELL"):
   trades.append((stamp,symbol,event,d))
 for items in heartbeat_by_symbol.values():items.sort(key=lambda x:x[0])
 outcomes={"tp_close_observed":0,"sl_close_observed":0,"unresolved":0}
 groups={}
 examples=[]
 for stamp,symbol,side,d in trades:
  try:
   entry,sl,tp=[float(d[k]) for k in ("entry","sl","tp")]
   if not all(math.isfinite(x) and x>0 for x in (entry,sl,tp)):continue
   if not (sl<entry<tp if side=="BUY" else tp<entry<sl):continue
  except (KeyError,ValueError,TypeError):continue
  bias=d.get("htf_bias")
  label=str(bias)[:60] if bias is not None else "unknown"
  key=symbol+" | "+side+" | "+label
  g=groups.setdefault(key,{"symbol":symbol,"side":side,"htf_bias":label,"signals":0,"tp_close_observed":0,"sl_close_observed":0,"unresolved":0})
  g["signals"]+=1
  outcome="unresolved";observed=0
  for ht,hb in heartbeat_by_symbol.get(symbol,[]):
   if ht<=stamp:continue
   try:close=float(hb["close"])
   except (KeyError,ValueError,TypeError):continue
   if not math.isfinite(close) or close<=0:continue
   observed+=1
   if (close>=tp if side=="BUY" else close<=tp):outcome="tp_close_observed";break
   if (close<=sl if side=="BUY" else close>=sl):outcome="sl_close_observed";break
  outcomes[outcome]+=1;g[outcome]+=1
  if outcome=="sl_close_observed" and len(examples)<12:
   examples.append({"symbol":symbol,"side":side,"time":stamp.isoformat(),"htf_bias":label,"m5_closes_checked":observed,"observation":"M5 close beyond stop; not proof of an executed loss"})
 suggestions=[]
 for g in groups.values():
  resolved=g["tp_close_observed"]+g["sl_close_observed"]
  if resolved>=30 and g["sl_close_observed"]>g["tp_close_observed"]:
   suggestions.append({"scope":g["symbol"]+" "+g["side"],"hypothesis":"Review higher-timeframe agreement and entry filters in this segment","evidence_count":resolved,"action":"backtest_only","requires_out_of_sample_validation":True})
 return {"mode":"read_only_learning_audit","signals_reviewed":sum(outcomes.values()),"observations":outcomes,
         "segments":list(groups.values()),"error_examples":examples,"hypotheses":suggestions,
         "minimum_resolved_observations_per_segment":30,
         "learning_status":"hypotheses_available" if suggestions else "collect_more_evidence",
         "limitations":["M5 close observations cannot establish intrabar first-touch, fills, or actual PnL","Missing heartbeat data biases results","No autonomous strategy edits, deployments, or trading","Hypotheses are not proven improvements"],
         "next_step":"Collect continuous M5 OHLC and signal metadata; validate any proposed filter on out-of-sample data before a separate Pine candidate is reviewed"}
def validate(d):
 if not isinstance(d,dict) or d.get("schema")!="bigben.v1":raise ValueError("schema")
 if d.get("event") not in ("BUY","SELL","TP_HIT","SL_HIT","HEARTBEAT"):raise ValueError("event")
 if not isinstance(d.get("symbol"),str) or not re.fullmatch(r"[A-Za-z0-9:_!./-]{1,60}",d["symbol"]) or ".." in d["symbol"] or d["symbol"].startswith(("/", ".")):raise ValueError("symbol")
 if not isinstance(d.get("event_id"),str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,120}",d["event_id"]):raise ValueError("event_id")
 try:
  t=datetime.fromisoformat(d["time"].replace("Z","+00:00"))
  if t.tzinfo is None or abs(t.timestamp()-time.time())>600:raise ValueError()
 except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError):raise ValueError("time")
 if d["event"] in ("BUY","SELL"):
  try:entry,sl,tp,rr=[d[k] for k in ("entry","sl","tp","rr")]
  except KeyError:raise ValueError("levels")
  if any(type(n) not in (int,float) or not math.isfinite(n) or n<=0 for n in (entry,sl,tp,rr)):raise ValueError("levels")
  if not ((sl<entry<tp) if d["event"]=="BUY" else (tp<entry<sl)):raise ValueError("direction")
  if not math.isclose(abs(tp-entry)/abs(entry-sl),rr,rel_tol=.03,abs_tol=.03):raise ValueError("rr")
 if d["event"]=="HEARTBEAT" and "close" in d:
  price=d["close"]
  if type(price) not in (int,float) or not math.isfinite(price) or price<=0:raise ValueError("close")
  for tf in ("m15","h1","h4"):
   if tf in d and (type(d[tf]) not in (int,float) or d[tf] not in (-1,0,1)):raise ValueError("bias")
 return d
def trade_notification_text(d):
 pair=_scalping.levels(d)
 full,scalp=pair["full_trade"],pair["scalp"]
 return ("📊 Big Ben AI Pro\n"+str(d["event"])+" | "+str(d["symbol"])
  +"\n\nالصفقة الكاملة — الهدف الأصلي"
  +"\nEntry: "+str(full["entry"])+" | SL: "+str(full["sl"])
  +"\nTP: "+str(full["tp"])+" | RR: "+str(round(full["rr"],4))
  +"\n\nخيار السكالب — هدف حسابي بديل"
  +"\nEntry: "+str(scalp["entry"])+" | SL: "+str(scalp["sl"])
  +"\nTP: "+str(scalp["tp"])+" | RR: "+str(round(scalp["rr"],4))
  +"\nليس إشارة مستقلة؛ التكاليف وحجم التيك غير مؤكدين."
  +"\nاختر أحد الخيارين؛ فتحهما معًا يضاعف التعرض."
  +"\nتحليل فقط — لا يوجد تنفيذ أوامر.")

def telegram_notify(d):
 # Explicit chat allowlist avoids accidentally sending private trade data to strangers.
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):
  return "not_configured"
 if d.get("event") not in ("BUY","SELL"):
  return "skipped"
 message=trade_notification_text(d)
 payload=json.dumps({"chat_id":chat,"text":message}).encode()
 req=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=payload,headers={"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=6) as response:
   return "sent" if response.status==200 else "failed"
 except (urllib.error.URLError,TimeoutError,ValueError):
  return "failed"
def send_telegram_message(message):
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):
  return "not_configured"
 payload=json.dumps({"chat_id":chat,"text":message}).encode()
 req=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=payload,headers={"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=8) as response:
   return "sent" if response.status==200 else "failed"
 except (urllib.error.URLError,TimeoutError,ValueError):
  return "failed"
def dashboard_authenticated(headers):
 password=os.getenv("BIGBEN_DASHBOARD_PASSWORD","")
 if len(password)<20:return False
 expected="Basic "+base64.b64encode(("bigben:"+password).encode()).decode()
 return secure_equal(headers.get("Authorization",""),expected)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,obj):
  if urlsplit(self.path).path=="/v1/tradingview/events":
   print("webhook_result status="+str(status)+" reason="+str(obj.get("error","accepted"))+" duplicate="+str(obj.get("duplicate",False)),flush=True)
  b=json.dumps(obj).encode();self.send_response(status)
  for k,v in {"Content-Type":"application/json","Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'none'","Content-Length":str(len(b))}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=="/healthz":return self.reply(200,{"status":"ok","mode":"read-only"})
  if path=="/healthz/integrations":
   token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
   chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
   return self.reply(200,{"status":"ok","telegram":{"bot_token_configured":bool(token),"chat_id_configured":bool(re.fullmatch(r"-?[0-9]{5,20}",chat))},"tradingview":{"webhook_token_configured":len(os.getenv("BIGBEN_WEBHOOK_TOKEN",""))>=32},"database":{"storage":storage_kind()},"market_data":{"twelve_data_key_configured":bool(twelve_data_key()),"credentials_only":True}})
  if path=="/healthz/storage":
   try:
    init()
    if postgres_enabled():
     # Exercise INSERT and SELECT inside a transaction, then roll back:
     # confirms DB write permissions without leaving fake trading signals.
     with pg_connect() as c:
      c.execute("INSERT INTO events (id,symbol,event,time,payload) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", ("__bigben_health_probe__","HEALTH","HEARTBEAT","probe","{}"))
      c.execute("SELECT id FROM events WHERE id=%s", ("__bigben_health_probe__",)).fetchone()
      c.rollback()
    else:
     with sqlite_connection() as c:c.execute("SELECT 1").fetchone()
   except Exception:
    return self.reply(503,{"status":"unavailable","storage":storage_kind()})
   return self.reply(200,{"status":"ok","storage":storage_kind()})
  if path not in ("/","/dashboard","/api/events","/api/status","/api/diagnostics","/api/market","/api/outcomes","/api/research","/api/agent","/api/learning","/api/data-sources","/api/pine/current","/api/analysis","/api/scalping"):return self.reply(404,{"error":"not_found"})
  password=os.getenv("BIGBEN_DASHBOARD_PASSWORD","")
  if len(password)<20:return self.reply(503,{"error":"dashboard_not_configured"})
  supplied=self.headers.get("Authorization","")
  expected="Basic "+base64.b64encode(("bigben:"+password).encode()).decode()
  if not secure_equal(supplied,expected):
   self.send_response(401)
   self.send_header("WWW-Authenticate",'Basic realm="Big Ben Private Preview"')
   self.send_header("Cache-Control","no-store")
   self.send_header("Content-Length","0")
   self.end_headers()
   return
  if path=="/api/scalping":
   try:
    rr=parse_qs(urlsplit(self.path).query).get("rr",["1"])[0]
    return self.reply(200,_scalping.scenarios(list_events(2000,"all"),rr))
   except ValueError:return self.reply(400,{"error":"invalid_rr","range":"0.5..3"})
   except Exception:return self.reply(503,{"error":"scalping_unavailable"})
  if path=="/api/analysis":
   try:return self.reply(200,_analysis.analyze_events(list_events(2000,"heartbeat")))
   except Exception:return self.reply(503,{"error":"analysis_unavailable"})
  if path=="/api/pine/current":
   # Protected source preview of the versioned candidate. Edits are local draft only.
   pine_file=Path(__file__).resolve().parents[2]/"tradingview"/"Big_Ben_AI_Hybrid_M5_v6_4_Review.pine"
   if not pine_file.is_file():return self.reply(404,{"error":"source_unavailable"})
   return self.reply(200,{"version":"v6.4_review","code":pine_file.read_text(encoding="utf-8"),
      "mode":"read_only_versioned_candidate","changes_to_live_tradingview":False})
  if path=="/api/data-sources":
   # Configuration/readiness only. Never report entitlement or real-time support without a licensed probe.
   barchart_key=bool(os.getenv("BARCHART_API_KEY","").strip())
   mapping_configured=bool(os.getenv("BIGBEN_BARCHART_SYMBOL_MAP","").strip())
   twelve_key=bool(twelve_data_key())
   return self.reply(200,{"status":"configuration_only","preferred_provider":"Barchart OnDemand",
     "barchart":{"api_key_configured":barchart_key,"symbol_mapping_configured":mapping_configured,
                  "licensed_symbol_coverage":"unverified","live_and_historical_entitlements":"unverified",
                  "research_ready":barchart_key and mapping_configured},
     "twelve_data":{"api_key_configured":twelve_key,"role":"existing_quotes_optional",
                    "futures_coverage":"not_confirmed"},
     "data_policy":"Never use unsupported futures quotes, stale candles, or fabricated backtests"})
  if path=="/api/market":
   # Twelve Data is optional. Never label delayed or missing quotes as live.
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   q=parse_qs(urlsplit(self.path).query)
   symbol=q.get("symbol",["EUR/USD"])[0].strip().upper()
   if not re.fullmatch(r"[A-Z0-9:/._-]{2,32}",symbol):return self.reply(400,{"error":"symbol"})
   key=twelve_data_key()
   if not key:return self.reply(503,{"error":"market_provider_not_configured","provider":"Twelve Data"})
   from urllib.parse import urlencode
   url="https://api.twelvedata.com/price?"+urlencode({"symbol":symbol,"apikey":key})
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"BigBenAIPro/1.0"}),timeout=8) as resp:
     result=json.loads(resp.read(16384))
    if not isinstance(result,dict) or "price" not in result:return self.reply(502,{"error":"market_provider_unavailable","provider":"Twelve Data","symbol":symbol})
    price=float(result["price"])
    if not math.isfinite(price) or price<=0:raise ValueError()
    return self.reply(200,{"symbol":symbol,"price":price,"provider":"Twelve Data","fetched_at":datetime.now(timezone.utc).isoformat(),"quote_timestamp":None,"realtime_verified":False,"note":"Provider price fetched now; exchange quote time and real-time entitlement not verified."})
   except (urllib.error.URLError,TimeoutError,ValueError,TypeError,KeyError,OverflowError):
    return self.reply(502,{"error":"market_provider_unavailable","provider":"Twelve Data","symbol":symbol})
  if path=="/api/diagnostics":
   try:
    rows=list_events(500)
    now=datetime.now(timezone.utc)
    def recent(event_names):
     for symbol,event,t,payload in rows:
      if event in event_names:
       try:
        dt=datetime.fromisoformat(t.replace("Z","+00:00"))
        age=max(0,int((now-dt).total_seconds()))
        return {"symbol":symbol,"time":t,"age_seconds":age,"fresh":age<720}
       except (ValueError,TypeError,AttributeError):pass
     return None
    return self.reply(200,{"status":"ok","storage":storage_kind(),"webhook_token_configured":len(os.getenv("BIGBEN_WEBHOOK_TOKEN",""))>=32,"market_provider_configured":bool(twelve_data_key()),"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and re.fullmatch(r"-?[0-9]{5,20}",os.getenv("TELEGRAM_CHAT_ID",""))),"last_heartbeat":recent(("HEARTBEAT",)),"last_trade":recent(("BUY","SELL")),"last_event":recent(("BUY","SELL","HEARTBEAT")),"note":"No synthetic trades; fresh means received within 12 minutes, not a guarantee of TradingView market availability."})
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if path=="/api/agent":
   # Operational agent panel: actual observed states, not simulated AI decisions.
   try:
    rows=list_events(500)
    now=datetime.now(timezone.utc)
    latest={}
    for symbol,event,t,payload in rows:
     if symbol in latest or event!="HEARTBEAT":continue
     try:
      stamp=datetime.fromisoformat(t.replace("Z","+00:00"))
      age=max(0,int((now-stamp).total_seconds()))
      latest[symbol]={"symbol":symbol,"last_heartbeat":t,"age_seconds":age,"fresh":age<720}
     except (ValueError,TypeError,AttributeError):continue
    result=research_report()
    return self.reply(200,{"agent":"Big Ben reliability + research","mode":"read_only","checked_at":now.isoformat(),
      "services":{"storage":storage_kind(),"twelve_data_key_configured":bool(twelve_data_key()),"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))},
      "tracked_symbols":list(latest.values()),"research":{"status":result["status"],"observed_outcomes":result["observed_outcomes"],"signals_examined":result["signals_examined"]},
      "capabilities":["Monitor TradingView heartbeat freshness","Audit historical signal observations","Report missing provider configuration"],
      "not_enabled":["Automatic Pine editing","Automatic strategy retraining","Broker order execution"]})
   except Exception:return self.reply(503,{"error":"agent_status_unavailable"})
  if path=="/api/learning":
   try:return self.reply(200,learning_audit())
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if path=="/api/research":
   try:return self.reply(200,research_report())
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if path=="/api/outcomes":
   try:return self.reply(200,evaluate_signals())
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if path=="/api/status":
   try:
    rows=list_events()
    last=rows[0] if rows else None
    symbols={}
    for symbol,event,t,payload in rows:
     if symbol not in symbols:symbols[symbol]={"symbol":symbol,"last_seen":t,"last_event":event,"heartbeat_count":0,"trade_count":0,"last_close":None,"m15":None,"h1":None,"h4":None}
     if event=="HEARTBEAT" and symbols[symbol]["last_close"] is None:
      try:
       d=json.loads(payload)
       symbols[symbol].update({"last_close":d.get("close"),"m15":d.get("m15"),"h1":d.get("h1"),"h4":d.get("h4")})
      except (ValueError,TypeError):pass
     if event=="HEARTBEAT":symbols[symbol]["heartbeat_count"]+=1
     if event in ("BUY","SELL"):symbols[symbol]["trade_count"]+=1
    return self.reply(200,{"last_event_time":last[2] if last else None,"last_event_symbol":last[0] if last else None,"recent_trade_count":sum(1 for r in rows if r[1] in ("BUY","SELL")),"recent_heartbeat_count":sum(1 for r in rows if r[1]=="HEARTBEAT"),"symbols":list(symbols.values()),"storage":storage_kind(),"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))})
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if path=="/api/events":
   kind=parse_qs(urlsplit(self.path).query).get("type",["trades"])[0]
   if kind not in ("trades","all","heartbeat"):return self.reply(400,{"error":"type"})
   try:rows=list_events(150,kind)
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
   events=[]
   for symbol,event,t,payload in rows:
    d=json.loads(payload)
    events.append({"symbol":symbol,"event":event,"time":t,"received_at":d.get("received_at"),"entry":d.get("entry"),"sl":d.get("sl"),"tp":d.get("tp"),"rr":d.get("rr"),"evidence":d.get("evidence"),"confidence":d.get("confidence"),"entry_zone_low":d.get("entry_zone_low"),"entry_zone_high":d.get("entry_zone_high"),"htf_bias":d.get("htf_bias")})
   return self.reply(200,{"events":events,"count":len(events),"storage":storage_kind(),"source":"TradingView webhooks"})
  try:body=(Path(__file__).resolve().parents[1]/"index.html").read_bytes()
  except OSError:return self.reply(503,{"error":"dashboard_unavailable"})
  self.send_response(200)
  for k,v in {"Content-Type":"text/html; charset=utf-8","Content-Length":str(len(body)),"Cache-Control":"no-store","X-Frame-Options":"DENY","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Content-Security-Policy":"default-src 'none'; style-src 'self' 'unsafe-inline' https://*.tradingview.com; script-src 'self' 'unsafe-inline' https://s3.tradingview.com; frame-src https://*.tradingview.com; img-src 'self' data: https://*.tradingview.com; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_POST(self):
  if urlsplit(self.path).path=="/api/test-telegram":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   global LAST_TEST_SENT
   now=time.monotonic()
   if now-LAST_TEST_SENT<60:return self.reply(429,{"error":"rate_limited","retry_after_seconds":60})
   LAST_TEST_SENT=now
   result=send_telegram_message("✅ Big Ben AI Pro — رسالة اختبار اتصال Telegram. لا توجد صفقة أو إشارة تداول.")
   print("telegram_test_delivery="+result,flush=True)
   return self.reply(200 if result=="sent" else 503,{"status":result,"test_only":True})
  if urlsplit(self.path).path!="/v1/tradingview/events":return self.reply(404,{"error":"not_found"})
  secret=os.getenv("BIGBEN_WEBHOOK_TOKEN","")
  if len(secret)<32:return self.reply(503,{"error":"not_configured"})
  try:n=int(self.headers.get("Content-Length","0"))
  except ValueError:return self.reply(400,{"error":"length"})
  if n<1 or n>8192:return self.reply(413,{"error":"size"})
  try:d=json.loads(self.rfile.read(n))
  except (ValueError,UnicodeDecodeError):return self.reply(400,{"error":"json"})
  if not isinstance(d,dict):return self.reply(400,{"error":"json"})
  token=d.pop("token","")
  if not isinstance(token,str) or not secure_equal(token,secret):return self.reply(401,{"error":"unauthorized"})
  try:validate(d)
  except ValueError as e:return self.reply(422,{"error":str(e)})
  try:duplicate=save_event(d)
  except Exception:return self.reply(503,{"error":"storage_unavailable"})
  self.reply(200 if duplicate else 202,{"accepted":True,"duplicate":duplicate,"event_id":d["event_id"]})
  if not duplicate and d.get("event") in ("BUY","SELL"):
   # Respond to TradingView before the potentially slow Telegram API call.
   import threading
   def deliver():
    status=telegram_notify(d)
    print("telegram_delivery="+status,flush=True)
   threading.Thread(target=deliver,daemon=True).start()
if __name__=="__main__":
 init()  # Create schema once at process startup, not for every incoming M5 event.
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8080"))),Handler).serve_forever()
