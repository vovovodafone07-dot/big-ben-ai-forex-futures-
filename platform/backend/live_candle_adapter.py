"""Bounded M5 ingestion: Twelve Data first, yfinance reference fallback.

Provider coverage, bar freshness and exact TradingView feed equivalence are
different facts. This adapter never authorizes Telegram trade delivery.
"""
import json
import logging
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone, timedelta

VERSION = 1
FUTURES = {
    'CME_MINI:NQ1!': ('NQ=F', .25, 'CME'),
    'CME_MINI:MNQ1!': ('MNQ=F', .25, 'CME'),
    'CME_MINI:ES1!': ('ES=F', .25, 'CME'),
    'CME_MINI:MES1!': ('MES=F', .25, 'CME'),
    'COMEX:GC1!': ('GC=F', .1, 'CMX'),
    'COMEX_MINI:MGC1!': ('MGC=F', .1, 'CMX'),
    'NYMEX:CL1!': ('CL=F', .01, 'NYM'),
    'NYMEX:MCL1!': ('MCL=F', .01, 'NYM'),
    'CBOT_MINI:MYM1!': ('MYM=F', 1., 'CBT'),
    'CME:MBT1!': ('MBT=F', 5., 'CME'),
}
REASONS = {
    'not_configured': 'مفتاح Twelve Data غير مهيأ',
    'unsupported': 'لا توجد مطابقة موثقة لهذا الأصل لدى المصدرين المحددين',
    'entitlement': 'صلاحية البيانات غير متاحة في الحساب الحالي',
    'rate_limit': 'بلغ المصدر حد الطلبات؛ لا توجد ترقية مدفوعة',
    'provider_failure': 'تعذر جلب الشموع من المصدر',
    'identity': 'هوية الأصل أو الفاصل الزمني في رد المصدر غير مطابقين',
    'invalid_candles': 'الشموع أو طوابعها الزمنية غير صالحة',
    'no_closed_candles': 'لا توجد شموع مغلقة موثقة',
    'budget': 'اكتملت ميزانية الجلب المجانية المحلية لهذا المصدر',
}


class CandleError(ValueError):
    pass


def mapping(symbol):
    """No full-contract substitution for micros, no CFD-to-index substitution."""
    if symbol in FUTURES:
        yahoo, tick, exchange = FUTURES[symbol]
        return dict(yahoo=yahoo, twelve=None, kind='futures', tick=tick,
                    exchange=exchange, reference_only=True)
    if re.fullmatch(r'OANDA:[A-Z]{6}', symbol or ''):
        pair = symbol.split(':')[1]
        if pair[:3] in ('XAU', 'XAG'):
            return None
        return dict(twelve=pair[:3]+'/'+pair[3:], yahoo=pair+'=X', kind='forex',
                    tick=.001 if pair.endswith('JPY') else .00001,
                    reference_only=True)
    if symbol == 'BITSTAMP:BTCUSD':
        return dict(twelve='BTC/USD', yahoo='BTC-USD', kind='crypto', tick=.01,
                    reference_only=True)
    # Broker CFDs cannot be reconstructed from a cash index or another future.
    return None


