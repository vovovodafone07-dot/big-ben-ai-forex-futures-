"""Big Ben AI Pro: read-only webhook receiver. No broker/order endpoints."""
import os,json,hmac,math,re,sqlite3,time,base64,csv,io,urllib.request,urllib.error,hashlib,threading,sys
# Arabic operational logs must also work on Windows pipes with a legacy code page.
for _stream in (sys.stdout,sys.stderr):
 if callable(getattr(_stream,"reconfigure",None)):_stream.reconfigure(encoding="utf-8",errors="backslashreplace")
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
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
for _extra in ("news","desk","ai_provider","instruments","destinations","whatsapp","smt_research","workspace","operations","backup","market_sessions","market_pulses","event_pipeline","analysis_opportunities","native_chart_analysis","crypto_history","instant_engine","futures_preflight","instant_telegram","arabic_event_engine","connected_market","native_trade_journal","tradingview_dynamic_sync","connected_symbols_v2","telegram_interactive","bridge_validation","transport_fixture","live_candle_adapter","tv_watchlist","tradingview_candles","pattern_audit","massive_history"):
 _spec=importlib.util.spec_from_file_location("bigben_"+_extra,Path(__file__).with_name(_extra+".py"))
 _module=importlib.util.module_from_spec(_spec)
 _spec.loader.exec_module(_module)
 globals()["_"+_extra]=_module
_rpspec=importlib.util.spec_from_file_location("bigben_replay",Path(__file__).resolve().parents[2]/"research"/"pine_replay.py")
_replay=importlib.util.module_from_spec(_rpspec)
_rpspec.loader.exec_module(_replay)
MARKET_DATA_DIAGNOSTIC={"state":"UNKNOWN","reason":"probe_not_completed","realtime_verified":False,"futures_coverage_verified":False}

_demo_spec=importlib.util.spec_from_file_location("bigben_tradovate_demo",Path(__file__).with_name("tradovate_demo.py"))
_demo=importlib.util.module_from_spec(_demo_spec)
_demo_spec.loader.exec_module(_demo)

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
   _market_pulses.migrate(c)
   _instant_telegram.migrate(c)
   _arabic_event_engine.migrate(c)
   _native_trade_journal.migrate(c)
   _connected_market.migrate(c)
   _tradingview_dynamic_sync.migrate(c)
   _telegram_interactive.migrate(c)
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
   _market_pulses.migrate(c)
   _instant_telegram.migrate(c)
   _arabic_event_engine.migrate(c)
   _native_trade_journal.migrate(c)
   _connected_market.migrate(c)
   _tradingview_dynamic_sync.migrate(c)
   _telegram_interactive.migrate(c)
def history_connection():
 return pg_connect() if postgres_enabled() else sqlite_connection()

def refresh_market_history():
 """Use one budgeted ingestion path; never probe a pair outside TV membership."""
 return refresh_tracked_candles_once()

def run_daily_research():
 now=datetime.now(timezone.utc)
 marker="%s" if postgres_enabled() else "?"
 strategy=current_strategy_source()
 for symbol in _history.REFRESH_FOREX:
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
 for label in _history.REFRESH_FOREX:
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

def market_pulse_worker():
 """Analyze stored closed candles periodically; never emits BUY/SELL or orders."""
 while True:
  try:
   now=datetime.now(timezone.utc)
   with history_connection() as c:
    coverage=_history.coverage(c,now,postgres=postgres_enabled())
    for item in coverage.get("symbols",[]):
     symbol=item.get("symbol")
     if symbol not in _history.REFRESH_FOREX:continue
     marker="%s" if postgres_enabled() else "?"
     # Select the newest bounded window, then restore chronological EMA order.
     rows=c.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker+" ORDER BY time DESC LIMIT 1000",(symbol,)).fetchall()[::-1]
     result=_market_pulses.analyze(symbol,rows,now)
     _market_pulses.save(c,result,postgres_enabled())
     print("market_pulse symbol="+symbol+" state="+result["state"]+" decision="+result["decision"],flush=True)
  except Exception:
   print("market_pulse state=failed reason=storage_or_internal_failure",flush=True)
  time.sleep(int(os.getenv("BIGBEN_MARKET_PULSE_SECONDS","300")))

def send_arabic_market_event(event):
 """Durably claim one verified technical/news event and send at once."""
 if not os.getenv("TELEGRAM_BOT_TOKEN","").strip():
  return "not_configured"
 chat=telegram_destination()
 if not re.fullmatch(r"-?[0-9]{5,20}",chat):
  return "not_configured"
 with history_connection() as db:
  key=_arabic_event_engine.reserve(db,event,postgres_enabled())
 if not key:return "duplicate"
 try:
  content=(_arabic_event_engine.technical_message(event) if event["kind"]=="technical"
           else _arabic_event_engine.news_message(event))
  delivery=send_telegram_message(content,category="news" if event["kind"]=="news" else "analysis")
 except Exception:delivery="failed"
 try:
  with history_connection() as db:_arabic_event_engine.finish(db,key,delivery,postgres_enabled())
 except Exception:print("arabic_event status=delivery_receipt_failed",flush=True)
 return delivery

def scan_arabic_market_once(now=None):
 """Check bounded tracked, matched market sources and real official calendar.
 No price feed means no price event; licensed futures source never substituted.
 """
 now=now or datetime.now(timezone.utc)
 # Refresh watched supported sources BEFORE filtering by freshness. Otherwise a
 # stale asset is excluded from the very scan that could restore its data.
 refresh_tracked_crypto_once(now)
 refresh_tracked_candles_once(now)
 with history_connection() as db:
  from_market=tuple(item["symbol"] for item in owner_connected_assets(db,now))[:100]
 results={"checked_at":now.isoformat(),"symbols":{},"events":0,"news":0}
 for symbol in from_market:
  stage='فحص الجلسة'
  try:
   if _instruments.describe(symbol)['asset_class']=='forex' and _connected_market.forex_weekly_closed(now):
    results['symbols'][symbol]='السوق مغلق أسبوعياً'
    with history_connection() as db:_connected_market.record_open_state(db,symbol,False,postgres_enabled(),now)
    continue
   stage='تحليل الشموع'
   analysis=analyze_instant_native(symbol,"scalp")
   results["symbols"][symbol]=analysis["status"]
   live=_connected_market.gate(analysis,now)
   with history_connection() as db:
    newly_opened=_connected_market.record_open_state(db,symbol,live["open"],postgres_enabled(),now)
   if newly_opened=="opened":
    notification="🟢 استئناف بيانات السوق | "+symbol+"\n━━━━━━━━━━━━━━━━━━\nعادت شموع مغلقة حديثة من المصدر المطابق.\nهذا تحديث اتصال؛ لا يثبت افتتاح جلسة البورصة أو وجود صفقة."
    send_telegram_message(notification,category="market")
   if analysis["status"]=="DATA_UNAVAILABLE":continue
   provider=analysis.get('provider')
   if provider==_tradingview_candles.PROVIDER:
    with history_connection() as db:rows,_=_tradingview_candles.read(db,symbol,postgres_enabled())
   elif provider=="Bitstamp" and symbol.startswith("BITSTAMP:"):
    rows,_=bitstamp_native_candles(symbol,now)
   elif provider=="Twelve Data" and re.fullmatch(r"OANDA:[A-Z]{6}",symbol):
    base=symbol.split(":",1)[1]
    pair=base[:3]+"/"+base[3:]
    mark="%s" if postgres_enabled() else "?"
    with history_connection() as db:
     rows=db.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+mark+" ORDER BY time DESC LIMIT 1000",(pair,)).fetchall()
   else:
    continue
   stage='متابعة سجل الصفقة'
   with history_connection() as db:
    _native_trade_journal.follow(db,symbol,rows,postgres_enabled(),now,provider=provider)
   stage='كشف الحدث الفني'
   for event in _arabic_event_engine.technical_events(symbol,rows,now):
    status=send_arabic_market_event(event)
    if status=="sent":results["events"]+=1
   # Previously eligible plans follow same dedup as interactive Analyze.
   alert=trigger_instant_telegram(analysis)
   results["symbols"][symbol]=analysis["status"]+" / "+alert.get("status","none")
  except Exception as error:
   reason={KeyError:'حقل مطلوب غير متاح',TypeError:'نوع بيانات غير متوافق',ValueError:'قيمة بيانات غير صالحة'}.get(type(error),'تعذر إكمال المعالجة')
   print('تشخيص_الماسح الرمز='+symbol+' المرحلة='+stage+' السبب='+reason,flush=True)
 try:
  # Journal transitions and their pending outbox rows commit atomically above.
  with history_connection() as db:movements=_native_trade_journal.claim_notifications(db,postgres_enabled(),now=now)
  for movement in movements:
   try:delivery=send_telegram_message(_native_trade_journal.management_message(movement,now),category="management")
   except Exception:delivery="uncertain"
   # Generic sender cannot distinguish rejection from an accepted response lost in transit.
   if delivery=="failed":delivery="uncertain"
   with history_connection() as db:_native_trade_journal.finish_notification(db,movement["event_id"],delivery,postgres_enabled())
 except Exception:print("إدارة_الصفقات حالة=تعذر_تأكيد_التسليم",flush=True)
 try:deliver_trade_digest(now)
 except Exception:print("ملخص_الصفقات حالة=تعذر_المعالجة",flush=True)
 try:
  with history_connection() as db:
   news=_news.snapshot(db,now)
  deliver_bot_news(news,now)
  for event in _arabic_event_engine.news_scenarios(news,now):
   if event.get("event_type")!="RELEASED":continue
   delivery=send_arabic_market_event(event)
   if delivery=="sent":results["news"]+=1
 except Exception:print("arabic_scanner news=failed",flush=True)
 return results

def arabic_market_scanner_worker():
 """Best effort bounded timer: no real-time guarantees on sleeping free hosts."""
 try:period=max(30,min(300,int(os.getenv("BIGBEN_ARABIC_SCANNER_SECONDS","60"))))
 except (TypeError,ValueError):period=60
 while True:
  try:
   result=scan_arabic_market_once()
   print("arabic_scanner status=checked market_alerts="+str(result["events"])+" news_alerts="+str(result["news"]),flush=True)
  except Exception:print("arabic_scanner status=failed",flush=True)
  time.sleep(period)

def agent_watchdog():
 """Resident operational monitor; records symptoms in logs, never edits Pine or executes orders."""
 while True:
  try:
   state=integration_status()
   fresh=state.get("tradingview",{}).get("fresh_symbols",0)
   news=sum(1 for item in state.get("news",[]) if item.get("state")=="CONNECTED" and item.get("fresh"))
   print("agent_watchdog state=running fresh_symbols="+str(fresh)+" fresh_news_sources="+str(news)+" learning=evidence_only",flush=True)
  except Exception:
   print("agent_watchdog state=degraded reason=internal_check_failed",flush=True)
  time.sleep(300)

SIGNAL_ANALYSIS_SLOTS=threading.BoundedSemaphore(2)
BACKUP_SLOT=threading.BoundedSemaphore(1)

NATIVE_FETCH_TIMES=[]
NATIVE_FETCH_LOCK=threading.Lock()
ADAPTER_FETCH_LOCK=threading.Lock()

