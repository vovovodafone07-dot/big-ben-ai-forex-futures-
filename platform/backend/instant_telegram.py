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
import importlib.util
from pathlib import Path
_journal_spec=importlib.util.spec_from_file_location('telegram_journal',Path(__file__).with_name('native_trade_journal.py'))
_journal=importlib.util.module_from_spec(_journal_spec);_journal_spec.loader.exec_module(_journal)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SENDABLE = frozenset(("READY", "CONDITIONAL"))
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
    if plan.get("status")=="READY" and (plan.get("confirmation") or {}).get("confirmed") is not True:
        return False
    if not SYMBOL.fullmatch(str(plan.get("symbol",""))):
        return False
    if plan.get("mode") not in ("scalp","swing") or plan.get("provider") not in ("Twelve Data","Bitstamp","TradingView Webhook"):
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
    if plan.get("status")=="READY":
        # Once confirmed, key is determined by actual structural entry and stop,
        # not by drifting target projections or the age of a candle.
        setup={k:plan.get(k) for k in ("symbol","mode","technical_direction","entry","sl")}
        setup["structural_level"]=(plan.get("confirmation") or {}).get("level")
        setup["chat_hash"]=hashlib.sha256(str(chat).encode()).hexdigest()
        return hashlib.sha256(json.dumps(setup,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
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

def trade_only_message(plan, now=None):
    """Only the trade and confirmation/SL/TP levels; no macro analysis mixed in."""
    if not eligible(plan) or plan.get("status")!="READY":
        raise ValueError("trade_needs_verified_ready_status")
    now=now or datetime.now(timezone.utc)
    buy=plan['technical_direction']=='BUY'
    side='شراء' if buy else 'بيع';marker='🔵' if buy else '🔴'
    symbol=_esc(plan['symbol'].split(':',1)[1])
    asset=_esc({'crypto':'سوق فوري','forex':'فوركس','futures':'عقود آجلة','cfd':'عقود فروقات'}.get((plan.get('instrument') or {}).get('asset_class'),'سوق موثق'))
    body=[marker+' <b>توصية '+side+' | '+symbol+' ('+asset+') — '+('سكالب' if plan['mode']=='scalp' else 'سوينغ')+'</b>',
          '━━━━━━━━━━━━━━━━━━','📌 الاتجاه: '+side+' '+marker,
          '🎯 منطقة / سعر الدخول: '+_f(plan['entry']),
          '🛑 وقف الخسارة (SL): '+_f(plan['sl']),'',
          '🎯 الأهداف (مستويات سعرية مقاسة عند توفر دليلها):']
    for i,t in enumerate(plan['targets']):
        label=t.get('liquidity_type') or 'دليل القياس غير متاح في السجل'
        body.append(['1️⃣','2️⃣','3️⃣'][i]+' الهدف '+['الأول','الثاني','الثالث'][i]+' (TP'+str(i+1)+'): '+_f(t['price'])+' — '+_esc(label))
    checks=(plan.get('quality_filter') or {}).get('checks') or {}
    technical=[name for name in ('اتجاه متوافق','سحب سيولة واضح','كسر هيكل بزخم','إعادة اختبار فجوة سعرية') if checks.get(name) is True]
    body+=['','📋 مرتكزات الدقة:']+['• '+name for name in technical]
    c=plan.get('confirmation') or {}
    body+=['• تأكيد إغلاق '+('ساعة' if plan['mode']=='swing' else 'خمس دقائق')+' عند '+_f(c.get('level',plan['entry'])),
           '• وقف الخسارة يمثل مستوى إبطال الفكرة؛ لا يُحرّك تلقائياً لدى وسيط.',
           '⏱️ الوقت (بتوقيت عُمان): '+now.astimezone(ZoneInfo('Asia/Muscat')).strftime('%Y-%m-%d %H:%M:%S'),
           'خطة بحثية؛ لا تنفيذ صفقات حقيقية.']
    return '\n'.join(body)

def message(plan, now=None):
    if not eligible(plan):
        raise ValueError("not_sendable")
    now=now or datetime.now(timezone.utc)
    symbol=plan["symbol"].split(":",1)[1]
    asset=plan.get("instrument",{}).get("asset_class", "unverified")
    asset_label={"crypto":"سوق فوري","forex":"فوركس","futures":"عقود آجلة","cfd":"عقود فروقات","metals":"معادن"}.get(asset,asset)
    buy=plan["technical_direction"]=="BUY"
    status=plan["status"]
    kind=("✅ صفقة بحثية مؤكدة الشروط" if status=="READY" else
          "🟡 سيناريو مشروط — ليس دخولاً الآن" if status=="CONDITIONAL" else
          "⚠️ تحذير خبر — يمنع الدخول حتى زوال القيد")
    bias={"BULLISH":"صاعد","BEARISH":"هابط","RANGING":"عرضي"}.get(plan.get("bias"),"غير محسوم")
    tf="H1/H4 سياق · H1 تنفيذ" if plan["mode"]=="swing" else "H4/H1 سياق · M15/M5 تنفيذ"
    direction="شراء" if buy else "بيع"
    c=plan.get("confirmation") or {}
    evidence=plan.get("evidence") or {}
    translations={"NO_VERIFIED_EVENT":"لا يوجد خبر مؤثر موثق حالياً","NOT_VERIFIED":"لم يتم التحقق من التقويم","NEWS_CAUTION":"تنبيه خبر قوي","EVENT_UNRATED":"الحدث غير مصنف","NOT_DETECTED":"غير مرصود","NOT_MEASURED":"غير مقاس","LOW":"قاع","HIGH":"قمة","M5_CLOSE":"إغلاق شمعة 5 دقائق","H1_CLOSE":"إغلاق شمعة ساعة"}
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
      "• "+_esc(translations.get(c.get("type"),c.get("type","إغلاق فريم التنفيذ")))+" "+("فوق" if buy else "تحت")+" "+_f(c.get("level",plan["entry"]))+
          (" · متحقق" if c.get("confirmed") else " · غير متحقق بعد"),
      "• السيولة: "+_esc(translations.get(evidence.get("LIQUIDITY_SWEEP"),evidence.get("LIQUIDITY_SWEEP","غير مثبت")))+" | FVG: "+_esc((evidence.get("FVG") or {}).get("type","غير مثبت") if isinstance(evidence.get("FVG"),dict) else evidence.get("FVG","غير مثبت")),
      "• <b>الإبطال:</b> "+("هبوط" if buy else "صعود")+" السعر إلى "+_f(plan["sl"])+" قبل تحقق الدخول",
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
    if result not in ("sent","failed","not_configured","uncertain"):
        raise ValueError("invalid_delivery_state")
    mark="%s" if postgres else "?"
    connection.execute("UPDATE native_telegram_alerts SET delivery="+mark+",updated_at="+mark+
                       " WHERE fingerprint="+mark+" AND delivery='sending'",
                       (result,datetime.now(timezone.utc).isoformat(),key))

def analysis_message(plan, now=None):
    """Second card: technical evidence only, distinct from entry/SL/targets."""
    if not eligible(plan):raise ValueError("not_sendable")
    now=now or datetime.now(timezone.utc)
    evidence=plan.get("evidence") or {}
    bias={"BULLISH":"صاعد","BEARISH":"هابط","RANGING":"عرضي"}.get(plan.get("bias"),"غير محسوم")
    sweep={"LOW":"سحب سيولة قاع","HIGH":"سحب سيولة قمة"}.get(evidence.get("LIQUIDITY_SWEEP"),"سحب السيولة غير مؤكد")
    zone=plan.get("entry_zone") or [plan["entry"],plan["entry"]]
    zone_text=" — ".join(_f(value) for value in zone)
    scenario=("استمرار الصعود نحو الأهداف المحددة ما دام وقف الخسارة محفوظاً" if plan["technical_direction"]=="BUY" else
              "استمرار الهبوط نحو الأهداف المحددة ما دام وقف الخسارة محفوظاً")
    return "\n".join([
      "📈 تحديث تحليل فني: "+_esc(plan["symbol"]),"━━━━━━━━━━━━━━━━━━",
      "🧭 الاتجاه العام: "+bias,"💧 السيولة: "+sweep,
      "📍 منطقة الدخول المعتمدة: "+zone_text,"🎯 السيناريو المتوقع: "+scenario,
      "📋 التأكيد: "+("متحقق بإغلاق فريم الدخول" if (plan.get("confirmation") or {}).get("confirmed") else "مشروط؛ لم يتأكد الدخول"),
      "📡 مصدر الشموع: "+_esc(plan["provider"]),"شمعة المصدر: "+_esc(plan["source_time"]),
      "⏱️ الوقت: "+now.astimezone(ZoneInfo("Asia/Muscat")).strftime("%Y-%m-%d %H:%M:%S")+" مسقط",
      "تحليل بحثي مستقل عن تنفيذ الوسيط."])

def claim_companion(connection,plan,trade_chat,analysis_chat,postgres=False,now=None):
    """A separate receipt, only after the original trade was accepted by Telegram.

    Uncertain sends are not automatically retried: Telegram has no idempotency key.
    Legacy trade fingerprints remain unchanged across this additive rollout.
    """
    if not eligible(plan) or plan.get("status")!="READY":return None
    if not re.fullmatch(r"-?[0-9]{5,20}",str(analysis_chat)):return None
    parent=fingerprint(plan,trade_chat)
    mark="%s" if postgres else "?"
    row=connection.execute("SELECT delivery FROM native_telegram_alerts WHERE fingerprint="+mark,(parent,)).fetchone()
    if not row or row[0]!="sent":return None
    key=hashlib.sha256((parent+":technical:"+str(analysis_chat)).encode()).hexdigest()
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    result=connection.execute("INSERT INTO native_telegram_alerts(fingerprint,symbol,mode,status,delivery,created_at,updated_at) VALUES ("+
          ",".join([mark]*7)+") ON CONFLICT(fingerprint) DO NOTHING",
          (key,plan["symbol"],plan["mode"],"ANALYSIS","sending",stamp,stamp))
    return key if result.rowcount==1 else None

def send(plan,token,chat,opener=None,timeout=5,topic_id=None,category=None):
    if not eligible(plan):
        return "not_eligible"
    if not token or not re.fullmatch(r"-?[0-9]{5,20}",str(chat)):
        return "not_configured"
    opener=opener or urllib.request.urlopen
    content=analysis_message(plan) if category=="analysis" else trade_only_message(plan) if plan["status"]=="READY" else message(plan)
    body={"chat_id":chat,"text":content,"parse_mode":"HTML",
                        "disable_web_page_preview":True}
    if category!='analysis' and plan['status']=='READY':
        ident=_journal.key(plan)[:24]
        body['reply_markup']={'inline_keyboard':[[{'text':title,'callback_data':'trade:'+action+':'+ident} for title,action in
            [('📊 تحليل الزوج','view'),('🔄 فحص دخول جديد','new'),('📌 حالة الصفقة','state')]]]}
    if isinstance(topic_id,int) and topic_id>0:body["message_thread_id"]=topic_id
    payload=json.dumps(body,ensure_ascii=False).encode("utf-8")
    request=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=payload,
                                   method="POST",headers={"Content-Type":"application/json"})
    try:
        with opener(request,timeout=timeout) as response:
            # Telegram HTTP 200 is success; response JSON may include full echoed
            # HTML message and exceed 2048 bytes. Do not truncate+parse it.
            return "sent" if response.status==200 else "failed"
    except urllib.error.HTTPError as error:
        # Telegram may reject malformed markup or a chat without message permissions.
        # Only whitelist diagnostic categories; do not log the token, URL or chat.
        try:
            details=error.read(768).decode("utf-8","replace").lower()
        except Exception:
            details=""
        reason=("HTML_ENTITIES" if "parse entities" in details else
                "CHAT_NOT_FOUND" if "chat not found" in details else
                "BOT_BLOCKED" if "blocked by the user" in details else
                "MESSAGE_FORBIDDEN" if "not enough rights" in details or "forbidden" in details else
                "UNCLASSIFIED")
        print("native_telegram_error status="+str(error.code)+" category="+reason,flush=True)
        return "failed" if 400<=error.code<500 else "uncertain"
    except (ValueError,KeyError,TypeError,TimeoutError,OSError,urllib.error.URLError):
        print("native_telegram_error status=CONNECTION_OR_RESPONSE",flush=True)
        return "uncertain"
