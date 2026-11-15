"""Big Ben AI Pro: read-only webhook receiver. No broker/order endpoints."""
import os,json,hmac,math,re,sqlite3,time,base64,csv,io,urllib.request,urllib.error,hashlib,threading
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
_pspec=importlib.util.spec_from_file_location("bigben_market_probe",Path(__file__).with_name("market_probe.py"))
_probe=importlib.util.module_from_spec(_pspec)
_pspec.loader.exec_module(_probe)
_hspec=importlib.util.spec_from_file_location("bigben_history",Path(__file__).with_name("market_history.py"))
_history=importlib.util.module_from_spec(_hspec)
_hspec.loader.exec_module(_history)
_rspec=importlib.util.spec_from_file_location("bigben_research",Path(__file__).resolve().parents[2]/"research"/"orchestrator.py")
_research=importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(_research)
for _extra in ("news","desk","ai_provider","instruments","destinations","whatsapp","smt_research","workspace","operations","backup"):
 _spec=importlib.util.spec_from_file_location("bigben_"+_extra,Path(__file__).with_name(_extra+".py"))
 _module=importlib.util.module_from_spec(_spec)
 _spec.loader.exec_module(_module)
 globals()["_"+_extra]=_module
_rpspec=importlib.util.spec_from_file_location("bigben_replay",Path(__file__).resolve().parents[2]/"research"/"pine_replay.py")
_replay=importlib.util.module_from_spec(_rpspec)
_rpspec.loader.exec_module(_replay)
MARKET_DATA_DIAGNOSTIC={"state":"UNKNOWN","reason":"probe_not_completed","realtime_verified":False,"futures_coverage_verified":False}

def check_market_connection():
 global MARKET_DATA_DIAGNOSTIC
 MARKET_DATA_DIAGNOSTIC=_probe.probe_twelve_data(twelve_data_key())
 print("market_probe state="+MARKET_DATA_DIAGNOSTIC["state"]+" reason="+MARKET_DATA_DIAGNOSTIC["reason"],flush=True)

def current_strategy_source(directory=None):
 directory=Path(directory) if directory is not None else Path(__file__).resolve().parents[2]/"tradingview"
 manifest=json.loads((directory/"current_strategy.json").read_text(encoding="utf-8"))
 source_name=manifest["source"]
 if not isinstance(source_name,str) or Path(source_name).name!=source_name or not source_name.endswith(".pine"):
  raise ValueError("invalid_source_manifest")
 content=(directory/source_name).read_text(encoding="utf-8")
 digest=hashlib.sha256(content.encode("utf-8")).hexdigest()
 if not hmac.compare_digest(digest,manifest["source_sha256"]):raise ValueError("source_manifest_mismatch")
 return {**manifest,"code":content,"mode":"read_only_versioned_source",
  "changes_to_live_tradingview":False}

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
   _history.migrate(c)
   _research.migrate(c)
   _news.migrate(c)
   _ai_provider.migrate(c)
   _desk.migrate(c)
   _destinations.migrate(c)
   _replay.migrate(c)
   _workspace.migrate(c)
   _operations.migrate(c)
 else:
  DB.parent.mkdir(parents=True,exist_ok=True)
  with sqlite_connection() as c:
   c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,symbol TEXT,event TEXT,time TEXT,payload TEXT)")
   _migrations.migrate_events(c)
   _history.migrate(c)
   _research.migrate(c)
   _news.migrate(c)
   _ai_provider.migrate(c)
   _desk.migrate(c)
   _destinations.migrate(c)
   _replay.migrate(c)
   _workspace.migrate(c)
   _operations.migrate(c)
def history_connection():
 return pg_connect() if postgres_enabled() else sqlite_connection()

