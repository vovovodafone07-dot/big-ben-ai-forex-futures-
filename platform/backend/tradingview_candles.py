"""Authenticated chart-bar transport, independent of external quote vendors.

The HTTP caller authenticates first. A heartbeat containing only close is not
an OHLC bar. No fills, chart history or missing targets are reconstructed.
"""
import hashlib
import json
import math
import re
from datetime import datetime, timezone

PROVIDER='TradingView Webhook'
VALID=re.compile(r'^[A-Z0-9_]{2,40}:[A-Z0-9_.!/-]{1,50}$')

def stamp(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError()
        return dt.astimezone(timezone.utc)
    except (ValueError,TypeError):raise ValueError('طابع زمني غير صالح') from None

def validate(data, now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(data,dict) or data.get('schema')!='bigben.candle.v1' or str(data.get('timeframe'))!='5':
        raise ValueError('يلزم قالب شمعة TradingView لفريم خمس دقائق')
    symbol=data.get('symbol')
    if not isinstance(symbol,str) or not VALID.fullmatch(symbol):raise ValueError('رمز الشارت غير مؤهل')
    sent=stamp(data.get('time'));bar=stamp(data.get('bar_time'))
    if not 0<=(now-sent).total_seconds()<=180 or not 300<=(sent-bar).total_seconds()<=480:
        raise ValueError('الشمعة لم تغلق أو تأخرت؛ لم تُحدّث حداثة السعر')
    if bar.second or bar.microsecond or bar.minute%5:raise ValueError('وقت افتتاح شمعة غير مطابق')
    values={}
    for k in ('open','high','low','close','tick_size'):
        raw=data.get(k)
        if isinstance(raw,bool) or not isinstance(raw,(str,int,float)):raise ValueError('قيمة شمعة غير صالحة')
        try:v=float(raw)
        except (ValueError,TypeError,OverflowError):raise ValueError('قيمة شمعة غير صالحة') from None
        if not math.isfinite(v) or v<=0:raise ValueError('قيمة شمعة غير صالحة')
        values[k]=v
    if values['high']<max(values[k] for k in ('open','close','low')) or values['low']>min(values[k] for k in ('open','close','high')):
        raise ValueError('ترتيب OHLC غير صالح')
    row=dict(time=bar.isoformat(),**{k:values[k] for k in ('open','high','low','close')})
    key=hashlib.sha256((symbol+'|5|'+bar.isoformat()).encode()).hexdigest()
    return dict(schema='bigben.v1',event='HEARTBEAT',event_id='tv-candle:'+key,
                symbol=symbol,time=sent.isoformat(),bar_time=bar.isoformat(),
                timeframe='5',tick_size=values['tick_size'],close=values['close'],
                candle=row,provider=PROVIDER,broker_execution=False)

def ingest(db, event, postgres=False, now=None):
    now=now or datetime.now(timezone.utc);m='%s' if postgres else '?'
    row=event['candle'];symbol=event['symbol']
    prior=db.execute('SELECT open,high,low,close FROM market_candles WHERE provider='+m+' AND symbol='+m+' AND time='+m,
                     (PROVIDER,symbol,row['time'])).fetchone()
    values=tuple(row[k] for k in ('open','high','low','close'))
    if prior and tuple(prior)!=values:raise ValueError('وصلت قيم مختلفة للشمعة المحفوظة؛ لم تُستبدل')
    inserted=db.execute('INSERT INTO market_candles(provider,symbol,time,open,high,low,close,received_at) VALUES ('+','.join([m]*8)+') ON CONFLICT(provider,symbol,time) DO NOTHING',
                       (PROVIDER,symbol,row['time'],*values,now.isoformat())).rowcount==1
    # Out-of-order delivery cannot move the source watermark backwards.
    latest=db.execute('SELECT time,received_at FROM market_candles WHERE provider='+m+' AND symbol='+m+' ORDER BY time DESC LIMIT 1',(PROVIDER,symbol)).fetchone()
    meta=dict(provider=PROVIDER,symbol=symbol,interval='5min',adapter_version=1,
              checked_at=now.isoformat(),last_candle=latest[0],last_received_at=latest[1],
              tick_size=event['tick_size'],source_identity_verified=True,
              realtime_verified=False,reason='شموع الشارت المستلمة؛ ليست بث أسعار لكل تغير سعري')
    db.execute('INSERT INTO market_history_checks(symbol,checked_at,payload) VALUES ('+','.join([m]*3)+') ON CONFLICT(symbol) DO UPDATE SET checked_at=excluded.checked_at,payload=excluded.payload',
               ('tv:'+symbol,meta['checked_at'],json.dumps(meta,ensure_ascii=False)))
    return inserted

def read(db, symbol, postgres=False):
    m='%s' if postgres else '?'
    row=db.execute('SELECT payload FROM market_history_checks WHERE symbol='+m,('tv:'+symbol,)).fetchone()
    if not row:return [],{}
    meta=json.loads(row[0])
    rows=db.execute('SELECT time,open,high,low,close FROM market_candles WHERE provider='+m+' AND symbol='+m+' ORDER BY time DESC LIMIT 1000',(PROVIDER,symbol)).fetchall()
    return rows,meta

def fresh(meta, now=None):
    now=now or datetime.now(timezone.utc)
    try:
        return (meta.get('provider')==PROVIDER and meta.get('source_identity_verified') is True
                and 300<=(now-stamp(meta['last_candle'])).total_seconds()<=630
                and 0<=(now-stamp(meta['last_received_at'])).total_seconds()<=330)
    except (ValueError,TypeError,KeyError):return False

def template():
    return dict(schema='bigben.candle.v1',token='ضع_رمز_الخادم_بشكل_آمن',
                symbol='{{exchange}}:{{ticker}}',timeframe='{{interval}}',
                time='{{timenow}}',bar_time='{{time}}',open='{{open}}',
                high='{{high}}',low='{{low}}',close='{{close}}',
                tick_size='ضع_أصغر_حركة_سعرية_للرمز')
