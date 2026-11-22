"""Evidence-based instrument picker and market gates. A watchlist/TV alert is NOT a data connection."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import json
import re

def forex_weekly_closed(now):
    """Conservative weekly closure; an open weekly window is not venue-open proof."""
    local=now.astimezone(ZoneInfo('America/New_York'))
    return (local.weekday()==5 or
            (local.weekday()==4 and local.hour>=17) or
            (local.weekday()==6 and local.hour<17))

def next_forex_open(now):
    """General Sunday 17:00 New York window, DST-aware, not holiday proof."""
    local=now.astimezone(ZoneInfo('America/New_York'))
    candidate=(local+timedelta(days=(6-local.weekday())%7)).replace(hour=17,minute=0,second=0,microsecond=0)
    if candidate<=local:candidate+=timedelta(days=7)
    return candidate.astimezone(ZoneInfo('Asia/Muscat')).isoformat()

SUPPORTED_CRYPTO=("BITSTAMP:BTCUSD","BITSTAMP:ETHUSD","BITSTAMP:XRPUSD",
                  "BITSTAMP:SOLUSD","BITSTAMP:LTCUSD","BITSTAMP:ADAUSD",
                  "BITSTAMP:DOGEUSD","BITSTAMP:BTCEUR","BITSTAMP:ETHEUR")

def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS native_market_open_state (
       symbol TEXT PRIMARY KEY, is_open INTEGER NOT NULL, updated_at TEXT NOT NULL
    )""")

def record_open_state(db,symbol,is_open,postgres=False,now=None):
    """Emit 'opened' only after a previous real closed observation."""
    mark="%s" if postgres else "?"
    previous=db.execute("SELECT is_open FROM native_market_open_state WHERE symbol="+mark,(symbol,)).fetchone()
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    db.execute("INSERT INTO native_market_open_state(symbol,is_open,updated_at) VALUES ("+
        ",".join([mark]*3)+") ON CONFLICT(symbol) DO UPDATE SET is_open=excluded.is_open,updated_at=excluded.updated_at",
        (symbol,int(bool(is_open)),stamp))
    return "opened" if previous is not None and previous[0]==0 and is_open else None

def connected(connection,now=None,postgres=False):
    now=now or datetime.now(timezone.utc)
    result=[]
    marker="%s" if postgres else "?"
    # Discover all verified FX records, rather than restricting the picker to probe defaults.
    pairs={row[0] for row in connection.execute("SELECT symbol FROM market_history_checks").fetchall()
           if isinstance(row[0],str) and re.fullmatch(r"[A-Z]{3}/[A-Z]{3}",row[0])}
    for pair in sorted(pairs):
        symbol="OANDA:"+pair.replace("/","")
        try:
            check=connection.execute("SELECT payload FROM market_history_checks WHERE symbol="+marker,(pair,)).fetchone()
            data=json.loads(check[0]) if check else {}
            row=connection.execute("SELECT MAX(time),COUNT(*) FROM market_candles WHERE provider='Twelve Data' AND symbol="+marker,(pair,)).fetchone()
            if not (row and row[0] and row[1]>=100 and data.get("symbol")==pair and
                    data.get("interval")=="5min" and data.get("adapter_version") and
                    data.get("state")=="CONNECTED"):
                continue
            stamp=datetime.fromisoformat(str(row[0]).replace("Z","+00:00")).astimezone(timezone.utc)
            age=(now-stamp).total_seconds()
            result.append({"symbol":symbol,"label":pair.replace("/"," / "),"asset_class":"forex",
              "provider":"Twelve Data","connected":True,
              "market_state":("عطلة نهاية الأسبوع لسوق العملات" if forex_weekly_closed(now) else
                              "شموع حديثة؛ حالة الجلسة غير مؤكدة" if 300<=age<=630 else "بيانات متأخرة؛ حالة الجلسة غير مؤكدة"),
              "market_open":False if forex_weekly_closed(now) else None,
              "latest_closed_candle":stamp.isoformat(),"fresh":300<=age<=630})
        except (ValueError,TypeError,KeyError,AttributeError):
            continue
    for symbol in SUPPORTED_CRYPTO:
        try:
            check=connection.execute("SELECT payload FROM market_history_checks WHERE symbol="+marker,(symbol,)).fetchone()
            data=json.loads(check[0]) if check else {}
            row=connection.execute("SELECT MAX(time),COUNT(*) FROM market_candles WHERE provider='Bitstamp' AND symbol="+marker,(symbol,)).fetchone()
            if not (row and row[0] and row[1]>=100 and data.get("symbol")==symbol and
                    data.get("provider")=="Bitstamp" and data.get("state")=="CONNECTED"):
                continue
            stamp=datetime.fromisoformat(str(row[0]).replace("Z","+00:00")).astimezone(timezone.utc)
            age=(now-stamp).total_seconds()
            result.append({"symbol":symbol,"label":symbol.split(":",1)[1],"asset_class":"crypto",
              "provider":"Bitstamp","connected":True,
              "market_state":"مفتوح ـ شموع محدثة" if 300<=age<=630 else "لا يوجد تحديث سعري حديث",
              "latest_closed_candle":stamp.isoformat(),"fresh":300<=age<=630})
        except (ValueError,TypeError,KeyError,AttributeError):
            continue
    # Deliberately omit futures and CFDs until provider-matched expiry/venue data is verified.
    return sorted(result,key=lambda d:(d["asset_class"]!="forex",d["label"]))