def refresh_tracked_candles_once(now=None):
 """Read-only cached ingestion; references never promote a feed to live."""
 now=now or datetime.now(timezone.utc)
 if not ADAPTER_FETCH_LOCK.acquire(blocking=False):return {}
 result={}
 try:
  with history_connection() as db:symbols=sorted(owner_watchlist(db))
  for symbol in symbols:
   spec=_live_candle_adapter.mapping(symbol)
   if not spec:continue
   with history_connection() as db:_,tv_meta=_tradingview_candles.read(db,symbol,postgres_enabled())
   if _tradingview_candles.fresh(tv_meta,now):continue
   with history_connection() as db:_,prior=_live_candle_adapter.read(db,symbol,postgres_enabled())
   try:
    age=(now-datetime.fromisoformat(prior['checked_at'])).total_seconds()
    ttl=300 if prior.get('provider')=='Twelve Data' else 900
    if 0<=age<ttl:continue
   except (ValueError,KeyError,TypeError):pass
   def primary(s,key,at):
    if not spec['twelve']:raise _live_candle_adapter.CandleError('unsupported')
    if not key:raise _live_candle_adapter.CandleError('not_configured')
    with history_connection() as db:allowed=_live_candle_adapter.reserve(db,'twelve',at,postgres_enabled())
    if not allowed:raise _live_candle_adapter.CandleError('budget')
    return _live_candle_adapter.twelve(s,key,at)
   def fallback(s,at):
    with history_connection() as db:allowed=_live_candle_adapter.reserve(db,'yahoo',at,postgres_enabled())
    if not allowed:raise _live_candle_adapter.CandleError('budget')
    return _live_candle_adapter.yahoo(s,at)
   rows,meta=_live_candle_adapter.fetch(symbol,twelve_data_key(),now,primary=primary,fallback=fallback)
   with history_connection() as db:
    _live_candle_adapter.store(db,symbol,rows,meta,postgres_enabled())
    # Keep the existing FX research reader populated from the same successful
    # primary fetch. Do not copy Yahoo/reference bars into Twelve Data history.
    if rows and spec['kind']=='forex' and meta.get('provider')=='Twelve Data':
     legacy=dict(meta,symbol=spec['twelve'],adapter_version=_history.ADAPTER_VERSION,
                 state='CONNECTED' if meta['fresh'] else 'STALE')
     _history.store_check(db,spec['twelve'],legacy,rows,postgres_enabled())
   result[symbol]=meta['state']
   print('محول_الشموع الرمز='+symbol+' المصدر='+str(meta.get('provider') or 'غير متاح')+' الحالة='+meta['state']+' الشموع='+str(len(rows))+' العمر='+str(meta.get('source_age_seconds','غير متاح')),flush=True)
 finally:ADAPTER_FETCH_LOCK.release()
 return result

def refresh_tracked_crypto_once(now=None):
 now=now or datetime.now(timezone.utc)
 with history_connection() as c:symbols=sorted(owner_watchlist(c))
 result={}
 for symbol in symbols:
  if symbol not in _connected_market.SUPPORTED_CRYPTO:continue
  try:
   rows,meta=bitstamp_native_candles(symbol,now)
   stamp=datetime.fromisoformat(str(meta.get('last_candle','')).replace('Z','+00:00'))
   age=(now-stamp).total_seconds()
   fresh=meta.get('state')=='CONNECTED' and 300<=age<=630
   result[symbol]=fresh
   print('تحديث_المتابعة الرمز='+symbol+' شمعة='+stamp.isoformat()+' العمر_بالثواني='+str(round(age))+' حديث='+('نعم' if fresh else 'لا'),flush=True)
  except Exception:
   result[symbol]=False
   print('تحديث_المتابعة الرمز='+symbol+' الحالة=تعذر_التحقق',flush=True)
 return result

def bitstamp_native_candles(symbol,now=None):
 """Bounded crypto OHLC ingestion shared by chart and Analyze, never a proxy feed."""
 _crypto_history.pair_from_symbol(symbol)
 now=now or datetime.now(timezone.utc)
 mark="%s" if postgres_enabled() else "?"
 try:
  with history_connection() as c:
   prev=c.execute("SELECT payload FROM market_history_checks WHERE symbol="+mark,(symbol,)).fetchone()
  prior=json.loads(prev[0]) if prev else {}
  try:
   checked=datetime.fromisoformat(prior["checked_at"].replace("Z","+00:00")) if prior.get("checked_at") else None
   stamp=datetime.fromisoformat(prior['last_candle'].replace('Z','+00:00')) if prior.get('last_candle') else None
   needs_refresh=checked is None or not 0<=(now-checked).total_seconds()<90 or stamp is None or not 300<=(now-stamp).total_seconds()<=630
  except (ValueError,TypeError,AttributeError):needs_refresh=True
  if needs_refresh:
   allowed=False
   with NATIVE_FETCH_LOCK:
    tick=time.monotonic()
    NATIVE_FETCH_TIMES[:]=[v for v in NATIVE_FETCH_TIMES if tick-v<3600]
    if len(NATIVE_FETCH_TIMES)<90 and (not NATIVE_FETCH_TIMES or tick-NATIVE_FETCH_TIMES[-1]>=3):
     NATIVE_FETCH_TIMES.append(tick);allowed=True
   if allowed:
    try:
     rows,meta=_crypto_history.fetch_m5(symbol,now)
    except _crypto_history.CryptoHistoryError as error:
     rows=[]
     meta={"symbol":symbol,"provider":"Bitstamp","checked_at":now.isoformat(),
           "state":"DEGRADED","reason":str(error),"realtime_verified":False}
    with history_connection() as c:
     _crypto_history.store_check(c,symbol,meta,rows,postgres=postgres_enabled())
    prior=meta
  with history_connection() as c:
   rows=c.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Bitstamp' AND symbol="+mark+" ORDER BY time DESC LIMIT 1000",(symbol,)).fetchall()
  return rows,prior
 except (_crypto_history.CryptoHistoryError,ValueError):
  raise
 except Exception:
  raise _crypto_history.CryptoHistoryError("crypto_source_unavailable") from None

def crypto_startup_probe():
 """One bounded public OHLC probe; never sends orders or trades."""
 try:
  rows,meta=bitstamp_native_candles("BITSTAMP:BTCUSD")
  print("crypto_history symbol=BITSTAMP:BTCUSD provider=Bitstamp state="+str(meta.get("state","UNKNOWN"))+" candles="+str(len(rows))+" reason="+str(meta.get("reason","unknown")),flush=True)
 except _crypto_history.CryptoHistoryError as error:
  print("crypto_history symbol=BITSTAMP:BTCUSD provider=Bitstamp state=DEGRADED reason="+str(error),flush=True)

def analyze_instant_native(symbol,mode):
 """V2 read-only market analysis. Never uses TradingView trade alerts."""
 now=datetime.now(timezone.utc)
 instrument=_instruments.describe(symbol)
 asset=instrument["asset_class"]
 provider=None
 rows=[]
 check_meta={}
 with history_connection() as db:tv_rows,tv_meta=_tradingview_candles.read(db,symbol,postgres_enabled())
 # A newly connected chart must not suppress an already verified venue feed.
 # Keep complete histories separate; never splice different candle sources.
 if _tradingview_candles.fresh(tv_meta,now) and len(tv_rows)<300 and symbol in _connected_market.SUPPORTED_CRYPTO:
  try:
   venue_rows,venue_meta=bitstamp_native_candles(symbol,now)
   stamp=datetime.fromisoformat(str(venue_meta.get('last_candle','')).replace('Z','+00:00'))
   if (len(venue_rows)>=300 and venue_meta.get('symbol')==symbol and venue_meta.get('provider')=='Bitstamp'
       and venue_meta.get('state')=='CONNECTED' and 300<=(now-stamp).total_seconds()<=630):
    with history_connection() as db:news=_news.snapshot(db,now)
    out=_instant_engine.evaluate(symbol,venue_rows,mode=mode,asset_class=asset,provider='Bitstamp',tick_size=.01,
          now=now,news=news,source_identity_verified=True,realtime_verified=False)
    out.update(instrument=instrument,generated_at=now.isoformat(),scalp_ready=out['status']=='READY' and mode=='scalp',
               source_notice='تحليل سجل Bitstamp المستقل أثناء تراكم سجل شارت TradingView',
               chart_candles_received=len(tv_rows))
    return out
  except (_crypto_history.CryptoHistoryError,ValueError,TypeError):pass
 if _tradingview_candles.fresh(tv_meta,now):
  with history_connection() as db:news=_news.snapshot(db,now)
  out=_instant_engine.evaluate(symbol,tv_rows,mode=mode,asset_class=asset,
       provider=_tradingview_candles.PROVIDER,tick_size=tv_meta['tick_size'],
       now=now,news=news,source_identity_verified=True,realtime_verified=False)
  out.update(instrument=instrument,generated_at=now.isoformat(),source_provenance=tv_meta,
             scalp_ready=out['status']=='READY' and mode=='scalp',
             source_notice='تحديث شموع شارت TradingView؛ ليس تنفيذاً ولا بث أسعار لكل تغير')
  return out
 if asset=="futures":
  with history_connection() as db:rows,check_meta=_live_candle_adapter.read(db,symbol,postgres_enabled())
  if rows:
   provider=check_meta.get('provider')
   out=_instant_engine.evaluate(symbol,rows,mode=mode,asset_class=asset,provider=provider,
      tick_size=check_meta.get('tick_size',.01),now=now,source_identity_verified=True,realtime_verified=False)
   # A matching Yahoo root is still a different continuous-series source, and
   # Yahoo delay/roll conventions are not verified TradingView live pricing.
   if out['status']=='READY':out['status']='CONDITIONAL'
   out['reference_only']=True
   out['source_provenance']=check_meta
   out['source_notice']='تحليل مرجعي لشموع المصدر الاحتياطي؛ لا يُرسل كتوصية لايف'
  else:
   out=_instant_engine.unavailable("FUTURES_SOURCE_NOT_CONNECTED",symbol,mode,asset_class="futures")
 elif asset=="crypto" and symbol.startswith("BITSTAMP:"):
  provider="Bitstamp"
  try:
   rows,check_meta=bitstamp_native_candles(symbol,now)
  except _crypto_history.CryptoHistoryError as error:
   out=_instant_engine.unavailable("CRYPTO_PROVIDER_UNAVAILABLE",symbol,mode,provider,error=str(error))
  else:
   out=None
 elif asset=="forex" and symbol.startswith("OANDA:"):
  ticker=symbol.split(":",1)[1]
  pair=ticker[:3]+"/"+ticker[3:]
  provider="Twelve Data"
  try:
   with history_connection() as db:
    mark="%s" if postgres_enabled() else "?"
    raw=db.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+mark+" ORDER BY time DESC LIMIT 1000",(pair,)).fetchall()
    prev=db.execute("SELECT payload FROM market_history_checks WHERE symbol="+mark,(pair,)).fetchone()
   rows=raw
   check_meta=json.loads(prev[0]) if prev else {}
   out=None
  except Exception:
   out=_instant_engine.unavailable("FOREX_STORAGE_UNAVAILABLE",symbol,mode,provider)
 else:
  out=_instant_engine.unavailable("PROVIDER_NOT_MATCHED",symbol,mode,None,asset_class=asset)
 if out is None:
  try:
   with history_connection() as db:news=_news.snapshot(db,now)
  except Exception:news=None
  # Provider identity checks rely on previously authenticated ingestion; not mere UI symbol names.
  verified=(provider=="Bitstamp" and check_meta.get("provider")=="Bitstamp"
            and check_meta.get("symbol")==symbol and check_meta.get("state")=="CONNECTED") or (
            provider=="Twelve Data" and check_meta.get("symbol")==pair
            and check_meta.get("interval")=="5min" and check_meta.get("adapter_version") and check_meta.get("state")=="CONNECTED")
  tick_size=0.01 if asset=="crypto" else (0.001 if ticker.endswith("JPY") else 0.00001)
  out=_instant_engine.evaluate(symbol,rows,mode=mode,asset_class=asset,provider=provider,
           tick_size=tick_size,now=now,news=news,source_identity_verified=bool(verified))
  if check_meta.get('reference_only'):
   out['reference_only']=True
   out['source_provenance']=check_meta
 out["instrument"]=instrument
 out["generated_at"]=now.isoformat()
 out["news_integration"]="VERIFIED_EVENT_TIMES_ONLY"
 out["scalp_ready"]=out["status"]=="READY" and mode=="scalp"
 return out

