"""Durable authorized watchlist snapshot; unrelated platform preferences excluded."""
import json
import re
from datetime import datetime, timezone

KEY = '__tradingview_watchlist_v1__'
VALID = re.compile(r'^[A-Z0-9_]{2,40}:[A-Z0-9_.!/-]{1,50}$')


def validate(symbols):
    if not isinstance(symbols,list) or not 1 <= len(symbols) <= 1000:
        raise ValueError('قائمة TradingView غير صالحة أو فارغة؛ لم تُستبدل القائمة السابقة')
    result=[]
    for symbol in symbols:
        if not isinstance(symbol,str) or not VALID.fullmatch(symbol):
            raise ValueError('رمز TradingView غير مؤهل بمصدره')
        if symbol not in result:result.append(symbol)
    return result


def snapshot(db, postgres=False):
    m = '%s' if postgres else '?'
    row=db.execute('SELECT payload FROM market_history_checks WHERE symbol='+m,(KEY,)).fetchone()
    return json.loads(row[0]) if row else None


def sync(db, payload, postgres=False, now=None):
    if not isinstance(payload,dict) or payload.get('schema')!='bigben.watchlist.v1':
        raise ValueError('نسخة حمولة المزامنة غير صالحة')
    symbols=validate(payload.get('symbols'))
    revision=payload.get('revision');ident=payload.get('watchlist_id')
    if type(revision) is not int or revision < 1 or not re.fullmatch(r'[0-9]{1,20}',str(ident)):
        raise ValueError('معرف القائمة أو رقم المراجعة غير صالح')
    prior=snapshot(db,postgres)
    if prior and revision <= prior['revision']:
        if revision==prior['revision'] and str(ident)==prior['watchlist_id'] and symbols==prior['symbols']:
            return prior
        raise ValueError('مراجعة المزامنة أقدم من القائمة المحفوظة')
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    value=dict(schema='bigben.watchlist.v1',watchlist_id=str(ident),revision=revision,
               symbols=symbols,synced_at=stamp,source='TradingView authorized snapshot')
    m='%s' if postgres else '?'
    # Revision check and update remain atomic for simultaneous HTTP syncs.
    if prior:
        changed=db.execute('UPDATE market_history_checks SET checked_at='+m+',payload='+m+' WHERE symbol='+m+' AND payload='+m,
            (stamp,json.dumps(value),KEY,json.dumps(prior))).rowcount
    else:
        changed=db.execute('INSERT INTO market_history_checks(symbol,checked_at,payload) VALUES ('+','.join([m]*3)+') ON CONFLICT(symbol) DO NOTHING',
                           (KEY,stamp,json.dumps(value))).rowcount
    if changed != 1:raise ValueError('تغيرت القائمة أثناء المزامنة؛ أعد قراءة المراجعة')
    return value


def members(db, configured=(), postgres=False):
    value=snapshot(db,postgres)
    symbols=set(value['symbols'] if value else [s for s in configured if isinstance(s,str) and VALID.fullmatch(s)])
    if value:
        # The owner also authorizes symbols added to TradingView alerts. Only
        # newly authenticated events AFTER this snapshot may add membership.
        m='%s' if postgres else '?'
        for (symbol,) in db.execute('SELECT symbol FROM tradingview_discovered_symbols WHERE last_seen>'+m+" AND source='TradingView Webhook'",(value['synced_at'],)).fetchall():
            if VALID.fullmatch(symbol):symbols.add(symbol)
    return symbols