def gate(plan,now=None):
    """Never send new trade during stale/cancelled/no-source closed M5 snapshot."""
    now=now or datetime.now(timezone.utc)
    if isinstance(plan,dict) and (plan.get('reference_only') or (plan.get('source_provenance') or {}).get('reference_only')):
        return {'open':False,'reason':'المصدر احتياطي أو مرجعي؛ لا يثبت تغذية لايف مطابقة'}
    if isinstance(plan,dict) and plan.get('provider')=='TradingView Webhook':
        meta=plan.get('source_provenance') or {}
        try:
            bar=datetime.fromisoformat(meta['last_candle'].replace('Z','+00:00'))
            received=datetime.fromisoformat(meta['last_received_at'].replace('Z','+00:00'))
            valid=(bar.tzinfo is not None and received.tzinfo is not None
                   and meta.get('symbol')==plan.get('symbol') and meta.get('provider')=='TradingView Webhook'
                   and meta.get('source_identity_verified') is True
                   and plan.get('source_time')==meta['last_candle']
                   and 300<=(now-bar).total_seconds()<=630
                   and 0<=(now-received).total_seconds()<=330)
        except (KeyError,ValueError,TypeError,AttributeError):valid=False
        if not valid:return {'open':False,'reason':'شمعة TradingView غير حديثة أو غير مطابقة للأصل'}
        kind=plan.get('asset_class');symbol=str(plan.get('symbol',''))
        if kind in ('forex','metals','cfd') and forex_weekly_closed(now):
            return {'open':False,'reason':'عطلة نهاية الأسبوع؛ الافتتاح العام المتوقع بتوقيت عُمان: '+next_forex_open(now)}
        if kind=='futures':
            local=now.astimezone(ZoneInfo('America/New_York'))
            if local.weekday()==5 or (local.weekday()==4 and local.hour>=17) or (local.weekday()==6 and local.hour<18) or 17<=local.hour<18:
                return {'open':False,'reason':'فترة إغلاق أسبوعية أو صيانة عامة للعقود؛ يلزم استئناف شموع الشارت'}
        return {'open':True,'reason':'شمعة شارت TradingView حديثة مستلمة؛ لا يعتمد هذا المسار على المزود الخارجي'}
    if not isinstance(plan,dict) or plan.get("status")=="DATA_UNAVAILABLE":
        return {"open":False,"reason":"بيانات الأصل غير موثقة"}
    symbol=str(plan.get("symbol",""))
    if not (symbol.startswith("BITSTAMP:") or symbol.startswith("OANDA:")):
        return {"open":False,"reason":"لا توجد تغطية عقود موثقة لهذا الأصل"}
    expected="Bitstamp" if symbol.startswith("BITSTAMP:") else "Twelve Data"
    if plan.get("provider") != expected:
        return {"open":False,"reason":"مصدر السعر غير مطابق للأصل"}
    try:
        stamp=datetime.fromisoformat(plan["source_time"].replace("Z","+00:00"))
        if stamp.tzinfo is None:raise ValueError('missing_timezone')
        stamp=stamp.astimezone(timezone.utc)
        age=(now-stamp).total_seconds()
    except (KeyError,ValueError,TypeError,AttributeError):
        return {"open":False,"reason":"لا توجد شمعة حديثة"}
    if not 300<=age<=630:
        return {"open":False,"reason":"السوق مغلق أو شموع الأسعار متأخرة","age_seconds":int(age)}
    # Additional conservative forex weekly-closure guard. UTC Sat always closed.
    # Endpoints depend on broker/holidays, hence a recent real bar remains essential.
    if symbol.startswith("OANDA:") and forex_weekly_closed(now):
        return {"open":False,"reason":"عطلة نهاية الأسبوع لسوق العملات"}
    return {"open":True,"reason":"شموع مغلقة حديثة من المصدر المطابق","age_seconds":int(age)}