def deliver_native_companion(plan,trade_chat):
 """One separate technical card, after the durable trade acceptance receipt."""
 if plan.get("status")!="READY" or not _connected_market.gate(plan)["open"]:return
 chat=telegram_destination("analysis")
 if notifications_muted(chat):return
 with history_connection() as c:
  if plan.get("symbol") not in owner_watchlist(c):return
  key=_instant_telegram.claim_companion(c,plan,trade_chat,chat,postgres_enabled())
 if not key:return
 try:
  result=_instant_telegram.send(plan,os.getenv("TELEGRAM_BOT_TOKEN","").strip(),chat,
       topic_id=telegram_topic_id("analysis"),category="analysis")
 except Exception:result="uncertain"
 with history_connection() as c:_instant_telegram.finish(c,key,result,postgres_enabled())

def trigger_instant_telegram(plan):
 """Start a private, promptly dispatched native research alert if it is NEW.

 Does not block Analyze while Telegram's network responds. DB claim guarantees
 parallel browser refreshes cannot dispatch the same signal twice.
 """
 if plan.get('status')!='READY' or not _instant_telegram.eligible(plan):
  return {"status":"not_eligible"}
 with history_connection() as c:
  if plan.get("symbol") not in owner_watchlist(c):return {"status":"not_tracked"}
 market=_connected_market.gate(plan)
 if not market["open"]:
  return {"status":"market_closed","reason":market["reason"]}
 if os.getenv("BIGBEN_NATIVE_TELEGRAM_ENABLED","1")!="1":
  return {"status":"disabled"}
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=telegram_destination("trade" if plan.get("status")=="READY" else "analysis")
 if notifications_muted(chat):return {'status':'disabled'}
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):
  return {"status":"not_configured"}
 try:
  with history_connection() as c:
   key=_instant_telegram.claim(c,plan,chat,postgres_enabled())
 except Exception:
  return {"status":"storage_unavailable"}
 if not key:
  if plan.get("status")=="READY":
   threading.Thread(target=deliver_native_companion,args=(plan,chat),daemon=True).start()
  return {"status":"duplicate"}
 def deliver():
  try:
   result=(_instant_telegram.send(plan,token,chat,topic_id=telegram_topic_id("trade" if plan.get("status")=="READY" else "analysis"))
           if _connected_market.gate(plan)["open"] else "failed")
  except Exception:result="uncertain"
  try:
   with history_connection() as c:
    _instant_telegram.finish(c,key,result,postgres_enabled())
    if result=="sent" and plan.get("status")=="READY":
     _native_trade_journal.store(c,plan,postgres_enabled())
   print("native_telegram symbol="+plan["symbol"]+" status="+result,flush=True)
   if result=="sent":deliver_native_companion(plan,chat)
  except Exception:print("native_telegram status=receipt_storage_unavailable",flush=True)
 try:
  threading.Thread(target=deliver,name="native-telegram",daemon=True).start()
 except RuntimeError:
  try:
   with history_connection() as c:_instant_telegram.finish(c,key,"failed",postgres_enabled())
  except Exception:pass
  return {"status":"failed"}
 return {"status":"sending","fingerprint":key}

def stored_pattern_audits(now):
 """Read only stored, watchlist-scoped, unmixed candle histories."""
 audits=[]
 with history_connection() as db:
  m='%s' if postgres_enabled() else '?'
  for symbol in sorted(owner_watchlist(db)):
   rows=db.execute('SELECT provider,time,open,high,low,close FROM market_candles WHERE symbol='+m+' ORDER BY time DESC LIMIT 1500',(symbol,)).fetchall()
   grouped={}
   for provider,*bar in rows:grouped.setdefault(provider,[]).append(bar)
   candidates=[_pattern_audit.inspect(symbol,provider,bars,now) for provider,bars in grouped.items()]
   if re.fullmatch(r'OANDA:[A-Z]{6}',symbol):
    base=symbol.split(':',1)[1]
    pair=base[:3]+'/'+base[3:]
    bars=db.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+m+" ORDER BY time DESC LIMIT 1500",(pair,)).fetchall()
    if bars:candidates.append(_pattern_audit.inspect(symbol,'Twelve Data',bars,now))
   chosen=max(candidates,key=lambda a:(a['fresh'],a['candles']>=30,a['source_time'] or '',a['candles'])) if candidates else _pattern_audit.inspect(symbol,'لم يصل سجل شموع',[],now)
   audits.append(chosen)
 return audits

def analyze_native_chart(symbol,mode):
 """Standalone platform decisions from provider candles. Never load TV webhook trades."""
 now=datetime.now(timezone.utc)
 instrument=_instruments.describe(symbol)
 response={"symbol":symbol,"instrument":instrument,"generated_at":now.isoformat(),
           "requested_mode":mode,"strategy_version":"native-chart-v1","source":"Twelve Data M5 OHLC",
           "analysis_origin":"platform_native","uses_tradingview_signals":False,
           "decision":"WAIT","fresh":False,"source_time":None,
           "reasons":[],"checks":[],"news":[],"news_scenarios":[],"agent_tasks":[],
           "smt_research":{"state":"NOT_MEASURED"},"ai":{"state":"not_requested"},
           "full_trade":None,"scalp":None,"selected_trade":None}
 ticker=symbol.split(":",1)[-1]
 provider_pair=ticker[:3]+"/"+ticker[3:] if len(ticker)==6 and instrument["asset_class"]=="forex" else None
 if instrument["asset_class"]=="crypto" and symbol.startswith("BITSTAMP:"):
  response["source"]="Bitstamp spot M5 OHLC"
  try:
   rows,meta=bitstamp_native_candles(symbol,now)
   setup=_native_chart_analysis.evaluate(rows,mode=mode,now=now)
  except _crypto_history.CryptoHistoryError as error:
   meta={"reason":str(error),"state":"DEGRADED"}
   setup={"state":"CRYPTO_OHLC_UNAVAILABLE","candidate":None,"reason":str(error)}
  response["independent_setup"]=setup
  response["source_time"]=setup.get("source_time")
  response["fresh"]=setup.get("state") not in ("STALE_OR_UNCLOSED","INSUFFICIENT_DATA","MISSING_RECENT_M5_BARS","INVALID_CANDLE","DATA_CHECK_FAILED","CRYPTO_OHLC_UNAVAILABLE")
  response["decision_reason_code"]=setup.get("state","WAIT")
  response["mode_timeframes"]=["M5","M15","H1"] if mode=="scalp" else ["H1","H4"]
  response["analysis_timeframes"]=setup.get("timeframes",{})
  response["mode_note"]="السعر من تداول Spot في Bitstamp حصراً، وليس BTC Futures أو CFD؛ تحليل بحثي لا ينفذ أوامر."
  response["reasons"]=["مصدر شموع البيتكوين: Bitstamp Spot M5 من المنصة وليس TradingView.",
                       "حالة البيانات: "+str(meta.get("state","UNKNOWN"))+" / "+str(meta.get("reason","not_checked")),
                       "حالة التحليل: "+str(setup.get("state","UNKNOWN"))]
  candidate=setup.get("candidate") if response["fresh"] else None
  if candidate:
   response["decision"]=candidate["event"]
   response["selected_trade"]=candidate
   response["full_trade"]=candidate
   if mode=="scalp":response["scalp"]=candidate
   response["reasons"].append("فرصة بحثية غير مؤكدة؛ لا يوجد أمر تداول أو ضمان نتيجة.")
  response["agent_tasks"]=[{"role":"market_data","output":"Bitstamp Spot OHLC؛ "+str(meta.get("state"))},
                          {"role":"signal_quality","output":"Native "+response["decision"]},
                          {"role":"risk","output":"مستويات بحثية دون تنفيذ"}]
  return response
 if provider_pair not in _history.FOREX:
  response.update(decision_reason_code="SOURCE_NOT_SUPPORTED",mode_note="يتطلب هذا السوق مزود شموع OHLC مرخصاً؛ لن نستخدم CFD بديلاً عن عقود Futures.",
                  independent_setup={"state":"SOURCE_NOT_VERIFIED","candidate":None})
  response["reasons"]=["لم يثبت مصدر OHLC لهذه الأداة. تحليل Pine غير مستخدم."]
  return response
 # One bounded on-demand provider request per symbol/15min; global credit guard.
 try:
  with history_connection() as db:
   prev=db.execute("SELECT payload FROM market_history_checks WHERE symbol="+("%s" if postgres_enabled() else "?"),(provider_pair,)).fetchone()
  last=json.loads(prev[0]).get("checked_at") if prev else None
  checked=datetime.fromisoformat(last.replace("Z","+00:00")) if last else None
  fetch_due=checked is None or (now-checked).total_seconds()>=900
  if fetch_due and twelve_data_key():
   allowed=False
   with NATIVE_FETCH_LOCK:
    tick=time.monotonic()
    NATIVE_FETCH_TIMES[:]=[v for v in NATIVE_FETCH_TIMES if tick-v<3600]
    if len(NATIVE_FETCH_TIMES)<20 and (not NATIVE_FETCH_TIMES or tick-NATIVE_FETCH_TIMES[-1]>=5):
     NATIVE_FETCH_TIMES.append(tick);allowed=True
   if allowed:
    try:
     rows,meta=_history.fetch_m5(provider_pair,twelve_data_key(),now)
     meta.update(state="CONNECTED",reason="native_on_demand_closed_m5")
    except _history.HistoryError as error:
     rows=[]
     meta={"symbol":provider_pair,"state":"DEGRADED","reason":str(error),
           "checked_at":now.isoformat(),"adapter_version":_history.ADAPTER_VERSION}
    with history_connection() as db:_history.store_check(db,provider_pair,meta,rows,postgres=postgres_enabled())
  with history_connection() as db:
   marker="%s" if postgres_enabled() else "?"
   candles=db.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker+" ORDER BY time DESC LIMIT 1000",(provider_pair,)).fetchall()
  setup=_native_chart_analysis.evaluate(candles,mode=mode,now=now)
 except Exception:
  setup={"state":"DATA_CHECK_FAILED","candidate":None,"reason":"storage_or_provider_error"}
 response["independent_setup"]=setup
 candidate=setup.get("candidate")
 response["source_time"]=setup.get("source_time")
 response["fresh"]=setup.get("state") not in ("STALE_OR_UNCLOSED","INSUFFICIENT_DATA","DATA_CHECK_FAILED","MISSING_RECENT_M5_BARS")
 response["decision_reason_code"]=setup.get("state","NO_SETUP")
 response["mode_note"]="تحليل مستقل لشموع السوق؛ الفرصة المقترحة غير مؤكدة، ولا تعني تحقق التنفيذ أو الربح."
 response["reasons"]=["المصدر: Twelve Data M5 من المنصة، وليس إشارات TradingView.",
                      "نتيجة محرك التحليل: "+str(setup.get("state","UNKNOWN")),
                      "الأسعار ليست مثبتة كتغذية لحظية مرخصة، والسبريد والعمولة والانزلاق غير محسوبة."]
 response["mode_timeframes"]=["M5","M15","H1"] if mode=="scalp" else ["H1","H4"]
 response["analysis_timeframes"]=setup.get("timeframes",{})
 if candidate:
  response["decision"]=candidate["event"]
  response["selected_trade"]=candidate
  response["full_trade"]=candidate
  if mode=="scalp":response["scalp"]=candidate
  response["reasons"].append("نموذج "+candidate["pattern"]+" مكتمل على شمعة مغلقة؛ حالة الفرصة: بحثية، وليست إشارة تنفيذ.")
 response["agent_tasks"]=[{"role":"market_data","output":"مصدر شموع OHLC مستقل؛ "+str(setup.get("state"))},
                          {"role":"signal_quality","output":"قرار المحرك: "+response["decision"]+"؛ لا إشارات Pine"},
                          {"role":"risk","output":"مستويات بحثية وحساب RR؛ لا تنفيذ صفقات"}]
 return response

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