def refresh_market_history():
 """Three requests max per six-hour cycle; no retries or guessed contracts."""
 for symbol in _history.FOREX:
  now=datetime.now(timezone.utc)
  with history_connection() as c:
   checks=_history.coverage(c,now,postgres=postgres_enabled())["symbols"]
  prior=next(item for item in checks if item["symbol"]==symbol)
  if prior.get("adapter_version")==_history.ADAPTER_VERSION and prior.get("checked_at") and (now-datetime.fromisoformat(prior["checked_at"])).total_seconds()<21600:
   continue
  try:
   rows,result=_history.fetch_m5(symbol,twelve_data_key(),now)
   result.update(state="CONNECTED",reason="validated_closed_m5_history")
  except _history.HistoryError as error:
   rows=[]
   result={"symbol":symbol,"state":"DEGRADED" if twelve_data_key() else "DISCONNECTED",
     "reason":str(error),"checked_at":now.isoformat(),"realtime_verified":False,
     "adapter_version":_history.ADAPTER_VERSION}
  with history_connection() as c:
   result=_history.store_check(c,symbol,result,rows,postgres=postgres_enabled())
  print("market_history symbol="+symbol+" state="+result["state"]+" reason="+result["reason"]+" inserted="+str(result["candles_inserted"]),flush=True)

def run_daily_research():
 now=datetime.now(timezone.utc)
 marker="%s" if postgres_enabled() else "?"
 strategy=current_strategy_source()
 for symbol in _history.FOREX:
  with history_connection() as c:
   prior=c.execute("SELECT id FROM research_runs WHERE symbol="+marker+" AND created_at >= "+marker+" LIMIT 1",(symbol,now.date().isoformat())).fetchone()
   if prior:continue
   data=c.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker+" ORDER BY time DESC LIMIT 1000",(symbol,)).fetchall()
  if len(data)<120:continue
  rows=[dict(zip(("time","open","high","low","close"),r)) for r in reversed(data)]
  try:
   report=_research.run(symbol,rows,strategy,now)
   with history_connection() as c:_research.save(c,report,postgres=postgres_enabled())
   print("research_run symbol="+symbol+" status="+report["status"]+" tasks="+str(len(report["tasks"])),flush=True)
  except Exception:print("research_run symbol="+symbol+" status=failed reason=validation_or_storage_failure",flush=True)

def run_pine_research():
 now=datetime.now(timezone.utc)
 strategy=current_strategy_source()
 events=list_events(2000,"all")
 marker="%s" if postgres_enabled() else "?"
 for label in _history.FOREX:
  market=_desk.normalize(label)
  tick=None
  for symbol,kind,stamp,payload in events:
   if symbol!=market:continue
   try:
    value=json.loads(payload).get("tick_size")
    if type(value) in (int,float) and math.isfinite(value) and value>0:tick=value;break
   except (ValueError,TypeError):continue
  if tick is None:continue
  with history_connection() as c:
   data=c.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker+" ORDER BY time DESC LIMIT 1000",(label,)).fetchall()
  if len(data)<120:continue
  rows=[dict(zip(("time","open","high","low","close"),r)) for r in reversed(data)]
  digest=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
  run_id=hashlib.sha256((label+digest+str(tick)+_replay.ENGINE_SHA256+strategy["source_sha256"]).encode()).hexdigest()
  with history_connection() as c:
   if c.execute("SELECT id FROM pine_replay_runs WHERE id="+marker,(run_id,)).fetchone():continue
  try:
   report=_replay.replay(rows,tick,now=now)
   report.update(run_id=run_id,symbol=label,created_at=now.isoformat(),source_provider="Twelve Data",
    dataset_sha256=digest,start=rows[0]["time"],end=rows[-1]["time"],candles=len(rows),
    source_strategy_version=strategy.get("strategy_version",strategy["version"]),pine_source_sha256=strategy["source_sha256"],tick_size_source=market+" authenticated webhook")
   with history_connection() as c:_replay.save(c,report,postgres_enabled())
   print("pine_replay symbol="+label+" status=research_only trades="+str(len(report["trades"])),flush=True)
  except Exception:print("pine_replay symbol="+label+" status=failed reason=validation_or_storage_failure",flush=True)

def news_worker():
 while True:
  try:_news.refresh(history_connection,postgres_enabled())
  except Exception:print("news_refresh state=failed",flush=True)
  time.sleep(3600)

SIGNAL_ANALYSIS_SLOTS=threading.BoundedSemaphore(2)
BACKUP_SLOT=threading.BoundedSemaphore(1)

