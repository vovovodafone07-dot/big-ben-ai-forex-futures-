"""Big Ben AI Pro: read-only webhook receiver. No broker/order endpoints."""
import os,json,hmac,math,re,sqlite3,time,base64,sys,subprocess,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
DB=Path(os.getenv("BIGBEN_DB_PATH","/tmp/bigben-dev.sqlite3"))
LAST_TEST_SENT=0
def postgres_enabled():
 return bool(os.getenv("DATABASE_URL", "").strip())
def storage_kind():
 return "postgres" if postgres_enabled() else "ephemeral"
def pg_connect():
 # Existing Render service builds without pip install. Install driver only if
 # PostgreSQL is configured; keep secrets out of command arguments and logs.
 try:
  import psycopg
 except ImportError:
  target="/tmp/bigben-python-deps"
  if target not in sys.path:sys.path.insert(0,target)
  try:
   import psycopg
  except ImportError:
   subprocess.run([sys.executable,"-m","pip","install","--disable-pip-version-check","--quiet","--target",target,"psycopg[binary]>=3.2,<4"],check=True,timeout=90)
   import psycopg
 return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5)
def init():
 if postgres_enabled():
  with pg_connect() as c:
   c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, symbol TEXT NOT NULL, event TEXT NOT NULL, time TEXT NOT NULL, payload TEXT NOT NULL)")
 else:
  DB.parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(DB) as c:
   c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,symbol TEXT,event TEXT,time TEXT,payload TEXT)")
def list_events(limit=500):
 init()
 if postgres_enabled():
  with pg_connect() as c:
   return c.execute("SELECT symbol,event,time,payload FROM events ORDER BY time DESC LIMIT 500").fetchall()
 with sqlite3.connect(DB) as c:
  return c.execute("SELECT symbol,event,time,payload FROM events ORDER BY time DESC LIMIT 500").fetchall()
def save_event(d):
 init()
 vals=(d["event_id"],d["symbol"],d["event"],d["time"],json.dumps(d))
 if postgres_enabled():
  with pg_connect() as c:
   return c.execute("INSERT INTO events (id,symbol,event,time,payload) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",vals).rowcount==0
 with sqlite3.connect(DB) as c:
  return c.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",vals).rowcount==0
def validate(d):
 if not isinstance(d,dict) or d.get("schema")!="bigben.v1":raise ValueError("schema")
 if d.get("event") not in ("BUY","SELL","TP_HIT","SL_HIT","HEARTBEAT"):raise ValueError("event")
 if not isinstance(d.get("symbol"),str) or not re.fullmatch(r"[A-Za-z0-9:_!./-]{1,60}",d["symbol"]) or ".." in d["symbol"] or d["symbol"].startswith(("/", ".")):raise ValueError("symbol")
 if not isinstance(d.get("event_id"),str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,120}",d["event_id"]):raise ValueError("event_id")
 try:
  t=datetime.fromisoformat(d["time"].replace("Z","+00:00"))
  if t.tzinfo is None or abs(t.timestamp()-time.time())>600:raise ValueError()
 except (ValueError,TypeError,KeyError,AttributeError):raise ValueError("time")
 if d["event"] in ("BUY","SELL"):
  try:entry,sl,tp,rr=[d[k] for k in ("entry","sl","tp","rr")]
  except KeyError:raise ValueError("levels")
  if any(type(n) not in (int,float) or not math.isfinite(n) or n<=0 for n in (entry,sl,tp,rr)):raise ValueError("levels")
  if not ((sl<entry<tp) if d["event"]=="BUY" else (tp<entry<sl)):raise ValueError("direction")
  if not math.isclose(abs(tp-entry)/abs(entry-sl),rr,rel_tol=.03,abs_tol=.03):raise ValueError("rr")
 return d