def process_bbb_event(event):
 key="bbb-job:"+event["event_id"];now=datetime.now(timezone.utc);m="%s" if postgres_enabled() else "?"
 with history_connection() as c:
  claimed=c.execute("INSERT INTO telegram_bot_receipts(id,status,created_at) VALUES ("+m+",'processing',"+m+") ON CONFLICT(id) DO NOTHING",(key,now.isoformat())).rowcount==1
  if not claimed:
   claimed=c.execute("UPDATE telegram_bot_receipts SET created_at="+m+" WHERE id="+m+" AND status='processing' AND created_at<"+m,(now.isoformat(),key,(now-timedelta(seconds=120)).isoformat())).rowcount==1
 if not claimed:return
 state="تعذر التحليل"
 try:
  sent=datetime.fromisoformat(event["time"].replace("Z","+00:00"))
  if not 0<=(now-sent).total_seconds()<=180:state="محفوظ؛ انتهت حداثة التنبيه"
  else:
   plan=analyze_instant_native(event["symbol"],"scalp")
   if not _connected_market.gate(plan)["open"]:state="محفوظ؛ مصدر الأسعار أو الجلسة غير موثق"
   else:
    outcome=trigger_instant_telegram(plan)
    state="اكتملت المعالجة؛ "+{"sending":"حجز الإرسال","duplicate":"حجب التكرار","not_eligible":"لم يتأكد دخول قابل للإرسال","not_configured":"التسليم غير مهيأ","market_closed":"السوق مغلق"}.get(outcome.get("status"),"حالة التسليم تحتاج مراجعة")
 except Exception:state="تعذر التحليل؛ التنبيه محفوظ للمراجعة"
 with history_connection() as c:c.execute("UPDATE telegram_bot_receipts SET status="+m+" WHERE id="+m,(state,key))
 print("تنبيه_BBB الحالة="+state,flush=True)

def process_chart_candle(symbol):
 """Immediate chart-driven evaluation; sender retains durable setup dedup."""
 try:
  with history_connection() as db:
   if symbol not in owner_watchlist(db):return
  for mode in ('scalp','swing'):
   plan=analyze_instant_native(symbol,mode)
   result=trigger_instant_telegram(plan)
   print('معالجة_شمعة_الشارت الرمز='+symbol+' النمط='+mode+' الحالة='+str(result.get('status','غير متاحة'))+
         ' المصدر='+str(plan.get('provider') or 'غير متاح')+' سبب_التحليل='+str(plan.get('reason_code') or plan.get('status_ar') or 'تقييم فني')+
         ' شموع_الشارت='+str(plan.get('chart_candles_received','غير محدد')),flush=True)
 except Exception:print('معالجة_شمعة_الشارت الحالة=تعذر_الفحص',flush=True)

def bbb_recovery_worker():
 while True:
  try:
   with history_connection() as c:
    rows=c.execute("SELECT e.payload FROM events e LEFT JOIN telegram_bot_receipts r ON r.id='bbb-job:' || e.id WHERE e.id LIKE 'bbb:%' AND (r.id IS NULL OR r.status='processing') ORDER BY e.time LIMIT 100").fetchall()
   for row in rows:process_bbb_event(json.loads(row[0]))
  except Exception:print("استرجاع_التنبيهات الحالة=تعذر_الفحص",flush=True)
  time.sleep(15)

def run_signal_analysis(symbol):
 # This runs in a per-symbol worker, never in the webhook HTTP request.
 if not SIGNAL_ANALYSIS_SLOTS.acquire(timeout=10):
  print("signal_analysis deferred=capacity",flush=True);return False
 try:
  result=analyze_instrument(symbol,True)
  print("signal_analysis state=completed decision="+result["decision"]+" ai_state="+result["ai"]["state"],flush=True)
  return True
 except Exception:
  print("signal_analysis state=failed",flush=True);return False
 finally:SIGNAL_ANALYSIS_SLOTS.release()

def process_signal_event(symbol,d):
 """Process one real TradingView signal without broker execution."""
 if os.getenv("BIGBEN_ANALYSIS_KILL_SWITCH","0") == "1":
  print("signal_analysis state=blocked reason=kill_switch",flush=True);return
 if d.get("event") not in ("BUY","SELL"):return
 for attempt in range(3):
  try:
   status=telegram_notify(d)
   with history_connection() as c:_destinations.receipt(c,d["event_id"],"telegram",status,postgres_enabled())
   print("telegram_delivery="+status+" attempt="+str(attempt+1),flush=True)
   break
  except Exception:
   if attempt==2: print("telegram_delivery=failed retries=3",flush=True)
   else: time.sleep(0.5*(2**attempt))
 whatsapp_status=whatsapp_notify(d)
 if whatsapp_status!="disabled":
  try:
   with history_connection() as c:_destinations.receipt(c,d["event_id"],"whatsapp",whatsapp_status,postgres_enabled())
  except Exception:print("whatsapp_receipt storage_unavailable",flush=True)
 if os.getenv("BIGBEN_SIGNAL_ANALYSIS_ENABLED","1")=="1":
  for attempt in range(3):
   try:
    if not run_signal_analysis(symbol):raise RuntimeError("analysis_not_completed")
    break
   except Exception:
    if attempt==2:
     print("signal_analysis state=failed retries=3 symbol="+symbol,flush=True)
     raise RuntimeError("analysis_retries_exhausted") from None
    else:time.sleep(0.5*(2**attempt))

SIGNAL_PIPELINE=_event_pipeline.SymbolPipeline(process_signal_event,max_queue_per_symbol=int(os.getenv("BIGBEN_SYMBOL_QUEUE_SIZE","100")))

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
  deliveries=_destinations.recent(c)
 telegram_deliveries=[d for d in deliveries if d["channel"]=="telegram"]
 last_telegram=telegram_deliveries[0] if telegram_deliveries else None
 telegram_recent=False
 if last_telegram:
  try:
   delivery_age=(now-datetime.fromisoformat(last_telegram["created_at"].replace("Z","+00:00"))).total_seconds()
   telegram_recent=last_telegram["status"]=="sent" and 0<=delivery_age<86400
  except (ValueError,TypeError,AttributeError):
   telegram_recent=False
 freshness=event_freshness(rows,now)
 return {"checked_at":now.isoformat(),"mode":"live_analysis_alerts_only","broker_execution":"disabled","tradingview":{"symbols":list(tracked.values()),"fresh_symbols":sum(s["fresh"] for s in tracked.values()),"expected_symbols":len(set(_desk.SYMBOLS.values()) | set(tracked)),"observed_symbols":len(tracked),**freshness},
  "market_data":coverage,"news":feeds["sources"],"ai":_ai_provider.status(),"storage":storage_kind(),
  "agents":{"signal_analysis_enabled":os.getenv("BIGBEN_SIGNAL_ANALYSIS_ENABLED","1")=="1","deterministic_roles":9,"max_concurrent":2,"mode":"alerts_only","runtime_mode":"live_analysis","resident_watchdog":os.getenv("BIGBEN_AGENT_WATCHDOG_ENABLED","1")=="1","learning":"evidence_only_no_automatic_code_or_strategy_edits"},
  "telegram":{"configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),"delivery_verified_now":telegram_recent,"last_delivery":last_telegram},
  "pipeline":SIGNAL_PIPELINE.snapshot(),
  "broker_demo":_demo.configuration_status(),
  "whatsapp":_whatsapp.status()}

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

def fast_history_worker():
 """Bounded freshness refresh for three Forex symbols only; not a licensed realtime stream."""
 try:interval=max(900,min(3600,int(os.getenv("BIGBEN_FAST_M5_REFRESH_SECONDS","900"))))
 except ValueError:interval=900
 while True:
  time.sleep(interval)
  try:refresh_market_history()
  except Exception:print("market_history fast_refresh=failed",flush=True)

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
def signal_ttl_seconds(data):
 timeframe=str(data.get("timeframe") or "5").strip().upper()
 configured=os.getenv("BIGBEN_SIGNAL_TTL_SECONDS","").strip()
 if configured.isdigit() and int(configured)>0:return int(configured)
 return {"1":300,"3":600,"5":900,"15":3600,"30":7200,"60":14400,"1H":14400,"4H":86400,"D":172800}.get(timeframe,3600)
def signal_lifecycle(data, stamp, now=None):
 now=now or datetime.now(timezone.utc)
 try:
  dt=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
  if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
  age=max(0,int((now-dt).total_seconds()));ttl=signal_ttl_seconds(data)
 except (TypeError,ValueError,AttributeError):
  return {"status":"UNKNOWN","fresh":False,"age_seconds":None,"ttl_seconds":None,"expires_at":None}
 expires=(dt+timedelta(seconds=ttl)).isoformat()
 active=0<=age<=ttl
 return {"status":"ACTIVE" if active else "EXPIRED","fresh":active,"age_seconds":age,"ttl_seconds":ttl,"expires_at":expires}
def event_freshness(rows=None, now=None):
 now=now or datetime.now(timezone.utc)
 parsed=[]
 for symbol,kind,stamp,payload in rows if rows is not None else list_events(2000,"all"):
  try:
   data=json.loads(payload);dt=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
   age=(now-dt).total_seconds()
   parsed.append((dt,{"symbol":symbol,"event":kind,"source_time":stamp,"received_at":data.get("received_at"),"event_id":data.get("event_id"),"age_seconds":max(0,int(age)),"fresh":0<=age<720}))
  except (ValueError,TypeError,AttributeError):continue
 parsed.sort(key=lambda item:item[0],reverse=True)
 def pick(events):return next((item[1] for item in parsed if item[1]["event"] in events),None)
 latest=parsed[0][1] if parsed else None
 heartbeat=pick({"HEARTBEAT"});trade=pick({"BUY","SELL"})
 return {"recent_event_verified":bool(latest and latest["fresh"]),"heartbeat_recent":bool(heartbeat and heartbeat["fresh"]),"last_event":latest,"last_heartbeat":heartbeat,"last_trade":trade,"live_feed_verified":False,"note":"TradingView event freshness is verified separately from continuous market-feed availability"}

def save_event(d):
 received_at=datetime.now(timezone.utc).isoformat()
 stored={**d,"received_at":received_at}
 vals=(d["event_id"],d["symbol"],d["event"],d["time"],json.dumps(stored),received_at)
 with history_connection() as c:
  if postgres_enabled():
   duplicate=c.execute("INSERT INTO events (id,symbol,event,time,payload,received_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",vals).rowcount==0
  else:
   duplicate=c.execute("INSERT OR IGNORE INTO events (id,symbol,event,time,payload,received_at) VALUES (?,?,?,?,?,?)",vals).rowcount==0
  if not duplicate:
   # Called only after the existing webhook authentication and validation.
   # Same transaction: retries never inflate discovery or enable a price feed.
   try:instrument=_instruments.describe(d["symbol"])
   except ValueError:instrument=None  # Preserve legacy accepted identifiers.
   if instrument and _tradingview_dynamic_sync.SYMBOL_RE.fullmatch(instrument["symbol"]):
    _tradingview_dynamic_sync.record_symbol(c,
        {"symbol":instrument["symbol"],"asset_class":instrument["asset_class"]},
        authenticated=True,postgres=postgres_enabled())
  return duplicate
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
 lines=["📊 BIG BEN AI PRO",side+" | "+kind,"الاسم: "+instrument["name"],"الرمز: "+instrument["symbol"],"الفريم: "+str(d.get("timeframe","5"))+" دقائق | مسقط: "+stamp,
  "", "① الصفقة الكاملة — الهدف الأصلي", "الدخول Entry: "+str(full["entry"]),"الوقف SL: "+str(full["sl"]),"الهدف TP: "+str(full["tp"])+" | RR: "+str(round(full["rr"],4)),
  "", "② خيار السكالب — هدف حسابي بديل", "الدخول Entry: "+str(scalp["entry"]),"الوقف SL: "+str(scalp["sl"]),"الهدف TP: "+str(scalp["tp"])+" | RR: "+str(round(scalp["rr"],4))]
 checks=_desk.condition_checks(d.get("analysis",{}) if isinstance(d.get("analysis"),dict) else {})
 confirmed=[c["label"] for c in checks if c["state"]=="PASSED"]
 lines.extend(["", "أدلة المؤشر: "+("؛ ".join(confirmed[:5]) if confirmed else "تفاصيل الشروط غير مستلمة؛ لا تُفترض متحققة"),
  "النسخة: "+str(d.get("strategy_version","غير متاحة")), "المخطط: "+instrument["chart_url"],
  "", "اختر أحد الخيارين؛ ليس السكالب إشارة مستقلة.","التكاليف وحجم التيك غير مؤكدين. تحليل فقط — لا يوجد تنفيذ أوامر.","⚠️ تنبيه: التحليل قد يفشل أو يتأخر. دخولك ومسؤوليتك وحدك؛ لا تعتبر الرسالة توصية مالية."])
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

def telegram_destination(kind=None):
 override=os.getenv("BIGBEN_TELEGRAM_"+str(kind or "").upper()+"_CHAT_ID","").strip()
 if override and re.fullmatch(r"-?[0-9]{5,20}",override):return override
 try:
  with history_connection() as c:chat=_destinations.read(c)["telegram_chat_id"]
 except Exception:return ""
 return chat or os.getenv("TELEGRAM_CHAT_ID","").strip()

def telegram_topic_id(kind):
 raw=os.getenv("BIGBEN_TELEGRAM_"+str(kind).upper()+"_THREAD_ID","").strip()
 return int(raw) if raw.isdigit() and int(raw)>0 else None

def telegram_notify(d):
 # Legacy events must use the same native market/source/dedup pipeline as the new bridge.
 if d.get("event") not in ("BUY","SELL"):return "skipped"
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip();chat=telegram_destination()
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):return "not_configured"
 try:
  plan=analyze_instant_native(_instruments.normalize(d["symbol"]),"scalp")
  if not _connected_market.gate(plan)["open"]:return "market_closed"
  return trigger_instant_telegram(plan).get("status","not_eligible")
 except Exception:return "source_unverified"