def normalize(rows, now):
    if now.tzinfo is None or not rows or len(rows) > 3000:
        raise CandleError('invalid_candles')
    closed = []
    last = None
    for item in rows:
        try:
            stamp = datetime.fromisoformat(str(item['time']).replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError()
            stamp = stamp.astimezone(timezone.utc)
            if stamp > now:
                raise ValueError()
            if (now-stamp).total_seconds()<300:
                continue
            if stamp.second or stamp.microsecond or stamp.minute % 5:
                raise ValueError()
            if last is not None and stamp <= last:
                raise ValueError()
            last = stamp
            prices = {k: float(item[k]) for k in ('open', 'high', 'low', 'close')}
            if any(isinstance(item[k], bool) for k in prices):
                raise ValueError()
            if not all(math.isfinite(v) and v > 0 for v in prices.values()):
                raise ValueError()
            if prices['high'] < max(prices.values()) or prices['low'] > min(prices.values()):
                raise ValueError()
            if (now-stamp).total_seconds() >= 300:
                closed.append(dict(time=stamp.isoformat(), **prices))
        except (ValueError, TypeError, KeyError, OverflowError):
            raise CandleError('invalid_candles') from None
    if not closed:
        raise CandleError('no_closed_candles')
    return closed[-1000:]


def twelve(symbol, key, now, opener=None):
    spec = mapping(symbol)
    if not spec or not spec['twelve']:
        raise CandleError('unsupported')
    if not key:
        raise CandleError('not_configured')
    params = urllib.parse.urlencode(dict(symbol=spec['twelve'], apikey=key,
        interval='5min', timezone='UTC', order='asc', outputsize=1000))
    request = urllib.request.Request('https://api.twelvedata.com/time_series?'+params,
        headers={'User-Agent': 'BigBenAIPro-Candles/1'})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=10) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError()
        data = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise CandleError({401:'entitlement',403:'entitlement',429:'rate_limit'}.get(error.code,'provider_failure')) from None
    except Exception:
        raise CandleError('provider_failure') from None
    if not isinstance(data, dict):
        raise CandleError('identity')
    if data.get('status') == 'error':
        raise CandleError({'401':'entitlement','403':'entitlement','429':'rate_limit'}.get(str(data.get('code')),'provider_failure'))
    meta = data.get('meta') or {}
    kind = 'Physical Currency' if spec['kind']=='forex' else 'Digital Currency'
    if not isinstance(meta,dict) or meta.get('symbol') != spec['twelve'] or meta.get('interval') != '5min' or meta.get('type') != kind:
        raise CandleError('identity')
    try:
        rows = [dict(time=datetime.strptime(r['datetime'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).isoformat(),
                     **{k:r[k] for k in ('open','high','low','close')}) for r in data['values']]
    except (KeyError, TypeError, ValueError):
        raise CandleError('invalid_candles') from None
    return normalize(rows,now), 'Twelve Data', spec['twelve']


def yahoo(symbol, now, factory=None):
    spec = mapping(symbol)
    if not spec or not spec.get('yahoo'):
        raise CandleError('unsupported')
    try:
        if factory is None:
            import yfinance as yf
            factory = yf.Ticker
        # yfinance may log provider messages. Disable its own logger only;
        # never print returned exceptions or enable its debug HTTP logger.
        logging.getLogger('yfinance').disabled = True
        ticker = factory(spec['yahoo'])
        frame = ticker.history(period='5d', interval='5m', auto_adjust=False,
            back_adjust=False, repair=False, actions=False, timeout=10)
        meta = ticker.get_history_metadata()
        expected = {'futures':'FUTURE','crypto':'CRYPTOCURRENCY','forex':'CURRENCY'}[spec['kind']]
        if (not isinstance(meta,Mapping) or meta.get('symbol') != spec['yahoo'] or
            meta.get('instrumentType') != expected or
            meta.get('dataGranularity') != '5m' or
            (spec['kind']=='futures' and meta.get('exchangeName') != spec['exchange'])):
            raise CandleError('identity')
        rows = [dict(time=stamp.to_pydatetime().isoformat(),
                     **{k:row[k.title()] for k in ('open','high','low','close')})
                for stamp,row in frame.iterrows()]
        return normalize(rows,now), 'yfinance / Yahoo Finance', spec['yahoo']
    except CandleError:
        raise
    except Exception:
        raise CandleError('provider_failure') from None


def fetch(symbol, key='', now=None, *, primary=None, fallback=None):
    now = now or datetime.now(timezone.utc)
    spec = mapping(symbol)
    errors = []
    saved = None
    for name, call in [('Twelve Data',primary or twelve), ('yfinance / Yahoo Finance',fallback or yahoo)]:
        try:
            if name == 'Twelve Data':
                rows, provider, provider_symbol = call(symbol,key,now)
            else:
                rows, provider, provider_symbol = call(symbol,now)
            # Also validate injected/test adapters and reject stale primary in
            # favour of fallback; never extend the M5 freshness threshold.
            rows = normalize(rows,now)
            age = (now-datetime.fromisoformat(rows[-1]['time'])).total_seconds()
            meta = dict(symbol=symbol, provider=provider, provider_symbol=provider_symbol,
                interval='5min', adapter_version=VERSION, checked_at=now.isoformat(),
                last_candle=rows[-1]['time'], candles_received=len(rows),
                source_age_seconds=int(age), fresh=300<=age<=630,
                state='REFERENCE' if 300<=age<=630 else 'STALE',
                reference_only=True, realtime_verified=False, exact_feed_verified=False,
                tick_size=spec['tick'], errors=errors,
                reason='شموع مرجعية من مصدر بديل؛ لا تثبت سعر TradingView اللحظي' if name=='Twelve Data' else 'بيانات احتياطية؛ التأخير ومطابقة عقد التداول المستمر غير مثبتين')
            if meta['fresh'] or name != 'Twelve Data':
                return rows,meta
            saved = (rows, meta)
            errors.append(dict(provider=name, reason='شموع المصدر الأساسي متقادمة'))
        except CandleError as error:
            errors.append(dict(provider=name,reason=REASONS.get(str(error),REASONS['provider_failure'])))
    if saved:
        saved[1]['errors'] = errors
        return saved
    return [],dict(symbol=symbol,provider=None,state='UNAVAILABLE',checked_at=now.isoformat(),
                   fresh=False,reference_only=True,realtime_verified=False,
                   reason=REASONS['unsupported'] if not spec else REASONS['provider_failure'],errors=errors)


def store(db, symbol, rows, meta, postgres=False):
    m = '%s' if postgres else '?'
    for r in rows:
        db.execute('INSERT INTO market_candles(provider,symbol,time,open,high,low,close,received_at) VALUES ('+','.join([m]*8)+') ON CONFLICT(provider,symbol,time) DO NOTHING',
                   (meta['provider'],symbol,r['time'],r['open'],r['high'],r['low'],r['close'],meta['checked_at']))
    db.execute('INSERT INTO market_history_checks(symbol,checked_at,payload) VALUES ('+','.join([m]*3)+') ON CONFLICT(symbol) DO UPDATE SET checked_at=excluded.checked_at,payload=excluded.payload',
               ('adapter:'+symbol,meta['checked_at'],json.dumps(meta,ensure_ascii=False)))


def read(db, symbol, postgres=False):
    m = '%s' if postgres else '?'
    record = db.execute('SELECT payload FROM market_history_checks WHERE symbol='+m,('adapter:'+symbol,)).fetchone()
    if not record:
        return [],{}
    meta = json.loads(record[0])
    rows = db.execute('SELECT time,open,high,low,close FROM market_candles WHERE provider='+m+' AND symbol='+m+' ORDER BY time DESC LIMIT 1000',(meta.get('provider'),symbol)).fetchall()
    return rows,meta


def reserve(db, provider, now, postgres=False):
    """Durable free-plan budget, also counts failed attempts across restarts.

    Uses the existing backed-up receipt table; ON CONFLICT handles concurrent
    callers conservatively (a race may skip a call, never grants extra calls).
    """
    m = '%s' if postgres else '?'
    prefix = 'candles:'+provider+':'+now.date().isoformat()+':'
    count = db.execute('SELECT COUNT(*) FROM telegram_bot_receipts WHERE id LIKE '+m,(prefix+'%',)).fetchone()[0]
    limit = 400 if provider=='twelve' else 144
    recent = db.execute('SELECT COUNT(*) FROM telegram_bot_receipts WHERE id LIKE '+m+' AND created_at>='+m,
                        (prefix+'%',(now-timedelta(minutes=1)).isoformat())).fetchone()[0]
    if count >= limit or recent >= (6 if provider=='twelve' else 3):
        return False
    return db.execute('INSERT INTO telegram_bot_receipts(id,status,created_at) VALUES ('+','.join([m]*3)+') ON CONFLICT(id) DO NOTHING',
                      (prefix+str(count),'reserved',now.isoformat())).rowcount==1
