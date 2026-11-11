"""Big Ben AI Pro: read-only webhook receiver. No broker/order endpoints."""
import os,json,hmac,math,re,sqlite3,time,base64
from datetime import datetime,timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
DB=Path(os.getenv("BIGBEN_DB_PATH","/tmp/bigben-dev.sqlite3"))
def postgres_enabled():
 return bool(os.getenv("DATABASE_URL", "").strip())
def storage_kind():
 return "postgres" if postgres_enabled() else "ephemeral"
def pg_connect():
 # psycopg must be installed at build time; never log DATABASE_URL.
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
def list_events():
 init()
 if postgres_enabled():
  with pg_connect() as c:
   return c.execute("SELECT symbol,event,time,payload FROM events ORDER BY time DESC LIMIT 50").fetchall()
 with sqlite3.connect(DB) as c:
  return c.execute("SELECT symbol,event,time,payload FROM events ORDER BY time DESC LIMIT 50").fetchall()
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
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,obj):
  b=json.dumps(obj).encode();self.send_response(status)
  for k,v in {"Content-Type":"application/json","Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'none'","Content-Length":str(len(b))}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=="/healthz":return self.reply(200,{"status":"ok","mode":"read-only"})
  if path not in ("/","/dashboard","/api/events"):return self.reply(404,{"error":"not_found"})
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
  if path=="/api/events":
   rows=list_events()
   events=[]
   for symbol,event,t,payload in rows:
    d=json.loads(payload)
    events.append({"symbol":symbol,"event":event,"time":t,"entry":d.get("entry"),"sl":d.get("sl"),"tp":d.get("tp"),"rr":d.get("rr")})
   return self.reply(200,{"events":events,"count":len(events),"storage":storage_kind(),"source":"TradingView webhooks"})
  try:body=(Path(__file__).resolve().parents[1]/"index.html").read_bytes()
  except OSError:return self.reply(503,{"error":"dashboard_unavailable"})
  self.send_response(200)
  for k,v in {"Content-Type":"text/html; charset=utf-8","Content-Length":str(len(body)),"Cache-Control":"no-store","X-Frame-Options":"DENY","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_POST(self):
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
  duplicate=save_event(d)
  self.reply(200 if duplicate else 202,{"accepted":True,"duplicate":duplicate,"event_id":d["event_id"]})
if __name__=="__main__":
 init();ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8080"))),Handler).serve_forever()