def audit_telegram_connection():
 """Read-only Telegram bot/chat checks; no test messages, tokens or chat ids in logs."""
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=telegram_destination()
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):
  print("telegram_audit state=NOT_CONFIGURED",flush=True);return
 # HTTP status only, never log URL or Telegram API body containing private fields.
 for method,body in (("getMe",None),("getChat",{"chat_id":chat})):
  uri="https://api.telegram.org/bot"+token+"/"+method
  request=urllib.request.Request(uri,
    data=json.dumps(body).encode() if body is not None else None,
    headers={"Content-Type":"application/json"} if body else {})
  try:
   with urllib.request.urlopen(request,timeout=7) as response:
    raw=response.read(2048)
    verified=response.status==200 and json.loads(raw).get("ok") is True
   print("telegram_audit check="+method+" state="+("OK" if verified else "FAILED_RESPONSE"),flush=True)
  except urllib.error.HTTPError as error:
   print("telegram_audit check="+method+" state=HTTP_"+str(error.code),flush=True)
  except (OSError,ValueError,TimeoutError):
   print("telegram_audit check="+method+" state=CONNECTION_ERROR",flush=True)

def notifications_muted(chat):
 try:
  with history_connection() as c:return _telegram_interactive.muted(c,chat,postgres_enabled())
 except Exception:return True