def analyze_instrument(symbol,include_ai=False):
 with history_connection() as c:news=_news.snapshot(c)
 result=_desk.analyze(symbol,list_events(2000,"all"),news)
 with history_connection() as c:reports=_replay.latest(c)["runs"]
 report=next((r for r in reports if _desk.normalize(r["symbol"])==symbol),None)
 result["learning"]={"historical_report_available":bool(report),"pine_parity_verified":False,"automatic_changes":False,
  "rejection_counts":report.get("rejection_counts",{}) if report else {},"metrics":report.get("metrics",{}) if report else {}}
 for task in result["agent_tasks"]:
  if task["role"]=="learning":task["output"]="تقرير المحاكاة متاح لمراجعة حالات الرفض والنتائج؛ لا تعديل تلقائي" if report else "لا يوجد تقرير تاريخي لهذا الرمز؛ لا يُستنتج تحسن أو تعلم مثبت"
 with history_connection() as c:result["smt_research"]=_smt_research.from_storage(c,symbol,result["instrument"]["smt_comparison"]["candidate_symbol"],postgres_enabled())
 result["ai"]=_ai_provider.review(result,history_connection,postgres_enabled()) if include_ai else _ai_provider.status()
 with history_connection() as c:_desk.record(c,result,postgres_enabled())
 return result

def run_signal_analysis(symbol):
 if not SIGNAL_ANALYSIS_SLOTS.acquire(blocking=False):
  print("signal_analysis skipped=capacity",flush=True);return
 try:
  result=analyze_instrument(symbol,True)
  print("signal_analysis state=completed decision="+result["decision"]+" ai_state="+result["ai"]["state"],flush=True)
 except Exception:print("signal_analysis state=failed",flush=True)
 finally:SIGNAL_ANALYSIS_SLOTS.release()

