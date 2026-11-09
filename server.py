"""Read-only Big Ben market data proxy. Requires TWELVEDATA_API_KEY environment variable."""
import os, json, urllib.request, urllib.error, urllib.parse, http.server, pathlib, time, statistics, threading, re
ROOT=pathlib.Path(__file__).parent
KEY=os.getenv('TWELVEDATA_API_KEY','').strip()
LOCK=threading.Lock()
LAST_CALLS={}
CACHE={}
FUTURES={'ES':'ES','NQ':'NQ','YM':'YM','RTY':'RTY','6E':'6E','6B':'6B','6J':'6J','CL':'CL'}
def provider_error(payload, default='Market data unavailable'):
    # Do not expose provider request URLs, API credentials or arbitrary provider text.
    if not isinstance(payload,dict):return default
    code=payload.get('code')
    msg=str(payload.get('message',default))
    msg=re.sub(r'(?i)(apikey|api_key|token|secret|authorization)[=: ]+[^\s&,]+',r'\1=[hidden]',msg)
    msg=msg[:260]
    return ('Twelve Data '+str(code)+': ' if isinstance(code,int) else 'Twelve Data: ')+msg

def analyze(bars,rr,direction):
    b=[{'o':float(x['open']),'h':float(x['high']),'l':float(x['low']),'c':float(x['close'])} for x in reversed(bars)]
    if len(b)<35: raise ValueError('Not enough candles')
    closes=[x['c'] for x in b]; ema=lambda n: sum(closes[-n:])/n
    atr=statistics.mean([max(x['h']-x['l'],abs(x['h']-b[i-1]['c']),abs(x['l']-b[i-1]['c'])) for i,x in enumerate(b) if i>len(b)-15]);
    trend='buy' if closes[-1]>ema(20) and ema(10)>ema(20) else 'sell' if closes[-1]<ema(20) and ema(10)<ema(20) else 'neutral'
    last=b[-1]; upper=max(x['h'] for x in b[-21:-1]); lower=min(x['l'] for x in b[-21:-1]); breakout='buy' if last['c']>upper else 'sell' if last['c']<lower else None
    valid=breakout and breakout==trend and (direction=='both' or direction==breakout)
    entry=last['c']; stop=(min(x['l'] for x in b[-8:])-atr*.2) if breakout=='buy' else (max(x['h'] for x in b[-8:])+atr*.2) if breakout=='sell' else None
    risk=abs(entry-stop) if stop is not None else 0
    if risk<=0: valid=False
    targets=[round(entry+(1 if breakout=='buy' else -1)*risk*rr*i/3,8) for i in (1,2,3)] if valid else []
    return {'trend':trend,'breakout':breakout,'confirmed':bool(valid),'entry':round(entry,8) if valid else None,'stop':round(stop,8) if valid else None,'targets':targets,'confidence':70 if valid else None,'close':round(last['c'],8),'atr':round(atr,8),'timestamp':bars[0].get('datetime'),'method':'SMA10/20 + 20-candle close breakout; heuristic confidence, not calibrated'}
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'")
        super().end_headers()
    def sendjson(self,body,status=200):
        raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_HEAD(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path not in ('/', '/index.html'):
            self.send_response(404);self.end_headers();return
        self.path='/index.html'
        return super().do_HEAD()
    def do_GET(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path=='/health':return self.sendjson({'ok':True})
        if p.path=='/api/status':return self.sendjson({'connected':bool(KEY),'provider':'Twelve Data','note':'API key configured; not proof of successful provider connection or futures coverage'})
        if p.path not in ('/api/analyze',):
            if p.path in ('/', '/index.html'):
                self.path='/index.html'
                return super().do_GET()
            return self.sendjson({'error':'Not found'},404)
        if not KEY:return self.sendjson({'error':'لم يتم إعداد مفتاح مزود البيانات على الخادم'},503)
        # Small per-client limiter to protect provider quota; no proxy trust assumptions.
        client=self.client_address[0]; now=time.monotonic()
        with LOCK:
            LAST_CALLS[client]=[t for t in LAST_CALLS.get(client,[]) if now-t<60]
            if len(LAST_CALLS[client])>=12:return self.sendjson({'error':'تجاوز حد الطلبات المؤقت، حاول بعد دقيقة'},429)
            LAST_CALLS[client].append(now)
            if len(LAST_CALLS)>2000:LAST_CALLS.clear()
        q=urllib.parse.parse_qs(p.query);symbol=q.get('symbol',[''])[0].upper().split(':')[-1].replace('!','');typ=q.get('type',['forex'])[0];tf=q.get('tf',['M5'])[0];direction=q.get('direction',['both'])[0]
        try:rr=float(q.get('rr',['3'])[0])
        except:rr=3
        if typ not in ('forex','futures','gold') or tf not in ('M1','M5','M15','M30') or direction not in ('both','buy','sell') or not (.5<=rr<=20) or not re.fullmatch(r'[A-Z0-9]{2,16}',symbol) :return self.sendjson({'error':'Invalid market parameters'},400)
        if typ in ('forex','gold'):
            if len(symbol)!=6 or not symbol.isalpha():return self.sendjson({'error':'Currency and spot metal symbols must be six letters'},400)
            provider_symbol=symbol[:3]+'/'+symbol[3:]
        else:provider_symbol=FUTURES.get(symbol,symbol)
        intervals={'M1':'1min','M5':'5min','M15':'15min','M30':'30min','H1':'1h','H4':'4h','D1':'1day'}
        try:
            out={};errors={}
            for frame in [tf,'M15','H1','H4','D1']:
                if frame in out:continue
                cachekey=(provider_symbol,frame);cached=CACHE.get(cachekey)
                if cached and time.time()-cached[0]<60:bars=cached[1]
                else:
                    url='https://api.twelvedata.com/time_series?'+urllib.parse.urlencode({'symbol':provider_symbol,'interval':intervals[frame],'outputsize':60,'apikey':KEY})
                    with urllib.request.urlopen(url,timeout=12) as res:payload=json.load(res)
                    if payload.get('status')=='error' or 'values' not in payload:raise ValueError(provider_error(payload))
                    bars=payload['values'];CACHE[cachekey]=(time.time(),bars)
                out[frame]=analyze(bars,rr,direction)
            return self.sendjson({'symbol':symbol,'type':typ,'provider':'Twelve Data','frames':out,'entryFrame':tf,'retrievedAt':int(time.time()),'warning':'Market data may be delayed. This is rule-based analysis, not a verified trade signal.'})
        except urllib.error.HTTPError as e:
            try: detail=provider_error(json.loads(e.read(4096).decode('utf-8','replace')))
            except Exception: detail='No additional provider details'
            return self.sendjson({'error':f'Twelve Data HTTP {e.code}: {detail}', 'provider_status':e.code},502)
        except (urllib.error.URLError, TimeoutError):return self.sendjson({'error':'تعذر الاتصال بمزود البيانات أو انتهت مهلة الطلب'},502)
        except ValueError as e:
            return self.sendjson({'error':str(e)[:300]},422)
        except Exception:return self.sendjson({'error':'تعذر إكمال التحليل؛ راجع سجلات الخادم'},502)
if __name__=='__main__':
    port=int(os.getenv('PORT','8000'));print(f'Big Ben read-only dashboard on port {port}');http.server.ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