def send_telegram_message(message,category="analysis",*,destination=None):
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=telegram_destination(category) if destination is None else destination
 if notifications_muted(chat):return 'not_configured'
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):
  return "not_configured"
 data={"chat_id":chat,"text":message}
 topic=telegram_topic_id(category)
 if topic:data["message_thread_id"]=topic
 payload=json.dumps(data,ensure_ascii=False).encode()
 req=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=payload,headers={"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=8) as response:
   return "sent" if response.status==200 else "failed"
 except (urllib.error.URLError,TimeoutError,ValueError):
  return "failed"
def owner_watchlist(db):
 """TradingView snapshot/authorized new alerts only; no old UI preference union."""
 watched=[]
 try:
  configured=json.loads(os.getenv("BIGBEN_TRACKED_SYMBOLS_JSON","[]"))
  if isinstance(configured,list):watched.extend(configured[:1000])
 except (ValueError,TypeError):pass
 return _tv_watchlist.members(db,watched,postgres_enabled())

def owner_connected_assets(db,now=None):
 now=now or datetime.now(timezone.utc)
 watched=owner_watchlist(db)
 current={a['symbol']:a for a in _connected_market.connected(db,now,postgres_enabled()) if a['symbol'] in watched and a.get('connected') is True and a.get('fresh') is True}
 for symbol in watched:
  rows,meta=_tradingview_candles.read(db,symbol,postgres_enabled())
  if _tradingview_candles.fresh(meta,now):
   asset=_instruments.describe(symbol)['asset_class']
   gate=_connected_market.gate(dict(symbol=symbol,provider=_tradingview_candles.PROVIDER,
              source_time=meta['last_candle'],source_provenance=meta,asset_class=asset),now)
   current[symbol]=dict(symbol=symbol,label=symbol,asset_class=asset,provider=_tradingview_candles.PROVIDER,
       connected=True,fresh=True,market_open=gate['open'],market_state=gate['reason'],
       latest_closed_candle=meta['last_candle'],history_ready=len(rows)>=300)
 return list(current.values())

def tracked_asset_catalog(db,connected=None):
 now=datetime.now(timezone.utc)
 if connected is None:connected=owner_connected_assets(db,now)
 watched=owner_watchlist(db)
 current={a['symbol']:a for a in connected if a['symbol'] in watched}
 result=[]
 for symbol in sorted(watched):
  info=_instruments.describe(symbol)
  row=dict(current.get(symbol) or {},symbol=symbol,label=symbol,asset_class=info['asset_class'])
  row.setdefault('connected',False);row.setdefault('fresh',False)
  row['actionable']=row['connected'] is True and row['fresh'] is True
  with_meta=_live_candle_adapter.read(db,symbol,postgres_enabled())[1]
  row['candle_adapter']=with_meta
  if not row['actionable']:
   row['market_state']=with_meta.get('reason','لا توجد تغذية مطابقة موثقة؛ الأصل محفوظ في قائمة TradingView')
  if info['asset_class']=='forex' and _connected_market.forex_weekly_closed(now):
   row['market_open']=False
   row['next_weekly_open']=_connected_market.next_forex_open(now)
   row['market_state']='السوق مغلق أسبوعياً؛ الافتتاح العام المتوقع بتوقيت عُمان: '+row['next_weekly_open']+'؛ يلزم تدفق شموع حديثة بعده'
  result.append(row)
 return result

def watchlist_diagnostics(db,now=None):
 """Per-symbol readiness, without probes, secret values, or invented prices."""
 current={a['symbol']:a for a in tracked_asset_catalog(db)}
 result=[]
 for symbol in sorted(owner_watchlist(db)):
  asset=_instruments.describe(symbol);row=current.get(symbol)
  fresh=bool(row and row.get('connected') and row.get('fresh'))
  if row:reason=row.get('market_state','حالة الجلسة غير مثبتة')
  elif asset['asset_class']=='futures':reason='لا يوجد مسار OHLC حي موثق لهذا العقد في المحرك الحالي؛ يلزم مصدر مطابق وصلاحية بيانات ومواصفات العقد.'
  elif symbol.startswith(('OANDA:','BITSTAMP:')):reason='لم يجتز المصدر تحقق الهوية والشموع الكافية والحداثة؛ لا تُغيّر حالته إلى متصل بمجرد وجود الرمز.'
  else:reason='لا يوجد محول شموع مستمر مطابق لهذا الرمز؛ Webhook ينقل حدثاً ولا يعوض سجل الأسعار.'
  result.append({'الرمز':symbol,'نوع_الأصل':asset['asset_class'],'متصل_حديث':fresh,'التشخيص':reason,
                 'مصدر_الشموع':(row.get('provider') or row.get('candle_adapter',{}).get('provider')) if row else None,'وقت_الشمعة':(row.get('latest_closed_candle') or row.get('candle_adapter',{}).get('last_candle')) if row else None})
 return result

def send_bot_payload(payload):
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 if not token:return "not_configured"
 data={k:v for k,v in payload.items() if k in ("chat_id","text","reply_markup")}
 request=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=json.dumps(data,ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(request,timeout=8) as response:return "sent" if response.status==200 else "uncertain"
 except Exception:return "uncertain"

def transport_proofs():
 with history_connection() as c:
  rows=c.execute("SELECT id,status FROM telegram_bot_receipts WHERE id LIKE 'transport:%' ORDER BY created_at DESC LIMIT 10").fetchall()
 return [{"معرف_الاختبار":r[0],"الإثبات":r[1]} for r in rows]

def send_transport_card(message):
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=os.getenv("BIGBEN_TELEGRAM_ALLOWED_USER_IDS","").split(",")[0].strip()
 if not token or not re.fullmatch(r"[0-9]{5,20}",chat):return {"الحالة":"غير مهيأ"}
 req=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=json.dumps({"chat_id":chat,"text":message},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=8) as response:
   raw=response.read(65537)
   if response.status!=200 or len(raw)>65536:raise ValueError()
   data=json.loads(raw)
   ident=(data.get("result") or {}).get("message_id")
   if data.get("ok") is not True or type(ident) is not int:raise ValueError()
  return {"الحالة":"قبله Telegram","معرف_الرسالة":ident}
 except Exception:return {"الحالة":"تسليم غير مؤكد؛ لا إعادة تلقائية"}

def execute_transport_fixture(test_id,case):
 key="transport:"+test_id+":"+case
 with history_connection() as c:
  claimed=_telegram_interactive.claim(c,key,postgres_enabled())
  if not claimed:
   m="%s" if postgres_enabled() else "?"
   row=c.execute("SELECT status FROM telegram_bot_receipts WHERE id="+m,(key,)).fetchone()
   return {"مكرر":True,"النتيجة_المحفوظة":row[0] if row else "غير متاحة"}
 event=_transport_fixture.payload(_bridge_validation.normalize)
 result={"نوع_الإثبات":"اختبار اصطناعي؛ ليس تنبيهاً صادراً من TradingView أو إثبات أسعار حية","التحقق_من_JSON":"ناجح","إضافة_صفقة_حقيقية":False,"الرسائل":[]}
 if case=="closed":
  stamp=datetime(2026,11,21,15,0,tzinfo=timezone.utc)
  gate=_connected_market.gate({"symbol":"OANDA:EURUSD","provider":"Twelve Data","status":"READY","source_time":(stamp-timedelta(minutes=5)).isoformat()},stamp)
  result["بوابة_السوق_المغلق"]="حجبت الإرسال" if not gate["open"] else "فشل الاختبار"
 else:
  for message in _transport_fixture.cards(event,_tradingview_dynamic_sync.trade_card,_tradingview_dynamic_sync.analysis_card):
   receipt=send_transport_card(message);result["الرسائل"].append(receipt)
   if "معرف_الرسالة" not in receipt:break
  result["فصل_الأخبار"]="رسالتان مستقلتان بلا محتوى أخبار"
 with history_connection() as c:
  m="%s" if postgres_enabled() else "?"
  c.execute("UPDATE telegram_bot_receipts SET status="+m+" WHERE id="+m,(json.dumps(result,ensure_ascii=False),key))
 print("اختبار_النقل الحالة="+("حجب_سوق_مغلق" if case=="closed" else "إيصالات_"+str(len([r for r in result["الرسائل"] if "معرف_الرسالة" in r]))),flush=True)
 return result

def run_local_transport_check():
 test_id=os.getenv("BIGBEN_TRANSPORT_SELF_TEST_ID","")
 secret=os.getenv("BIGBEN_TRANSPORT_TEST_TOKEN","")
 if not re.fullmatch(r"[A-Za-z0-9_-]{8,60}",test_id) or len(secret)<32:return
 time.sleep(2)
 try:
  port=int(os.getenv("PORT","10000"))
  for case in ("closed","open","open"):
   req=urllib.request.Request("http://127.0.0.1:"+str(port)+"/v1/tradingview/transport-test",data=json.dumps({"test_id":test_id,"case":case}).encode(),headers={"Content-Type":"application/json","X-BigBen-Test-Token":secret},method="POST")
   with urllib.request.urlopen(req,timeout=25) as response:result=json.loads(response.read(65536))
   print("اختبار_HTTP الحالة="+("منع_تكرار_مؤكد" if result.get("مكرر") else "فحص_سوق_مغلق" if case=="closed" else "فحص_نقل_اصطناعي"),flush=True)
   for item in result.get("الرسائل",[]):
    if "معرف_الرسالة" in item:print("إثبات_Telegram معرف_الرسالة="+str(item["معرف_الرسالة"]),flush=True)
  audit=os.getenv("BIGBEN_AUDIT_TOKEN","")
  if len(audit)>=32:
   req=urllib.request.Request("http://127.0.0.1:"+str(port)+"/v1/audit/state",headers={"X-BigBen-Audit-Token":audit})
   with urllib.request.urlopen(req,timeout=10) as response:state=json.loads(response.read(131072))
   print("فحص_الحالة المصادقة=ناجحة عدد_الأصول="+str(len(state.get("الأصول",[]))),flush=True)
 except Exception:print("اختبار_HTTP الحالة=تعذر_إكمال_الاختبار",flush=True)

def configure_interactive_bot():
 if os.getenv("BIGBEN_TELEGRAM_INTERACTIVE_ENABLED","0")!="1":return
 allowed=set(filter(None,os.getenv("BIGBEN_TELEGRAM_ALLOWED_USER_IDS","").replace(" ","").split(",")))
 result=_telegram_interactive.configure_webhook(os.getenv("TELEGRAM_BOT_TOKEN","").strip(),
     os.getenv("BIGBEN_TELEGRAM_WEBHOOK_SECRET",""),os.getenv("RENDER_EXTERNAL_URL","").strip(),allowed)
 print("تهيئة_البوت الحالة="+result,flush=True)
 try:
  with history_connection() as c:rows=watchlist_diagnostics(c)
  for row in rows:print('تشخيص_المتابعة الرمز='+row['الرمز']+' متصل_حديث='+('نعم' if row['متصل_حديث'] else 'لا')+' السبب='+str(row['التشخيص']),flush=True)
 except Exception:print('تشخيص_المتابعة الحالة=تعذر_فحص_السجل',flush=True)

def process_bot_update(update):
 try:
  allowed=set(filter(None,os.getenv("BIGBEN_TELEGRAM_ALLOWED_USER_IDS","").replace(" ","").split(",")))
  with history_connection() as c:
   assets=owner_connected_assets(c)
   catalog=tracked_asset_catalog(c,assets)
   diagnostics=watchlist_diagnostics(c)
   news=_news.snapshot(c);trades=_native_trade_journal.recent(c)
   reply=_telegram_interactive.handle(c,update,allowed_users=allowed,connected=lambda:assets,
       news=lambda:news,journal=lambda:trades,tracked=lambda:catalog,diagnostics=lambda:diagnostics,postgres=postgres_enabled())
  if not reply:return
  callback=reply.get("callback_id")
  if callback:
   token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
   try:
    req=urllib.request.Request("https://api.telegram.org/bot"+token+"/answerCallbackQuery",data=json.dumps({"callback_query_id":callback}).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=3):pass
   except Exception:pass
  massive_requested=reply.get("massive_request")
  if massive_requested:
   try:
    data=_massive_history.read(*massive_requested,{a["symbol"] for a in catalog},os.getenv("MASSIVE_FUTURES_API_KEY","").strip())
    closed=datetime.fromisoformat(data["last_closed_at"]).astimezone(_telegram_interactive.ZONE)
    reply["text"]="شموع تاريخية من Massive\n"+data["ticker"]+" · "+data["exchange"]+" · "+data["frame"]
    reply["text"]+="\nعدد الشموع: "+str(len(data["candles"]))+"\nآخر إغلاق بتوقيت عُمان: "+closed.strftime("%Y-%m-%d %H:%M")
   except _massive_history.HistoryError as error:
    reply["text"]=_massive_history.MESSAGES[str(error)]
  requested=reply.get("analysis_request")
  news_requested=reply.get("news_request")
  if news_requested:
   news_plan=analyze_instant_native(news_requested["symbol"],news_requested["mode"])
   reply["text"]=_telegram_interactive.important_news_analysis(news_requested["symbol"],news,news_plan)
  if requested:
   plan=analyze_instant_native(requested["symbol"],requested["mode"])
   reply["text"]=_telegram_interactive.signal_briefing(plan,_connected_market.gate(plan))
   if requested.get('read_only'):
    if _instant_telegram.eligible(plan):reply['text']=_instant_telegram.analysis_message(plan)
   elif plan.get("status")=="READY":
    dispatch=trigger_instant_telegram(plan)
    print("جلب_صفقة_البوت الرمز="+plan["symbol"]+" الحالة="+str(dispatch.get("status"))+" البصمة="+str(dispatch.get("fingerprint", "محفوظة_أو_غير_مؤهلة")),flush=True)
  delivery=send_bot_payload(reply)
  with history_connection() as c:
   m="%s" if postgres_enabled() else "?"
   c.execute("UPDATE telegram_bot_receipts SET status="+m+" WHERE id="+m,(delivery,"update:"+str(update["update_id"])))
 except PermissionError:print("البوت_التفاعلي حالة=حساب_غير_مصرح",flush=True)
 except Exception:print("البوت_التفاعلي حالة=تعذر_معالجة_الطلب",flush=True)

def deliver_trade_digest(now):
 """Send the prior Oman calendar-day summary once to the management destination."""
 local=now.astimezone(_native_trade_journal.ZONE)
 if local.hour==0 and local.minute<5:return
 chat=telegram_destination("management")
 if not re.fullmatch(r"-?[0-9]{5,20}",chat):return
 day=local.date()-timedelta(days=1)
 key="trade-digest:"+hashlib.sha256(chat.encode()).hexdigest()[:16]+":"+day.isoformat()
 postgres=postgres_enabled()
 m="%s" if postgres else "?"
 with history_connection() as c:
  if c.execute("SELECT 1 FROM telegram_bot_receipts WHERE id="+m,(key,)).fetchone():return
  summary=_native_trade_journal.daily_summary(c,day,postgres)
  if not summary or not _telegram_interactive.claim(c,key,postgres,now):return
 try:status=send_telegram_message(summary,category="management",destination=chat)
 except Exception:status="uncertain"
 if status=="failed":status="uncertain"
 with history_connection() as c:
  c.execute("UPDATE telegram_bot_receipts SET status="+m+" WHERE id="+m,(status,key))

def deliver_bot_news(snapshot,now):
 local=now.astimezone(_telegram_interactive.ZONE)
 try:hour=int(os.getenv("BIGBEN_NEWS_DIGEST_HOUR","5"))
 except ValueError:hour=5
 with history_connection() as c:
  chats=c.execute("SELECT chat FROM telegram_bot_state WHERE news_enabled=1").fetchall()
 allowed=set(filter(None,os.getenv("BIGBEN_TELEGRAM_ALLOWED_USER_IDS","").replace(" ","").split(",")))
 destination=""
 if local.hour>=max(0,min(23,hour)):
  destination=telegram_destination("news")
  if destination:
   key="digest:default:"+hashlib.sha256(destination.encode()).hexdigest()[:16]+":"+local.date().isoformat()
   with history_connection() as c:claimed=_telegram_interactive.claim(c,key,postgres_enabled(),now)
   if claimed:
    status=send_telegram_message(_telegram_interactive.digest(snapshot,now),category="news")
    with history_connection() as c:
     m="%s" if postgres_enabled() else "?"
     c.execute("UPDATE telegram_bot_receipts SET status="+m+" WHERE id="+m,(status,key))
 for (chat,) in chats:
  if chat not in allowed:continue
  if notifications_muted(chat):continue
  messages=[]
  if local.hour>=max(0,min(23,hour)) and chat!=destination:
   messages.append(("digest:"+chat+":"+local.date().isoformat(),_telegram_interactive.digest(snapshot,now)))
  for when,event in _telegram_interactive.today_events(snapshot,now):
   minutes=(when-now.astimezone(_telegram_interactive.ZONE)).total_seconds()/60
   if 0<=minutes<=10:
    key="news:"+chat+":"+str(event.get("id") or when.isoformat())
    messages.append((key,"🔔 تنبيه خبر اقتصادي\n"+str(event.get("title_ar") or "إصدار اقتصادي مجدول")+" — "+when.strftime("%H:%M")+" بتوقيت عُمان\nقد ترتفع التقلبات؛ لا يُستنتج اتجاه الصفقة من الموعد وحده."))
  for key,message in messages:
   with history_connection() as c:claimed=_telegram_interactive.claim(c,key,postgres_enabled(),now)
   if not claimed:continue
   status=send_bot_payload({"chat_id":chat,"text":message})
   with history_connection() as c:
    m="%s" if postgres_enabled() else "?"
    c.execute("UPDATE telegram_bot_receipts SET status="+m+" WHERE id="+m,(status,key))

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
  if urlsplit(self.path).path=="/api/instant/telegram/status":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   key=parse_qs(urlsplit(self.path).query).get("fingerprint",[""])[0]
   if not re.fullmatch(r"[0-9a-f]{64}",key):return self.reply(400,{"error":"invalid_fingerprint"})
   try:
    with history_connection() as c:
     mark="%s" if postgres_enabled() else "?"
     record=c.execute("SELECT delivery,updated_at FROM native_telegram_alerts WHERE fingerprint="+mark,(key,)).fetchone()
    return self.reply(200,{"status":record[0],"updated_at":record[1]} if record else {"status":"not_found"})
   except Exception:return self.reply(503,{"error":"delivery_status_unavailable"})

  if path=="/v1/audit/state":
   secret=os.getenv("BIGBEN_AUDIT_TOKEN","")
   if len(secret)<32 or not secure_equal(self.headers.get("X-BigBen-Audit-Token",""),secret):return self.reply(401,{"message":"فحص غير مصرح"})
   try:
    with history_connection() as c:
     assets=tracked_asset_catalog(c)
     events=c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
     deliveries=c.execute("SELECT delivery,COUNT(*) FROM native_telegram_alerts GROUP BY delivery").fetchall()
    return self.reply(200,{"الحالة":"الخادم وقاعدة البيانات يعملان","التخزين":storage_kind(),"النسخة":os.getenv("RENDER_GIT_COMMIT","نسخة محلية"),"عدد_الأحداث":events,"الأصول":assets,"إيصالات_التسليم":[{"الحالة":r[0],"العدد":r[1]} for r in deliveries],"تنفيذ_الأوامر":"معطل","الأخبار":"مسار مستقل عن بطاقات الصفقة والتحليل والمتابعة","تغطية_الأسعار":{"مفتاح_العقود_مهيأ":bool(os.getenv("BARCHART_API_KEY")),"ترخيص_وتغطية_Futures_CFD_موثقان":False},"اختبارات_النقل":transport_proofs()})
   except Exception:return self.reply(503,{"message":"تعذر إكمال الفحص"})
  if path=="/healthz":return self.reply(200,{"status":"ok","release":"symbol-sync-demo-readonly-v2","mode":"live-analysis-alerts-only","runtime_mode":"live_analysis","broker_execution":"disabled","agents":"enabled","resident_watchdog":os.getenv("BIGBEN_AGENT_WATCHDOG_ENABLED","1")=="1","learning":"evidence_only_no_automatic_code_or_strategy_edits"})
  if path=="/healthz/integrations":
   token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
   chat=telegram_destination()
   return self.reply(200,{"status":"ok","mode":"live-analysis-alerts-only","broker_execution":"disabled","telegram":{"bot_token_configured":bool(token),"chat_id_configured":bool(re.fullmatch(r"-?[0-9]{5,20}",chat))},"tradingview":{"webhook_token_configured":len(os.getenv("BIGBEN_WEBHOOK_TOKEN",""))>=32,"events_are_required_for_live_signal_state":True,**event_freshness()},"whatsapp":_whatsapp.status(),"ai":_ai_provider.status(),"agents":{"enabled":os.getenv("BIGBEN_SIGNAL_ANALYSIS_ENABLED","1")=="1","roles":9,"mode":"alerts_only","runtime_mode":"live_analysis","resident_watchdog":os.getenv("BIGBEN_AGENT_WATCHDOG_ENABLED","1")=="1","learning":"evidence_only_no_automatic_code_or_strategy_edits"},"database":{"storage":storage_kind()},"market_data":{"twelve_data_key_configured":bool(twelve_data_key()),"credentials_only":True,"probe":MARKET_DATA_DIAGNOSTIC.copy()}})
  if path=="/healthz/market-sessions":
   return self.reply(200,_market_sessions.status())
  if path=="/healthz/storage":
   try:
    init()
    if postgres_enabled():
     # Read-only connectivity check: health checks must never create market events.
     with pg_connect() as c:
      c.execute("SELECT 1").fetchone()
    else:
     with sqlite_connection() as c:c.execute("SELECT 1").fetchone()
   except Exception:
    return self.reply(503,{"status":"unavailable","storage":storage_kind()})
   return self.reply(200,{"status":"ok","storage":storage_kind()})
  if path=="/api/market/sessions":
   return self.reply(200,_market_sessions.status())
  if path not in ("/","/dashboard","/reference_dashboard.css","/api/events","/api/events.csv","/api/status","/api/diagnostics","/api/market","/api/chart/candles","/api/massive/history","/api/outcomes","/api/research","/api/agent","/api/learning","/api/data-sources","/api/pine/current","/api/analysis","/api/scalping","/api/market/coverage","/api/research/runs","/api/news","/api/integrations","/api/research/pine-runs","/api/instruments","/api/connected-symbols","/v1/connected-symbols","/api/tradingview/discovered-symbols","/api/tracked-symbols","/api/trade-journal","/api/destinations","/api/analysis/runs","/api/workspace/drafts","/api/workspace/notes","/api/operations","/api/backup/export","/api/research/walk-forward","/api/market/pulses"):return self.reply(404,{"error":"not_found"})
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
  if path=="/reference_dashboard.css":
   try:body=(Path(__file__).resolve().parents[1]/"reference_dashboard.css").read_bytes()
   except OSError:return self.reply(503,{"error":"dashboard_stylesheet_unavailable"})
   self.send_response(200)
   for k,v in {"Content-Type":"text/css; charset=utf-8","Content-Length":str(len(body)),
    "Cache-Control":"no-cache","X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY"}.items():self.send_header(k,v)
   self.end_headers();self.wfile.write(body)
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
  if path=="/api/market/pulses":
   try:
    with history_connection() as c:return self.reply(200,{"pulses":_market_pulses.latest(c),"source":"stored closed candles","trades_created":False})
   except Exception:return self.reply(503,{"error":"market_pulses_unavailable"})
  if path=="/api/analysis/runs":
   try:
    with history_connection() as c:rows=c.execute("SELECT payload FROM analysis_runs ORDER BY created_at DESC LIMIT 20").fetchall()
    return self.reply(200,{"runs":[json.loads(row[0]) for row in rows],"signal_analysis_enabled":os.getenv("BIGBEN_SIGNAL_ANALYSIS_ENABLED","1")=="1","deterministic_roles":9,"agent_mode":"live_analysis","resident_watchdog":os.getenv("BIGBEN_AGENT_WATCHDOG_ENABLED","1")=="1","learning_policy":"evidence_only_no_automatic_code_or_strategy_edits","ai_daily_request_limit":10})
   except Exception:return self.reply(503,{"error":"analysis_history_unavailable"})
  if path=="/api/trade-journal":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   try:
    with history_connection() as db:records=_native_trade_journal.recent(db)
    return self.reply(200,{"records":records,"count":len(records),"execution":"متابعة بحثية افتراضية دون تنفيذ أوامر"})
   except Exception:return self.reply(503,{"error":"journal_unavailable"})
  if path=="/api/tracked-symbols":
   try:
    with history_connection() as c:items=tracked_asset_catalog(c)
    return self.reply(200,{"symbols":items,"count":len(items),"note":"أصول المتابعة ليست كلها متصلة بالأسعار؛ تحقّق من حالة كل أصل."})
   except Exception:return self.reply(503,{"message":"تعذر قراءة أصول المتابعة"})
  if path=="/api/tradingview/discovered-symbols":
   try:
    with history_connection() as c:items=_tradingview_dynamic_sync.discovered(c)
    return self.reply(200,{"symbols":items,"note":"رموز مستلمة من تنبيهات موثقة؛ لا تعني اتصال الأسعار أو إنشاء تنبيهات جديدة."})
   except Exception:return self.reply(503,{"error":"symbol_discovery_unavailable"})
  if path in ("/api/connected-symbols","/v1/connected-symbols"):
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   try:
    with history_connection() as db:symbols=owner_connected_assets(db)
    return self.reply(200,{"symbols":symbols,"count":len(symbols),
       "futures_note":"لا تُعرض العقود الآجلة حتى يكتمل اتصال مصدر شموع مرخص مطابق للعقد",
       "source_policy":"رموز بيانات مؤكدة فقط، وليس مجرد قائمة مراقبة"})
   except Exception:return self.reply(503,{"error":"connected_symbols_unavailable"})
  if path=="/api/instruments":
   try:
    with history_connection() as c:allowed=owner_watchlist(c)
    catalog=[i for i in _instruments.catalog(allowed,[]) if i['symbol'] in allowed]
    return self.reply(200,{"instruments":catalog,"selected_instruments":catalog,"watchlist":sorted(allowed),"arbitrary_qualified_symbols":False,"alert_coverage_not_implied":True})
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
   with history_connection() as c:diagnostics=watchlist_diagnostics(c)
   return self.reply(200,{"تشخيص_المتابعة":diagnostics,"status":"configuration_only","preferred_provider":"TradingView Webhook",
     "barchart":{"api_key_configured":barchart_key,"symbol_mapping_configured":mapping_configured,
                  "licensed_symbol_coverage":"unverified","live_and_historical_entitlements":"unverified",
                  "research_ready":barchart_key and mapping_configured},
     "twelve_data":{"api_key_configured":twelve_key,"role":"primary_candles_budgeted_400_daily",
                    "futures_coverage":"not_confirmed","probe":MARKET_DATA_DIAGNOSTIC.copy()},
     "tradingview":{"role":"primary_authenticated_chart_candles","url":"/v1/tradingview/candles","history_required":300,"configured_alerts_do_not_prove_candle_delivery":True},
     "yfinance":{"role":"free_reference_fallback","daily_attempt_limit":144,"live_verified":False,"broker_cfd_equivalence":False},
     "data_policy":"Never use unsupported futures quotes, stale candles, or fabricated backtests"})
  if path=="/api/massive/history":
   query=parse_qs(urlsplit(self.path).query)
   with history_connection() as db:watched=owner_watchlist(db)
   try:
    result=_massive_history.read(query.get("ticker",[""])[0],query.get("frame",["M5"])[0],
                                 watched,os.getenv("MASSIVE_FUTURES_API_KEY","").strip())
   except _massive_history.HistoryError as error:
    code=str(error)
    status={"invalid":400,"not_tracked":403,"identity":422,"entitlement":403,"no_data":404,"rate_limit":429}.get(code,503)
    return self.reply(status,{"error":code,"message":_massive_history.MESSAGES[code]})
   return self.reply(200,result)
  if path=="/api/chart/candles":
   # Native canvas uses exactly the stored, provider-verified closed OHLC bars.
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   try:
    q=parse_qs(urlsplit(self.path).query)
    symbol=_instruments.normalize(q.get("symbol",[""])[0])
    with history_connection() as c:
     if symbol not in owner_watchlist(c):return self.reply(403,{'رسالة':'الأصل خارج قائمة TradingView المصرح بها'})
    instrument=_instruments.describe(symbol)
    marker="%s" if postgres_enabled() else "?"
    provider="Twelve Data"
    with history_connection() as c:tv_rows,tv_meta=_tradingview_candles.read(c,symbol,postgres_enabled())
    if _tradingview_candles.fresh(tv_meta):
     candles,source_meta=tv_rows,tv_meta;provider=_tradingview_candles.PROVIDER
    elif instrument["asset_class"]=="crypto" and symbol.startswith("BITSTAMP:"):
     provider="Bitstamp"
     candles,source_meta=bitstamp_native_candles(symbol)
    elif instrument["asset_class"]=="forex" and symbol.split(":",1)[1][:3]+"/"+symbol.split(":",1)[1][3:] in _history.FOREX:
     ticker=symbol.split(":",1)[1]
     pair=ticker[:3]+"/"+ticker[3:]
     with history_connection() as c:
      candles=c.execute("SELECT time,open,high,low,close FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker+" ORDER BY time DESC LIMIT 1000",(pair,)).fetchall()
    else:
     with history_connection() as c:candles,source_meta=_live_candle_adapter.read(c,symbol,postgres_enabled())
     if not candles:return self.reply(422,{'رسالة':'لا توجد شموع مرجعية لهذا الأصل','symbol':symbol})
     provider=source_meta.get('provider')
    out=[{"time":row[0],"open":row[1],"high":row[2],"low":row[3],"close":row[4]} for row in reversed(candles)]
    last=out[-1]["time"] if out else None
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(last.replace("Z","+00:00"))).total_seconds() if last else None
    return self.reply(200,{"symbol":symbol,"provider":provider,"interval":"5min",
      "realtime_verified":False,"reference_only":provider=='yfinance / Yahoo Finance',"candles":out,"last_closed_candle":last,
      "age_seconds":int(age) if age is not None else None,
      "fresh":age is not None and 300<=age<=630,"feed_state":("NO_DATA" if age is None else "CURRENT_CLOSED_M5" if 300<=age<=630 else "STALE" if age>630 else "UNCLOSED"),"checked_at":datetime.now(timezone.utc).isoformat(),"note":"Closed provider candles only, periodically fetched; not tick streaming or TradingView indicator events."})
   except _crypto_history.CryptoHistoryError as error:return self.reply(503,{"error":"crypto_ohlc_unavailable","reason":str(error),"symbol":symbol})
   except (TypeError,ValueError,IndexError):return self.reply(400,{"error":"invalid_symbol"})
   except Exception:return self.reply(503,{"error":"chart_candles_unavailable"})
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
    return self.reply(200,{"agent":"Big Ben reliability + research","mode":"alerts_only","checked_at":now.isoformat(),
      "services":{"storage":storage_kind(),"twelve_data_key_configured":bool(twelve_data_key()),"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))},
      "pattern_audits":stored_pattern_audits(now),"tracked_symbols":list(latest.values()),"research":{"status":result["status"],"observed_outcomes":result["observed_outcomes"],"signals_examined":result["signals_examined"]},
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
    lifecycle=signal_lifecycle(d,t) if event in ("BUY","SELL") else {"status":"HEARTBEAT","fresh":None,"age_seconds":None,"ttl_seconds":None,"expires_at":None}
    events.append({"event_id":d.get("event_id"),"instrument":_instruments.describe(symbol),"notification_text":trade_notification_text(d) if event in ("BUY","SELL") else None,"symbol":symbol,"event":event,"time":t,"received_at":d.get("received_at"),"entry":d.get("entry"),"sl":d.get("sl"),"tp":d.get("tp"),"rr":d.get("rr"),"evidence":d.get("evidence"),"confidence":d.get("confidence"),"entry_zone_low":d.get("entry_zone_low"),"entry_zone_high":d.get("entry_zone_high"),"htf_bias":d.get("htf_bias"),**lifecycle})
   return self.reply(200,{"events":events,"count":len(events),"storage":storage_kind(),"source":"TradingView webhooks"})
  try:body=(Path(__file__).resolve().parents[1]/"index.html").read_bytes()
  except OSError:return self.reply(503,{"error":"dashboard_unavailable"})
  self.send_response(200)
  for k,v in {"Content-Type":"text/html; charset=utf-8","Content-Length":str(len(body)),"Cache-Control":"no-store","X-Frame-Options":"DENY","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Content-Security-Policy":"default-src 'none'; style-src 'self' 'unsafe-inline' https://*.tradingview.com; script-src 'self' 'unsafe-inline' https://s3.tradingview.com; frame-src https://*.tradingview.com; img-src 'self' data: https://*.tradingview.com; connect-src 'self' wss://ws.bitstamp.net; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_POST(self):
  if urlsplit(self.path).path=='/v1/verification/news-delivery':
   secret=os.getenv('BIGBEN_NEWS_PROOF_TOKEN','')
   if len(secret)<32 or not secure_equal(self.headers.get('X-BigBen-News-Proof',''),secret):return self.reply(401,{'الحالة':'طلب غير مصرح'})
   owner=os.getenv('BIGBEN_TELEGRAM_ALLOWED_USER_IDS','').split(',')[0].strip()
   if notifications_muted(owner):return self.reply(409,{'الحالة':'الإشعارات مكتومة؛ لم تُرسل الرسالة'})
   now=datetime.now(timezone.utc)
   try:
    with history_connection() as db:
     bulletin=_telegram_interactive.verified_news_bulletin(_news.snapshot(db,now),now)
     if not bulletin:return self.reply(409,{'الحالة':'لا يوجد خبر حالي أو قادم موثق؛ حُجبت الأخبار الماضية'})
     key='news-proof:'+owner+':'+bulletin['source_id']
     claimed=_telegram_interactive.claim(db,key,postgres_enabled(),now)
     if not claimed:
      m='%s' if postgres_enabled() else '?'
      row=db.execute('SELECT status FROM telegram_bot_receipts WHERE id='+m,(key,)).fetchone()
      return self.reply(200,{'مكرر':True,'الإيصال':json.loads(row[0]) if row and row[0].startswith('{') else 'حجز سابق؛ لا إعادة تلقائية'})
    receipt=send_transport_card(bulletin['text'])
    receipt.update({'معرف_المصدر':bulletin['source_id'],'تاريخ_النشر':bulletin['published_at'],'نوع_الإثبات':'حدث اقتصادي حالي أو قادم؛ سيناريوهات مشروطة مستقلة'})
    with history_connection() as db:
     m='%s' if postgres_enabled() else '?'
     db.execute('UPDATE telegram_bot_receipts SET status='+m+' WHERE id='+m,(json.dumps(receipt,ensure_ascii=False),key))
    return self.reply(200,receipt)
   except Exception:return self.reply(503,{'الحالة':'تعذر إكمال التحقق؛ لا إعادة تلقائية لتسليم غير مؤكد'})
  if urlsplit(self.path).path=="/v1/tradingview/candles":
   secret=os.getenv('BIGBEN_WEBHOOK_TOKEN','')
   if len(secret)<32:return self.reply(503,{'رسالة':'مستقبل الشموع غير مهيأ'})
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=8192:return self.reply(413,{'رسالة':'حجم غير مقبول'})
    data=json.loads(self.rfile.read(size))
    if not isinstance(data,dict):raise ValueError()
    if not secure_equal(data.pop('token',''),secret):return self.reply(401,{'رسالة':'شمعة غير مصرح بها'})
    event=_tradingview_candles.validate(data)
    instrument=_instruments.describe(event['symbol'])
    specs=instrument.get('contract_specs')
    if specs and not math.isclose(event['tick_size'],specs['price_tick']):raise ValueError()
    with history_connection() as db:
     inserted=_tradingview_candles.ingest(db,event,postgres_enabled())
    duplicate=save_event(event)
    self.reply(202 if inserted else 200,{'تم_الاستلام':True,'شمعة_جديدة':inserted,'مكرر':duplicate,'الرمز':event['symbol'],'التنفيذ':'معطل','ملاحظة':'إرسال الصفقة يتطلب تاريخاً كافياً وأهدافاً مقاسة وفحص السوق؛ لا يشترط مصدراً خارجياً'})
    if not duplicate:threading.Thread(target=process_chart_candle,args=(event['symbol'],),daemon=True).start()
    return
   except (ValueError,TypeError,UnicodeDecodeError):return self.reply(422,{'رسالة':'حمولة شمعة غير صالحة أو متأخرة؛ لم تُجدّد حداثة السعر'})
   except Exception:return self.reply(503,{'رسالة':'تعذر حفظ شمعة TradingView'})
  if urlsplit(self.path).path=="/v1/tradingview/watchlist-sync":
   secret=os.getenv('BIGBEN_WATCHLIST_SYNC_TOKEN','')
   if len(secret)<32 or not secure_equal(self.headers.get('X-BigBen-Watchlist-Token',''),secret):return self.reply(401,{'رسالة':'مزامنة غير مصرح بها'})
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=65536:return self.reply(413,{'رسالة':'حجم المزامنة غير صالح'})
    data=json.loads(self.rfile.read(size))
    with history_connection() as db:result=_tv_watchlist.sync(db,data,postgres_enabled())
    return self.reply(200,{'تمت_المزامنة':True,'عدد_الأصول':len(result['symbols']),'المراجعة':result['revision']})
   except (ValueError,TypeError,UnicodeDecodeError):return self.reply(422,{'رسالة':'قائمة أو مراجعة مزامنة غير صالحة؛ حُفظت القائمة السابقة'})
   except Exception:return self.reply(503,{'رسالة':'تعذر حفظ مزامنة القائمة'})
  if urlsplit(self.path).path=="/v1/tradingview/transport-test":
   secret=os.getenv("BIGBEN_TRANSPORT_TEST_TOKEN","")
   if os.getenv("BIGBEN_TRANSPORT_TEST_ENABLED","0")!="1":return self.reply(503,{"message":"الاختبار معطل"})
   if len(secret)<32 or not secure_equal(self.headers.get("X-BigBen-Test-Token",""),secret):return self.reply(401,{"message":"اختبار غير مصرح"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=1024:raise ValueError()
    data=json.loads(self.rfile.read(size));test_id=data.get("test_id");case=data.get("case")
    if not isinstance(test_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,60}",test_id) or case not in ("closed","open"):raise ValueError()
    if test_id!=os.getenv("BIGBEN_TRANSPORT_SELF_TEST_ID",""):raise ValueError()
   except (ValueError,TypeError,AttributeError):return self.reply(400,{"message":"طلب اختبار غير صالح"})
   try:return self.reply(200,execute_transport_fixture(test_id,case))
   except Exception:return self.reply(503,{"message":"تعذر إكمال اختبار النقل"})
  if urlsplit(self.path).path=="/v1/tradingview/bbb":
   secret=os.getenv("BIGBEN_BBB_WEBHOOK_TOKEN","")
   if len(secret)<32:return self.reply(503,{"message":"مستقبل BBB غير مهيأ"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=8192:return self.reply(413,{"message":"حجم غير مقبول"})
    data=json.loads(self.rfile.read(size))
    if not isinstance(data,dict):raise ValueError('حمولة غير صالحة')
    token=data.pop("token","")
    if not secure_equal(token,secret):return self.reply(401,{"message":"تنبيه غير مصرح"})
    event=_bridge_validation.normalize(data)
    duplicate=save_event(event)
   except (ValueError,TypeError,UnicodeDecodeError) as error:return self.reply(422,{"message":"حمولة التنبيه غير صالحة؛ تحقق من الرمز والتوقيت ومستويات الأسعار"})
   except Exception:return self.reply(503,{"message":"تعذر حفظ التنبيه"})
   self.reply(200 if duplicate else 202,{"مقبول":True,"مكرر":duplicate,"معرف_الحدث":event["event_id"],"حالة":"تم الحفظ؛ لا يثبت استلام التنبيه اتصال الأسعار أو افتتاح السوق"})
   if not duplicate:threading.Thread(target=process_bbb_event,args=(event,),daemon=True).start()
   return
  if urlsplit(self.path).path=="/v1/telegram/updates":
   secret=os.getenv("BIGBEN_TELEGRAM_WEBHOOK_SECRET","")
   if len(secret)<32:return self.reply(503,{"message":"لم يهيأ استقبال البوت بعد"})
   if not secure_equal(self.headers.get("X-Telegram-Bot-Api-Secret-Token",""),secret):return self.reply(401,{"message":"طلب غير مصرح"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=32768:return self.reply(413,{"message":"حجم الطلب غير مقبول"})
    update=json.loads(self.rfile.read(size))
    if not isinstance(update,dict) or type(update.get("update_id")) is not int:raise ValueError()
   except (ValueError,UnicodeDecodeError):return self.reply(400,{"message":"طلب غير صالح"})
   self.reply(202,{"message":"استلم طلب التفاعل"})
   threading.Thread(target=process_bot_update,args=(update,),daemon=True).start()
   return
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
  if urlsplit(self.path).path=="/api/news/test":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   try:
    _news.refresh(history_connection,postgres_enabled())
    with history_connection() as c:result=_news.snapshot(c)
    result["test_only"]=True;result["message"]="تم اختبار مصادر الأخبار الرسمية؛ لا يتم إنشاء إشارة أو تعديل الاستراتيجية."
    return self.reply(200,result)
   except Exception:return self.reply(503,{"error":"news_test_failed"})
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
    return self.reply(200,{"saved":True,**preferences,"whatsapp_automatic_connected":_whatsapp.status()["provider_connection_verified"],"whatsapp":_whatsapp.status()})
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if urlsplit(self.path).path=="/api/instant/analyze":
   if not dashboard_authenticated(self.headers):return self.reply(401,{"error":"unauthorized"})
   if self.headers.get("Content-Type","").split(";",1)[0]!="application/json":return self.reply(415,{"error":"json_content_type_required"})
   origin=self.headers.get("Origin")
   if origin and urlsplit(origin).netloc!=self.headers.get("Host"):return self.reply(403,{"error":"origin"})
   try:
    size=int(self.headers.get("Content-Length","0"))
    if not 0<size<=2048:return self.reply(413,{"error":"size"})
    request=json.loads(self.rfile.read(size))
    if not isinstance(request,dict):raise ValueError()
    symbol=_instruments.normalize(request.get("symbol"))
    mode=request.get("mode","scalp")
    if mode not in ("scalp","swing"):return self.reply(400,{"error":"unsupported_analysis_mode"})
   except (ValueError,TypeError,UnicodeDecodeError):return self.reply(400,{"error":"invalid_symbol_or_json"})
   try:
    result=analyze_instant_native(symbol,mode)
    result["telegram_delivery"]=trigger_instant_telegram(result)
    return self.reply(200,result)
   except Exception:return self.reply(503,{"error":"instant_analysis_unavailable"})
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
    mode=request.get("mode","scalp")
    if mode not in ("scalp","swing"):return self.reply(400,{"error":"unsupported_analysis_mode"})
    result=analyze_native_chart(symbol,mode)
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
   queued=SIGNAL_PIPELINE.enqueue(d["symbol"],d)
   if not queued:print("signal_pipeline state=backpressure symbol="+d["symbol"],flush=True)
if __name__=="__main__":
 init()  # Create schema once at process startup, not for every incoming M5 event.
 import threading
 threading.Thread(target=check_market_connection,daemon=True).start()
 threading.Thread(target=crypto_startup_probe,daemon=True).start()
 threading.Thread(target=audit_telegram_connection,daemon=True).start()
 threading.Thread(target=configure_interactive_bot,daemon=True).start()
 threading.Thread(target=bbb_recovery_worker,daemon=True).start()
 if os.getenv("BIGBEN_AGENT_WATCHDOG_ENABLED","1")=="1":
  threading.Thread(target=agent_watchdog,daemon=True).start()
 threading.Thread(target=history_worker,daemon=True).start()
 if os.getenv("BIGBEN_FAST_M5_HISTORY_ENABLED","1")=="1":threading.Thread(target=fast_history_worker,daemon=True).start()
 threading.Thread(target=news_worker,daemon=True).start()
 threading.Thread(target=market_pulse_worker,daemon=True).start()
 if os.getenv("BIGBEN_ARABIC_SCANNER_ENABLED","1")=="1":threading.Thread(target=arabic_market_scanner_worker,daemon=True).start()
 port=int(os.getenv("PORT","10000"))
 print("http_server bind=0.0.0.0 port="+str(port),flush=True)
 server=ThreadingHTTPServer(("0.0.0.0",port),Handler)
 threading.Thread(target=run_local_transport_check,daemon=True).start()
 server.serve_forever()