def integration_status():
 rows=list_events(2000,"all");now=datetime.now(timezone.utc);tracked={}
 for symbol,kind,stamp,payload in rows:
  if symbol in tracked:continue
  try:
   data=json.loads(payload);dt=datetime.fromisoformat(stamp.replace("Z","+00:00"))
   age=(now-dt).total_seconds()
   tracked[symbol]={"symbol":symbol,"source_time":stamp,"received_at":data.get("received_at"),"fresh":0<=age<720,"strategy_version":data.get("strategy_version"),"bridge_version":data.get("bridge_version")}
  except (ValueError,TypeError,AttributeError):continue
 with history_connection() as c:
  feeds=_news.snapshot(c)
  coverage=_history.coverage(c,postgres=postgres_enabled())
 return {"checked_at":now.isoformat(),"tradingview":{"symbols":list(tracked.values()),"fresh_symbols":sum(s["fresh"] for s in tracked.values()),"expected_symbols":len(set(_desk.SYMBOLS.values()) | set(tracked)),"observed_symbols":len(tracked)},
  "market_data":coverage,"news":feeds["sources"],"ai":_ai_provider.status(),"storage":storage_kind(),
  "telegram":{"configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),"delivery_verified_now":False}}

def run_history_cycle():
 with history_connection() as c:token=_operations.claim(c,"history_research",postgres=postgres_enabled())
 if token is None:return "already_running"
 stages=[]
 for name,action in (("history",refresh_market_history),("proxy_research",run_daily_research),("pine_replay",run_pine_research)):
  started=datetime.now(timezone.utc).isoformat()
  try:
   action();stages.append({"name":name,"status":"COMPLETED","started_at":started,"finished_at":datetime.now(timezone.utc).isoformat(),"meaning":"function returned; see data coverage and reports for actual results"})
  except Exception:
   stages.append({"name":name,"status":"FAILED","started_at":started,"finished_at":datetime.now(timezone.utc).isoformat(),"reason":"storage_or_internal_failure"})
 with history_connection() as c:
  status=_operations.finish(c,token,stages,postgres=postgres_enabled())
  report=_operations.save_daily(c,{"coverage":_history.coverage(c,postgres=postgres_enabled()),
      "research":_research.latest(c),"replay":_replay.latest(c),"cycle_status":status},postgres=postgres_enabled())
 if report and os.getenv("BIGBEN_DAILY_TELEGRAM_ENABLED","1")=="1":
  delivery=send_telegram_message(report["arabic_report"])
  with history_connection() as c:_operations.notification_result(c,report,delivery,postgres_enabled())
 return status

def history_worker():
 # A sleeping free Render service cannot guarantee a wall-clock schedule.
 while True:
  try:run_history_cycle()
  except Exception:print("market_history cycle=failed reason=storage_or_internal_failure",flush=True)
  time.sleep(21600)

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
 pair=_scalping.levels(d);full,scalp=pair["full_trade"],pair["scalp"]
 instrument=_instruments.describe(d["symbol"])
 kind={"forex":"فوركس","futures":"فيوتشرز","metals":"معادن"}.get(instrument["asset_class"],"سوق")
 side="🟢 شراء BUY" if d["event"]=="BUY" else "🔴 بيع SELL"
 from zoneinfo import ZoneInfo
 try:stamp=datetime.fromisoformat(d["time"].replace("Z","+00:00")).astimezone(ZoneInfo("Asia/Muscat")).strftime("%Y-%m-%d %H:%M")
 except (KeyError,ValueError,TypeError):stamp="غير متاح"
 lines=["📊 BIG BEN AI PRO",side+" | "+kind,"الاسم: "+instrument["name"],"الرمز: "+instrument["symbol"],"الفريم: M5 | مسقط: "+stamp,
  "", "① الصفقة الكاملة — الهدف الأصلي", "الدخول Entry: "+str(full["entry"]),"الوقف SL: "+str(full["sl"]),"الهدف TP: "+str(full["tp"])+" | RR: "+str(round(full["rr"],4)),
  "", "② خيار السكالب — هدف حسابي بديل", "الدخول Entry: "+str(scalp["entry"]),"الوقف SL: "+str(scalp["sl"]),"الهدف TP: "+str(scalp["tp"])+" | RR: "+str(round(scalp["rr"],4))]
 checks=_desk.condition_checks(d.get("analysis",{}) if isinstance(d.get("analysis"),dict) else {})
 confirmed=[c["label"] for c in checks if c["state"]=="PASSED"]
 lines.extend(["", "أدلة المؤشر: "+("؛ ".join(confirmed[:5]) if confirmed else "تفاصيل الشروط غير مستلمة؛ لا تُفترض متحققة"),
  "النسخة: "+str(d.get("strategy_version","غير متاحة")), "المخطط: "+instrument["chart_url"],
  "", "اختر أحد الخيارين؛ ليس السكالب إشارة مستقلة.","التكاليف وحجم التيك غير مؤكدين. تحليل فقط — لا يوجد تنفيذ أوامر."])
 return "\n".join(lines)

def whatsapp_notify(d):
 if d.get("event") not in ("BUY","SELL"):return "skipped"
 if not _whatsapp.status()["enabled"]:return "disabled"
 try:
  with history_connection() as c:recipient=_destinations.read(c)["whatsapp_number"]
  levels=_scalping.levels(d);instrument=_instruments.describe(d["symbol"])
  checks=_desk.condition_checks(d.get("analysis",{}) if isinstance(d.get("analysis"),dict) else {})
  evidence="؛ ".join(c["label"] for c in checks if c["state"]=="PASSED")[:512] or "تفاصيل الأدلة غير مستلمة"
  parameters=[instrument["name"]+" | "+instrument["symbol"],d["event"],str(levels["full_trade"]["entry"]),str(levels["full_trade"]["sl"]),str(levels["full_trade"]["tp"]),str(levels["scalp"]["tp"]),str(d["time"]),str(d.get("strategy_version","غير متاحة")),evidence]
  return _whatsapp.send_template(recipient,parameters)
 except (ValueError,KeyError,TypeError):return "invalid_signal"
 except Exception:return "storage_unavailable"

def telegram_destination():
 try:
  with history_connection() as c:chat=_destinations.read(c)["telegram_chat_id"]
 except Exception:return ""
 return chat or os.getenv("TELEGRAM_CHAT_ID","").strip()

def telegram_notify(d):
 # Explicit chat allowlist avoids accidentally sending private trade data to strangers.
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=telegram_destination()
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
 chat=telegram_destination()
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
  b=_backup.canonical(obj) if urlsplit(self.path).path=="/api/backup/export" else json.dumps(obj).encode();self.send_response(status)
  for k,v in {"Content-Type":"application/json","Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'none'","Content-Length":str(len(b))}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(b)
 def csv_reply(self,rows,filename):
  output=io.StringIO(newline="")
  fields=("time","received_at","symbol","event","event_id","entry","sl","tp","rr","close","m15","h1","h4","timeframe","strategy_version","bridge_version")
  writer=csv.DictWriter(output,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
  writer.writeheader()
  for row in rows:writer.writerow(row)
  body=output.getvalue().encode("utf-8-sig")
  self.send_response(200)
  for k,v in {"Content-Type":"text/csv; charset=utf-8","Content-Disposition":"attachment; filename=\""+filename+"\"","Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Length":str(len(body))}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=="/healthz":return self.reply(200,{"status":"ok","mode":"read-only"})
  if path=="/healthz/integrations":
   token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
   chat=telegram_destination()
   return self.reply(200,{"status":"ok","telegram":{"bot_token_configured":bool(token),"chat_id_configured":bool(re.fullmatch(r"-?[0-9]{5,20}",chat))},"tradingview":{"webhook_token_configured":len(os.getenv("BIGBEN_WEBHOOK_TOKEN",""))>=32},"database":{"storage":storage_kind()},"market_data":{"twelve_data_key_configured":bool(twelve_data_key()),"credentials_only":True,"probe":MARKET_DATA_DIAGNOSTIC.copy()}})
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
  if path not in ("/","/dashboard","/api/events","/api/events.csv","/api/status","/api/diagnostics","/api/market","/api/outcomes","/api/research","/api/agent","/api/learning","/api/data-sources","/api/pine/current","/api/analysis","/api/scalping","/api/market/coverage","/api/research/runs","/api/news","/api/integrations","/api/research/pine-runs","/api/instruments","/api/destinations","/api/analysis/runs","/api/workspace/drafts","/api/workspace/notes","/api/operations","/api/backup/export","/api/research/walk-forward"):return self.reply(404,{"error":"not_found"})
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
  if path=="/api/events.csv":
   rows=[]
   for symbol,event,stamp,payload in list_events(5000,"all"):
    try:data=json.loads(payload)
    except (ValueError,TypeError):data={}
    rows.append({"time":stamp,"received_at":data.get("received_at"),"symbol":symbol,"event":event,"event_id":data.get("event_id"),**data})
   return self.csv_reply(rows,"bigben-tradingview-events.csv")
  if path=="/api/research/walk-forward":
   try:
    report=json.loads((Path(__file__).resolve().parents[2]/"research/reports/walk-forward-2026-11-14.json").read_text(encoding="utf-8"))
    if report.get("mode")!="STATIC_DATED_RESEARCH_SNAPSHOT":raise ValueError("report_schema")
    root=Path(__file__).resolve().parents[2]
    runner_hash=hashlib.sha256(((root/"research/walk_forward.py").read_text(encoding="utf-8")+(root/"scripts/run_walk_forward_snapshot.py").read_text(encoding="utf-8")).encode()).hexdigest()
    source_hash=current_strategy_source()["source_sha256"]
    if any(r.get("runner_sha256")!=runner_hash or r.get("pine_source_sha256")!=source_hash or r.get("engine_sha256")!=_replay.ENGINE_SHA256 for r in report.get("runs",[])):raise ValueError("stale_research_source")
    return self.reply(200,report)
   except (OSError,ValueError,TypeError):return self.reply(503,{"error":"walk_forward_report_unavailable"})
  if path=="/api/backup/export":
   if not BACKUP_SLOT.acquire(blocking=False):return self.reply(429,{"error":"export_in_progress"})
   try:
    with history_connection() as c:result=_backup.snapshot(c,postgres_enabled())
    return self.reply(200,result)
   except ValueError:return self.reply(413,{"error":"snapshot_too_large_native_database_backup_required"})
   except Exception:return self.reply(503,{"error":"backup_unavailable"})
   finally:BACKUP_SLOT.release()
  if path in ("/api/workspace/drafts","/api/workspace/notes","/api/operations"):
   try:
    with history_connection() as c:
     if path=="/api/workspace/drafts":result=_workspace.drafts(c,current_strategy_source())
     elif path=="/api/operations":result=_operations.snapshot(c)
     else:
      raw=parse_qs(urlsplit(self.path).query).get("symbol",[None])[0]
      result=_workspace.notes(c,_desk.normalize(raw) if raw else None,postgres_enabled())
    return self.reply(200,result)
   except ValueError:return self.reply(400,{"error":"symbol"})
   except Exception:return self.reply(503,{"error":"workspace_unavailable"})
  if path=="/api/analysis/runs":
   try:
    with history_connection() as c:rows=c.execute("SELECT payload FROM analysis_runs ORDER BY created_at DESC LIMIT 20").fetchall()
    return self.reply(200,{"runs":[json.loads(row[0]) for row in rows],"signal_analysis_enabled":os.getenv("BIGBEN_SIGNAL_ANALYSIS_ENABLED","1")=="1","ai_daily_request_limit":10})
   except Exception:return self.reply(503,{"error":"analysis_history_unavailable"})
  if path=="/api/instruments":
   try:
    with history_connection() as c:preferences=_destinations.read(c)
    observed={r[0] for r in list_events(5000,"all")}
    return self.reply(200,{"instruments":_instruments.catalog(observed,preferences["watchlist"]),"arbitrary_qualified_symbols":True,"alert_coverage_not_implied":True})
   except Exception:return self.reply(503,{"error":"catalog_unavailable"})
  if path=="/api/destinations":
   try:
    with history_connection() as c:
     preferences=_destinations.read(c);deliveries=_destinations.recent(c)
    return self.reply(200,{**preferences,"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and (preferences["telegram_chat_id"] or os.getenv("TELEGRAM_CHAT_ID"))),"telegram_uses_server_default":not bool(preferences["telegram_chat_id"]),"whatsapp_mode":"automatic_template" if _whatsapp.status()["enabled"] else "manual_share","whatsapp_automatic_connected":_whatsapp.status()["provider_connection_verified"],"whatsapp":_whatsapp.status(),"deliveries":deliveries})
   except Exception:return self.reply(503,{"error":"settings_unavailable"})
  if path=="/api/integrations":
   try:return self.reply(200,integration_status())
   except Exception:return self.reply(503,{"error":"integrations_unavailable"})
  if path=="/api/news":
   try:
    with history_connection() as c:result=_news.snapshot(c)
    return self.reply(200,result)
   except Exception:return self.reply(503,{"error":"news_unavailable"})
  if path=="/api/research/pine-runs":
   try:
    run_id=parse_qs(urlsplit(self.path).query).get("id",[None])[0]
    with history_connection() as c:result=_replay.latest(c,run_id,postgres_enabled())
    return self.reply(200 if result is not None else 404,result or {"error":"run_not_found"})
   except ValueError:return self.reply(400,{"error":"run_id"})
   except Exception:return self.reply(503,{"error":"replay_unavailable"})
  if path=="/api/research/runs":
   try:
    with history_connection() as c:result=_research.latest(c)
    return self.reply(200,result)
   except Exception:return self.reply(503,{"error":"research_runs_unavailable"})
  if path=="/api/market/coverage":
   try:
    with history_connection() as c:result=_history.coverage(c,postgres=postgres_enabled())
    return self.reply(200,result)
   except Exception:return self.reply(503,{"error":"history_unavailable"})
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
   try:return self.reply(200,current_strategy_source())
   except (OSError,ValueError,KeyError,TypeError):return self.reply(503,{"error":"source_unavailable_or_mismatched"})
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
                    "futures_coverage":"not_confirmed","probe":MARKET_DATA_DIAGNOSTIC.copy()},
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
    events.append({"event_id":d.get("event_id"),"instrument":_instruments.describe(symbol),"notification_text":trade_notification_text(d) if event in ("BUY","SELL") else None,"symbol":symbol,"event":event,"time":t,"received_at":d.get("received_at"),"entry":d.get("entry"),"sl":d.get("sl"),"tp":d.get("tp"),"rr":d.get("rr"),"evidence":d.get("evidence"),"confidence":d.get("confidence"),"entry_zone_low":d.get("entry_zone_low"),"entry_zone_high":d.get("entry_zone_high"),"htf_bias":d.get("htf_bias")})
   return self.reply(200,{"events":events,"count":len(events),"storage":storage_kind(),"source":"TradingView webhooks"})
  try:body=(Path(__file__).resolve().parents[1]/"index.html").read_bytes()
  except OSError:return self.reply(503,{"error":"dashboard_unavailable"})
  self.send_response(200)
  for k,v in {"Content-Type":"text/html; charset=utf-8","Content-Length":str(len(body)),"Cache-Control":"no-store","X-Frame-Options":"DENY","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Content-Security-Policy":"default-src 'none'; style-src 'self' 'unsafe-inline' https://*.tradingview.com; script-src 'self' 'unsafe-inline' https://s3.tradingview.com; frame-src https://*.tradingview.com; img-src 'self' data: https://*.tradingview.com; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_POST(self):
  if urlsplit(self.path).path in ("/api/workspace/drafts","/api/workspace/notes"):
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   if self.headers.get("Content-Type","").split(";",1)[0]!="application/json":return self.reply(415,{"error":"json_content_type_required"})
   origin=self.headers.get("Origin")
   if origin and urlsplit(origin).netloc!=self.headers.get("Host"):return self.reply(403,{"error":"origin"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=150000:return self.reply(413,{"error":"size"})
    value=json.loads(self.rfile.read(size))
    with history_connection() as c:
     result=_workspace.create_draft(c,value,current_strategy_source(),postgres_enabled()) if urlsplit(self.path).path.endswith("drafts") else _workspace.save_note(c,value,_desk.normalize,postgres_enabled())
    return self.reply(201,result)
   except (ValueError,TypeError,UnicodeDecodeError):return self.reply(400,{"error":"invalid_workspace_input"})
   except Exception:return self.reply(503,{"error":"workspace_unavailable"})
  if urlsplit(self.path).path=="/api/destinations":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   if self.headers.get("Content-Type","").split(";",1)[0]!="application/json":return self.reply(415,{"error":"json_content_type_required"})
   origin=self.headers.get("Origin")
   if origin and urlsplit(origin).netloc!=self.headers.get("Host"):return self.reply(403,{"error":"origin"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=16384:return self.reply(413,{"error":"size"})
    preferences=_destinations.validate(json.loads(self.rfile.read(size)),_desk.normalize)
   except (ValueError,TypeError,UnicodeDecodeError):return self.reply(400,{"error":"invalid_destinations_or_symbols"})
   try:
    with history_connection() as c:_destinations.save(c,preferences,postgres_enabled())
    return self.reply(200,{"saved":True,**preferences,"whatsapp_automatic_connected":False})
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if urlsplit(self.path).path=="/api/analyze":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   if self.headers.get("Content-Type","").split(";",1)[0]!="application/json":return self.reply(415,{"error":"json_content_type_required"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=2048:return self.reply(413,{"error":"size"})
    request=json.loads(self.rfile.read(size))
    if not isinstance(request,dict):raise ValueError()
    symbol=_desk.normalize(request.get("symbol"))
   except (ValueError,TypeError,UnicodeDecodeError):return self.reply(400,{"error":"symbol_or_json","symbols":list(_desk.SYMBOLS)})
   try:
    result=analyze_instrument(symbol,request.get("ai") is True)
    return self.reply(200,result)
   except Exception:return self.reply(503,{"error":"analysis_unavailable"})
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
    try:
     with history_connection() as c:_destinations.receipt(c,d["event_id"],"telegram",status,postgres_enabled())
    except Exception:print("delivery_receipt storage_unavailable",flush=True)
    print("telegram_delivery="+status,flush=True)
    whatsapp_status=whatsapp_notify(d)
    if whatsapp_status!="disabled":
     try:
      with history_connection() as c:_destinations.receipt(c,d["event_id"],"whatsapp",whatsapp_status,postgres_enabled())
     except Exception:print("whatsapp_receipt storage_unavailable",flush=True)
     print("whatsapp_delivery="+whatsapp_status,flush=True)
    if os.getenv("BIGBEN_SIGNAL_ANALYSIS_ENABLED","1")=="1":run_signal_analysis(d["symbol"])
   threading.Thread(target=deliver,daemon=True).start()
if __name__=="__main__":
 init()  # Create schema once at process startup, not for every incoming M5 event.
 import threading
 threading.Thread(target=check_market_connection,daemon=True).start()
 threading.Thread(target=history_worker,daemon=True).start()
 threading.Thread(target=news_worker,daemon=True).start()
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8080"))),Handler).serve_forever()
