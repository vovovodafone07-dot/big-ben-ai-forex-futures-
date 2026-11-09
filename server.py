"""Read-only Big Ben market data proxy. Requires TWELVEDATA_API_KEY environment variable."""
import os, json, urllib.request, urllib.error, urllib.parse, http.server, pathlib, time, statistics, threading, re
ROOT=pathlib.Path(__file__).parent
KEY=os.getenv('TWELVEDATA_API_KEY','').strip()
LOCK=threading.Lock()
WEBHOOK_SECRET=os.getenv('TV_WEBHOOK_SECRET','').strip()
TV_EVENTS={}
TV_EVENTS_LOCK=threading.Lock()
TV_ALLOWED={'buy','sell','wait'}
TV_TYPES={'forex','futures','gold'}

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

def lookup_symbol(symbol):
    """Look up exact instrument symbols without silently substituting CFDs/ETFs."""
    try:
        url='https://api.twelvedata.com/symbol_search?'+urllib.parse.urlencode({'symbol':symbol,'outputsize':20,'apikey':KEY})
        with urllib.request.urlopen(url,timeout=8) as res: result=json.load(res)
        rows=result.get('data',[]) if isinstance(result,dict) else []
        return [{'symbol':str(x.get('symbol',''))[:32], 'name':str(x.get('instrument_name',''))[:90],
                 'exchange':str(x.get('exchange',''))[:50], 'type':str(x.get('instrument_type',''))[:40]}
                for x in rows[:10] if isinstance(x,dict)]
    except Exception:return []

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
    def webhook_reject(self, reason, status=400):
        # Log only a fixed diagnostic code. Never log request body or secret.
        print('TV_WEBHOOK_REJECT reason='+reason+' status='+str(status), flush=True)
        return self.sendjson({'error':reason},status)
    def do_POST(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path!='/api/tradingview/webhook':return self.sendjson({'error':'Not found'},404)
        if not WEBHOOK_SECRET:return self.webhook_reject('Webhook not configured',503)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=4096:return self.webhook_reject('Invalid payload length',413)
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):return self.webhook_reject('Invalid JSON',400)
            import hmac
            if not hmac.compare_digest(str(payload.get('secret','')),WEBHOOK_SECRET):return self.webhook_reject('Unauthorized',401)
            # TradingView may send a modified ticker ID as a JSON-encoded string,
            # e.g. {"settlement-as-close":true,"symbol":"CME_MINI:MNQ1!"}.
            # Extract only the canonical symbol; never trust arbitrary nested data.
            raw_symbol=payload.get('symbol','')
            if isinstance(raw_symbol,str) and raw_symbol.lstrip().startswith('{'):
                try:
                    modified=json.loads(raw_symbol)
                    raw_symbol=modified.get('symbol','') if isinstance(modified,dict) else ''
                except (ValueError,TypeError):
                    return self.webhook_reject('Invalid modified ticker',400)
            symbol=raw_symbol.upper().strip() if isinstance(raw_symbol,str) else ''
            if not re.fullmatch(r'[A-Z0-9_:.!/-]{2,40}',symbol):return self.webhook_reject('Invalid symbol',400)
            signal=str(payload.get('signal','wait')).lower()
            if signal not in TV_ALLOWED:return self.webhook_reject('Invalid signal',400)
            kind=str(payload.get('type','futures')).lower()
            # Older TradingView alert snapshots can carry a chart-type label instead
            # of our market classification. Normalize only recognizable symbols.
            if kind not in TV_TYPES:
                base=symbol.split(':')[-1]
                if base.startswith(('XAU','XAG')):kind='gold'
                elif re.fullmatch(r'[A-Z]{6}',base):kind='forex'
                elif re.fullmatch(r'(?:M?ES|M?NQ|M?YM|M?RTY|6[A-Z]|CL|GC|SI|MBT|BTC)[A-Z0-9!]*',base):kind='futures'
                else:return self.webhook_reject('Invalid market type',400)
            def number(key):
                v=payload.get(key)
                if v is None or v=='':return None
                f=float(v)
                if not (-1e12<f<1e12):raise ValueError('Invalid price')
                return f
            entry=number('entry');stop=number('stop');targets=[number('tp1'),number('tp2'),number('tp3')]
            if signal!='wait' and (entry is None or stop is None or any(v is None for v in targets)):
                return self.webhook_reject('Missing setup levels',400)
            trends={k:str(payload.get(k,'neutral')).lower() for k in ('m15','h1','h4','d1')}
            if any(v not in ('buy','sell','neutral') for v in trends.values()):return self.webhook_reject('Invalid trend',400)
            event={'symbol':symbol,'type':kind,'signal':signal,'entry':entry,'stop':stop,'targets':targets,'trends':trends,'bar_time':str(payload.get('bar_time',''))[:60],'received_at':int(time.time()),'source':'TradingView webhook'}
            with TV_EVENTS_LOCK:
                TV_EVENTS[symbol]=event
                if signal!='wait':TV_EVENTS[symbol+'#last_setup']=event
                if len(TV_EVENTS)>250:
                    oldest=min(TV_EVENTS,key=lambda k:TV_EVENTS[k]['received_at']);TV_EVENTS.pop(oldest,None)
            print('TV_WEBHOOK_ACCEPT symbol='+symbol+' signal='+signal, flush=True)
            return self.sendjson({'ok':True,'symbol':symbol,'signal':signal})
        except (ValueError,TypeError,UnicodeDecodeError,json.JSONDecodeError):return self.webhook_reject('Invalid payload',400)
        except (BrokenPipeError, ConnectionResetError):
            print('TV_WEBHOOK_CLIENT_DISCONNECTED', flush=True)
    def do_HEAD(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path not in ('/', '/index.html'):
            self.send_response(404);self.end_headers();return
        self.path='/index.html'
        return super().do_HEAD()
    def do_GET(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path=='/health':return self.sendjson({'ok':True})
        if p.path=='/api/tradingview/latest':
            with TV_EVENTS_LOCK:events=sorted(TV_EVENTS.values(),key=lambda x:x['received_at'],reverse=True)
            return self.sendjson({'connected':bool(WEBHOOK_SECRET),'events':events,'note':'In-memory data resets on deploy/restart. Events only arrive from configured TradingView alerts.'})
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
            return self.sendjson({'error':f'Twelve Data HTTP {e.code}: {detail}' + (' | لم يتعرف المزود على رمز عقد الفيوتشرز. يجب تحديد رمز عقد مدعوم من المصدر، ولا يمكن استخدام بديل مختلف دون موافقتك.' if e.code==404 and typ=='futures' else ''), 'provider_status':e.code, 'symbol':provider_symbol, 'symbol_matches':lookup_symbol(symbol) if e.code==404 and typ=='futures' else []},422 if e.code==404 else 502)
        except (urllib.error.URLError, TimeoutError):return self.sendjson({'error':'تعذر الاتصال بمزود البيانات أو انتهت مهلة الطلب'},502)
        except ValueError as e:
            return self.sendjson({'error':str(e)[:300]},422)
        except Exception:return self.sendjson({'error':'تعذر إكمال التحليل؛ راجع سجلات الخادم'},502)
if __name__=='__main__':
    port=int(os.getenv('PORT','8000'));print(f'Big Ben read-only dashboard on port {port}');http.server.ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