def telegram_notify(d):
 # Explicit chat allowlist avoids accidentally sending private trade data to strangers.
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
 chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
 if not token or not re.fullmatch(r"-?[0-9]{5,20}",chat):
  return "not_configured"
 if d.get("event") not in ("BUY","SELL"):
  return "skipped"
 message=("📊 Big Ben AI Pro\n"
          +str(d["event"])+" | "+str(d["symbol"])+"\\n"
          +"Entry: "+str(d["entry"])+"\\nSL: "+str(d["sl"])
          +"\\nTP: "+str(d["tp"])+"\\nRR: "+str(d["rr"])
          +"\\nAnalysis only — no order execution")
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
 return hmac.compare_digest(headers.get("Authorization",""),expected)
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
   return self.reply(200,{"status":"ok","telegram":{"bot_token_configured":bool(token),"chat_id_configured":bool(re.fullmatch(r"-?[0-9]{5,20}",chat))},"tradingview":{"webhook_token_configured":len(os.getenv("BIGBEN_WEBHOOK_TOKEN",""))>=32},"database":{"storage":storage_kind()}})
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
     with sqlite3.connect(DB) as c:c.execute("SELECT 1").fetchone()
   except Exception:
    return self.reply(503,{"status":"unavailable","storage":storage_kind()})
   return self.reply(200,{"status":"ok","storage":storage_kind()})
  if path not in ("/","/dashboard","/api/events","/api/status"):return self.reply(404,{"error":"not_found"})
  password=os.getenv("BIGBEN_DASHBOARD_PASSWORD","")
  if len(password)<20:return self.reply(503,{"error":"dashboard_not_configured"})
  supplied=self.headers.get("Authorization","")
  expected="Basic "+base64.b64encode(("bigben:"+password).encode()).decode()
  if not hmac.compare_digest(supplied,expected):
   self.send_response(401)
   self.send_header("WWW-Authenticate",'Basic realm="Big Ben Private Preview"')
   self.send_header("Cache-Control","no-store")
   self.send_header("Content-Length","0")
   self.end_headers()
   return
  if path=="/api/status":
   try:
    rows=list_events()
    last=rows[0] if rows else None
    symbols={}
    for symbol,event,t,payload in rows:
     if symbol not in symbols:symbols[symbol]={"symbol":symbol,"last_seen":t,"last_event":event,"heartbeat_count":0,"trade_count":0}
     if event=="HEARTBEAT":symbols[symbol]["heartbeat_count"]+=1
     if event in ("BUY","SELL"):symbols[symbol]["trade_count"]+=1
    return self.reply(200,{"last_event_time":last[2] if last else None,"last_event_symbol":last[0] if last else None,"recent_trade_count":sum(1 for r in rows if r[1] in ("BUY","SELL")),"recent_heartbeat_count":sum(1 for r in rows if r[1]=="HEARTBEAT"),"symbols":list(symbols.values()),"storage":storage_kind(),"telegram_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))})
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
  if path=="/api/events":
   kind=parse_qs(urlsplit(self.path).query).get("type",["trades"])[0]
   if kind not in ("trades","all","heartbeat"):return self.reply(400,{"error":"type"})
   try:rows=list_events()
   except Exception:return self.reply(503,{"error":"storage_unavailable"})
   if kind=="trades":rows=[r for r in rows if r[1] in ("BUY","SELL")][:150]
   elif kind=="heartbeat":rows=[r for r in rows if r[1]=="HEARTBEAT"][:150]
   else:rows=rows[:150]
   events=[]
   for symbol,event,t,payload in rows:
    d=json.loads(payload)
    events.append({"symbol":symbol,"event":event,"time":t,"entry":d.get("entry"),"sl":d.get("sl"),"tp":d.get("tp"),"rr":d.get("rr"),"evidence":d.get("evidence"),"confidence":d.get("confidence"),"entry_zone_low":d.get("entry_zone_low"),"entry_zone_high":d.get("entry_zone_high")})
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
  if not isinstance(token,str) or not hmac.compare_digest(token,secret):return self.reply(401,{"error":"unauthorized"})
  try:validate(d)
  except ValueError as e:return self.reply(422,{"error":str(e)})
  try:duplicate=save_event(d)
  except Exception:return self.reply(503,{"error":"storage_unavailable"})
  self.reply(200 if duplicate else 202,{"accepted":True,"duplicate":duplicate,"event_id":d["event_id"]})
  if not duplicate:
   status=telegram_notify(d)
   print("telegram_delivery="+status,flush=True)
if __name__=="__main__":
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8080"))),Handler).serve_forever()
