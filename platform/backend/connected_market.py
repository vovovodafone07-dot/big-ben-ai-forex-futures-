"""Evidence-based instrument picker and market gates. A watchlist/TV alert is NOT a data connection."""
from datetime import datetime,timezone
import json

SUPPORTED_FOREX={"EUR/USD":"OANDA:EURUSD","GBP/USD":"OANDA:GBPUSD","USD/JPY":"OANDA:USDJPY"}
SUPPORTED_CRYPTO=("BITSTAMP:BTCUSD","BITSTAMP:ETHUSD","BITSTAMP:XRPUSD",
                  "BITSTAMP:SOLUSD","BITSTAMP:LTCUSD","BITSTAMP:ADAUSD",
                  "BITSTAMP:DOGEUSD","BITSTAMP:BTCEUR","BITSTAMP:ETHEUR")

def connected(connection,now=None,postgres=False):
    now=now or datetime.now(timezone.utc)
    result=[]
    marker="%s" if postgres else "?"
    for pair,symbol in SUPPORTED_FOREX.items():
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
              "market_state":"مفتوح ـ شموع محدثة" if 300<=age<=630 else "مغلق أو البيانات متأخرة",
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
    if not isinstance(plan,dict) or plan.get("status")=="DATA_UNAVAILABLE":
        return {"open":False,"reason":"بيانات الأصل غير موثقة"}
    symbol=str(plan.get("symbol",""))
    if not (symbol.startswith("BITSTAMP:") or symbol.startswith("OANDA:")):
        return {"open":False,"reason":"لا توجد تغطية عقود موثقة لهذا الأصل"}
    if plan.get("provider") not in ("Bitstamp","Twelve Data"):
        return {"open":False,"reason":"مصدر السعر غير مطابق للأصل"}
    try:
        stamp=datetime.fromisoformat(plan["source_time"].replace("Z","+00:00")).astimezone(timezone.utc)
        age=(now-stamp).total_seconds()
    except (KeyError,ValueError,TypeError,AttributeError):
        return {"open":False,"reason":"لا توجد شمعة حديثة"}
    if not 300<=age<=630:
        return {"open":False,"reason":"السوق مغلق أو شموع الأسعار متأخرة","age_seconds":int(age)}
    # Additional conservative forex weekly-closure guard. UTC Sat always closed.
    # Endpoints depend on broker/holidays, hence a recent real bar remains essential.
    if symbol.startswith("OANDA:") and now.weekday()==5:
        return {"open":False,"reason":"عطلة نهاية الأسبوع لسوق العملات"}
    return {"open":True,"reason":"شموع مغلقة حديثة من المصدر المطابق","age_seconds":int(age)}
