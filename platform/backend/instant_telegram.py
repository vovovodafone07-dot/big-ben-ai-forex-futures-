"""Native-analysis Telegram delivery; read-only, deduped, verified provider only.

The sender is invoked immediately after native analysis in the API request.
No artificial sleeps, no TradingView requirement, no broker integration.
A durable fingerprint is reserved before sending so same trade isn't delivered
twice by concurrent requests. Failures may retry on a subsequent analysis.
"""
import hashlib
import html
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SENDABLE = frozenset(("READY", "CONDITIONAL", "NEWS_CAUTION"))
SYMBOL = re.compile(r"^[A-Z0-9_.-]{2,24}:[A-Z0-9_!./-]{2,28}$")

def migrate(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS native_telegram_alerts (
      fingerprint TEXT PRIMARY KEY,
      symbol TEXT NOT NULL,
      mode TEXT NOT NULL,
      status TEXT NOT NULL,
      delivery TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )""")

def eligible(plan):
    if not isinstance(plan,dict) or plan.get("status") not in SENDABLE:
        return False
    if not SYMBOL.fullmatch(str(plan.get("symbol",""))):
        return False
    if plan.get("mode") not in ("scalp","swing") or plan.get("provider") not in ("Twelve Data","Bitstamp"):
        return False
    if plan.get("broker_execution") is not False:
        return False
    if plan.get("technical_direction") not in ("BUY","SELL"):
        return False
    if not isinstance(plan.get("source_time"),str):
        return False
    if plan.get("entry") is None or plan.get("sl") is None:
        return False
    targets=plan.get("targets")
    if not isinstance(targets,list) or len(targets)!=3:
        return False
    try:
        values=[float(plan["entry"]),float(plan["sl"])]+[float(t["price"]) for t in targets]
        from math import isfinite
        if not all(isfinite(x) and x>0 for x in values):
            return False
        if plan["technical_direction"]=="BUY" and not (values[1]<values[0]<values[2]<values[3]<values[4]):
            return False
        if plan["technical_direction"]=="SELL" and not (values[1]>values[0]>values[2]>values[3]>values[4]):
            return False
    except (ValueError,TypeError,KeyError):
        return False
    return True

def fingerprint(plan, chat):
    if not eligible(plan):
        raise ValueError("not_a_verified_research_plan")
    if not re.fullmatch(r"-?[0-9]{5,20}",str(chat)):
        raise ValueError("chat_not_configured")
    # Candle timestamp is intentionally excluded: stable levels are not NEW trades
    # merely because the provider has delivered one more closed M5 candle.
    subset={k:plan.get(k) for k in ("symbol","mode","status","technical_direction","entry","sl")}
    subset["targets"]=[t["price"] for t in plan["targets"]]
    subset["confirmed"]=bool((plan.get("confirmation") or {}).get("confirmed"))
    subset["chat_hash"]=hashlib.sha256(str(chat).encode()).hexdigest()
    return hashlib.sha256(json.dumps(subset,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def _f(x):
    return format(float(x),".8f").rstrip("0").rstrip(".")

def _esc(s):
    return html.escape(str(s),quote=True)

def message(plan, now=None):
    if not eligible(plan):
        raise ValueError("not_sendable")
    now=now or datetime.now(timezone.utc)
    symbol=plan["symbol"].split(":",1)[1]
    asset=plan.get("instrument",{}).get("asset_class", "unverified")
    asset_label={"crypto":"Spot","forex":"Forex","futures":"Futures","cfd":"CFD"}.get(asset,asset)
    buy=plan["technical_direction"]=="BUY"
    status=plan["status"]
    kind=("✅ صفقة بحثية مؤكدة الشروط" if status=="READY" else
          "🟡 سيناريو مشروط — ليس دخولاً الآن" if status=="CONDITIONAL" else
          "⚠️ تحذير خبر — يمنع الدخول حتى زوال القيد")
    bias={"BULLISH":"صاعد","BEARISH":"هابط","RANGING":"عرضي"}.get(plan.get("bias"),"غير محسوم")
    tf="H1/H4 سياق · H1 تنفيذ" if plan["mode"]=="swing" else "H4/H1 سياق · M15/M5 تنفيذ"
    direction="شراء | LONG" if buy else "بيع | SHORT"
    c=plan.get("confirmation") or {}
    evidence=plan.get("evidence") or {}
    news=plan.get("news") or {}
    related=news.get("related_events") or []
    upcoming=related[0] if isinstance(related,list) and related and isinstance(related[0],dict) else None
    news_detail=(" | "+str(upcoming.get("title",""))[:100]+" | خلال "+str(upcoming.get("minutes_until","?"))+" دقيقة") if upcoming else ""
    parts=[
      ("🔵" if buy else "🔴")+" <b>"+direction+" | "+_esc(symbol)+" ("+_esc(asset_label)+")</b>",
      "━━━━━━━━━━━━━━━━━━",
      "<b>"+_esc(kind)+"</b>",
      "📌 <b>الباياس:</b> "+bias+" | <b>الإطار:</b> "+tf,
      "🎯 <b>الدخول:</b> "+_f(plan["entry"])+( " (مشروط)" if status!="READY" else ""),
      "🛑 <b>وقف الخسارة SL:</b> "+_f(plan["sl"]),
      "✅ <b>الأهداف:</b>",
    ]
    for t in plan["targets"]:
        parts.append("• <b>"+_esc(t.get("name","TP"))+":</b> "+_f(t["price"])+" (هدف بحثي؛ "+_esc(t.get("reason","R-multiple"))+")")
    parts.extend([
      "📋 <b>شروط الدخول:</b>",
      "• "+_esc(c.get("type","إغلاق فريم التنفيذ"))+" "+("فوق" if buy else "تحت")+" "+_f(c.get("level",plan["entry"]))+
          (" · متحقق" if c.get("confirmed") else " · غير متحقق بعد"),
      "• السيولة: "+_esc(evidence.get("LIQUIDITY_SWEEP","غير مثبت"))+" | FVG: "+_esc((evidence.get("FVG") or {}).get("type","غير مثبت") if isinstance(evidence.get("FVG"),dict) else evidence.get("FVG","غير مثبت")),
      "• <b>الإبطال:</b> "+("هبوط" if buy else "صعود")+" السعر إلى "+_f(plan["sl"])+" قبل تحقق الدخول",
      "📰 <b>الأخبار:</b> "+_esc(news.get("state","NOT_VERIFIED")+news_detail)+" — لا يصنّف اتجاه الخبر دون بيانات ونتائج موثقة",
      "📡 <b>المصدر:</b> "+_esc(plan["provider"])+" | شمعة المصدر: "+_esc(plan["source_time"]),
      "⏱️ <b>وقت الإرسال:</b> "+now.astimezone(ZoneInfo("Asia/Muscat")).strftime("%Y-%m-%d %H:%M:%S")+" (مسقط)",
      "⚠️ بحث وتحليل فقط؛ لا تنفيذ أوامر ولا ضمان للنتائج."
    ])
    return "\n".join(parts)

def claim(connection,plan,chat,postgres=False,now=None):
    if not eligible(plan):
        return None
    key=fingerprint(plan,chat)
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    mark="%s" if postgres else "?"
    params=(key,plan["symbol"],plan["mode"],plan["status"],"sending",stamp,stamp)
    result=connection.execute("INSERT INTO native_telegram_alerts(fingerprint,symbol,mode,status,delivery,created_at,updated_at) VALUES ("+
                    ",".join([mark]*7)+") ON CONFLICT(fingerprint) DO NOTHING",params)
    if result.rowcount==1:return key
    retry=connection.execute("UPDATE native_telegram_alerts SET delivery='sending',updated_at="+mark+
       " WHERE fingerprint="+mark+" AND delivery IN ('failed','not_configured')",(stamp,key))
    return key if retry.rowcount==1 else None

def finish(connection,key,result,postgres=False):
    if result not in ("sent","failed","not_configured"):
        raise ValueError("invalid_delivery_state")
    mark="%s" if postgres else "?"
    connection.execute("UPDATE native_telegram_alerts SET delivery="+mark+",updated_at="+mark+
                       " WHERE fingerprint="+mark+" AND delivery='sending'",
                       (result,datetime.now(timezone.utc).isoformat(),key))

def send(plan,token,chat,opener=None,timeout=5):
    if not eligible(plan):
        return "not_eligible"
    if not token or not re.fullmatch(r"-?[0-9]{5,20}",str(chat)):
        return "not_configured"
    opener=opener or urllib.request.urlopen
    payload=json.dumps({"chat_id":chat,"text":message(plan),"parse_mode":"HTML",
                        "disable_web_page_preview":True},ensure_ascii=False).encode("utf-8")
    request=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=payload,
                                   method="POST",headers={"Content-Type":"application/json"})
    try:
        with opener(request,timeout=timeout) as response:
            data=response.read(2048)
            return "sent" if response.status==200 and json.loads(data).get("ok") is True else "failed"
    except (ValueError,KeyError,TypeError,TimeoutError,OSError,urllib.error.URLError):
        return "failed"
