"""Arabic, evidence-bound technical events and news scenarios.

No use of stale price, invented quotes or non-licensed futures contracts.
Only finished M5 candles from matching provider can generate events.
"""
import hashlib, json, math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def migrate(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS arabic_market_event_alerts (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, symbol TEXT NOT NULL,
      source_time TEXT NOT NULL, payload TEXT NOT NULL,
      delivery TEXT NOT NULL, created_at TEXT NOT NULL
    )""")

def fingerprint(event):
    stable={k:event.get(k) for k in ("kind","symbol","source_time","event_type","level","direction")}
    return hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def reserve(connection,event,postgres=False,now=None):
    if event.get("kind") not in ("technical","news") or not event.get("source_time"):
        return None
    key=fingerprint(event)
    mark="%s" if postgres else "?"
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    values=(key,event["kind"],event.get("symbol",""),event["source_time"],
            json.dumps(event,ensure_ascii=False),"sending",stamp)
    result=connection.execute("INSERT INTO arabic_market_event_alerts(id,kind,symbol,source_time,payload,delivery,created_at) VALUES ("+
                      ",".join([mark]*7)+") ON CONFLICT(id) DO NOTHING",values)
    if result.rowcount==1:return key
    retry=connection.execute("UPDATE arabic_market_event_alerts SET delivery='sending' WHERE id="+mark+
                   " AND delivery='failed'",(key,))
    return key if retry.rowcount==1 else None

def finish(connection,key,state,postgres=False):
    if state not in ("sent","failed","not_configured"):raise ValueError("invalid_delivery")
    mark="%s" if postgres else "?"
    connection.execute("UPDATE arabic_market_event_alerts SET delivery="+mark+" WHERE id="+mark,(state,key))

def _stamp(value):
    dt=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:raise ValueError("timestamp_without_timezone")
    return dt.astimezone(timezone.utc)

def _value(x):
    return format(float(x),".8f").rstrip("0").rstrip(".")

def technical_events(symbol, rows, now=None):
    """Detect *new* confirmed closed-bar breakout / sweep from matching OHLC.

    No inference of IFVG, order blocks, CISD or SMT without implementing
    their complete validation criteria.
    """
    now=now or datetime.now(timezone.utc)
    if len(rows)<55:return []
    ordered=sorted(rows,key=lambda x:str(x[0] if not isinstance(x,dict) else x["time"]))
    try:
        bars=[]
        for item in ordered[-70:]:
            when,op,high,low,close=(item["time"],item["open"],item["high"],item["low"],item["close"]) if isinstance(item,dict) else item[:5]
            when=_stamp(when);op,high,low,close=map(float,(op,high,low,close))
            if not all(math.isfinite(v) and v>0 for v in (op,high,low,close)) or not low<=min(op,close)<=max(op,close)<=high or when.second or when.minute%5:
                return []
            bars.append((when,op,high,low,close))
    except (ValueError,TypeError,KeyError,IndexError,OverflowError):return []
    if any((b[0]-a[0]).total_seconds()!=300 for a,b in zip(bars[-24:-1],bars[-23:])):return []
    last=bars[-1];age=(now-last[0]).total_seconds()
    if not 300<=age<=630:return []
    prior=bars[-21:-1]
    ceiling=max(x[2] for x in prior);floor=min(x[3] for x in prior)
    # The previous candle must not already have broken the same level.
    previous=bars[-2]
    events=[]
    tests=[
        ("BREAK_HIGH","شراء", "صاعد",last[4]>ceiling and previous[4]<=ceiling,ceiling),
        ("BREAK_LOW","بيع","هابط",last[4]<floor and previous[4]>=floor,floor),
        ("SWEEP_HIGH","بيع","احتمال انعكاس هابط",last[2]>ceiling and last[4]<ceiling,ceiling),
        ("SWEEP_LOW","شراء","احتمال انعكاس صاعد",last[3]<floor and last[4]>floor,floor),
    ]
    for event_type,side,direction,trigger,level in tests:
        if not trigger:continue
        events.append({"kind":"technical","symbol":symbol,"event_type":event_type,
                       "direction":direction,"side":side,"level":_value(level),
                       "source_time":last[0].isoformat(),"close":_value(last[4]),
                       "observed_at":now.isoformat(),
                       "note":"حدث فني مرصود من شمعة M5 مغلقة؛ ليس صفقة مؤكدة ولا تقديراً لسيولة دفتر الأوامر"})
    # Track previous UTC-session levels only with actually available previous-day bars.
    prior_days=sorted({b[0].date() for b in bars if b[0].date()<last[0].date()})
    if prior_days:
        d=prior_days[-1];prev_day=[b for b in bars if b[0].date()==d]
        for level,name,condition,side in [
            (max(b[2] for b in prev_day),"قمة اليوم السابق UTC",last[4]>max(b[2] for b in prev_day) and previous[4]<=max(b[2] for b in prev_day),"شراء"),
            (min(b[3] for b in prev_day),"قاع اليوم السابق UTC",last[4]<min(b[3] for b in prev_day) and previous[4]>=min(b[3] for b in prev_day),"بيع"),
        ]:
            if condition:
                events.append({"kind":"technical","symbol":symbol,"event_type":"PREVIOUS_DAY_BREAK",
                               "direction":"صاعد" if side=="شراء" else "هابط",
                               "side":side,"level":_value(level),"source_time":last[0].isoformat(),
                               "observed_at":now.isoformat(),"note":"مستوى يوم UTC، لا يعني جلسة بورصة محلية"})
    return events[:4]

def technical_message(event,now=None):
    if event.get("kind")!="technical":raise ValueError("wrong_kind")
    names={"BREAK_HIGH":"اختراق قمة نطاق آخر 20 شمعة",
           "BREAK_LOW":"كسر قاع نطاق آخر 20 شمعة",
           "SWEEP_HIGH":"سحب سيولة أعلى القمة مع إغلاق دونها",
           "SWEEP_LOW":"سحب سيولة أسفل القاع مع إغلاق فوقه",
           "PREVIOUS_DAY_BREAK":"كسر مستوى اليوم السابق (UTC)"}
    side=event.get("side")
    icon="🔵" if side=="شراء" else "🔴"
    when=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Muscat")).strftime("%Y-%m-%d %H:%M:%S")
    return ("⚡ تحديث فني جديد | "+event["symbol"]+"\n━━━━━━━━━━━━━━━━━━\n"
            "🧭 اتجاه الحدث: "+event["direction"]+" "+icon+"\n"
            "🔥 الحدث المرصود: "+names.get(event["event_type"],"تغيّر فني")+"\n"
            "📍 المستوى: "+event["level"]+"\n"
            "📌 الإغلاق المؤكد: "+event.get("close","—")+"\n"
            "🎯 التصرف: مراقبة إعادة الاختبار أو تأكيد الفريم الأعلى؛ لا توجد أهداف سعرية دون خطة مستقلة موثقة\n"
            "📊 المصدر: شموع مغلقة من نفس الأصل\n"
            "⏱️ وقت الإرسال (مسقط): "+when+"\n"
            "⚠️ تحليل بحثي، وليس توصية تنفيذ فورية")

def news_scenarios(snapshot,now=None):
    """No fabricated economic surprise, impact rating, consensus or actual."""
    now=now or datetime.now(timezone.utc)
    if not isinstance(snapshot,dict):return []
    events=[]
    for item in snapshot.get("calendar",[]):
        if item.get("feed_fresh") is not True or item.get("feed_state")!="CONNECTED":continue
        try:when=_stamp(item["time"])
        except (ValueError,TypeError,KeyError):continue
        minutes=(when-now).total_seconds()/60
        if not -15<=minutes<=30:continue
        title=str(item.get("title",""))[:140]
        lower=title.lower()
        classification=("تضخم" if "cpi" in lower or "consumer price" in lower else
                        "توظيف" if "employment situation" in lower or "nonfarm" in lower or "nfp" in lower else
                        "فائدة" if "fomc" in lower or "interest rate" in lower else "خبر اقتصادي")
        confirmed_numbers=(item.get("actual_verified") is True and item.get("consensus_verified") is True)
        event_type="RELEASED" if minutes<0 and confirmed_numbers else "UPCOMING" if minutes>=0 else None
        if event_type is None:continue
        events.append({"kind":"news","symbol":str(item.get("currency","USD")),"event_type":event_type,
                       "direction":"سيناريوهات مشروطة غير مؤكدة","source_time":when.isoformat(),
                       "level":None,"title":title,"classification":classification,
                       "minutes_until":round(minutes,1),
                       "consensus":item.get("consensus"),
                       "actual":item.get("actual"),"previous":item.get("previous"),
                       "impact_verified":item.get("impact_verified") is True,
                       "actual_verified":confirmed_numbers,
                       "source":item.get("source","تقويم رسمي")})
    return events[:8]

def news_message(event,now=None):
    if event.get("kind")!="news":raise ValueError("wrong_kind")
    # Macro sign heuristics apply to inflation surprises, not to every Fed event.
    if event.get("classification")=="تضخم":
        scenarios=("• إذا فاق التضخم التوقع الموثق: قد يدعم الدولار ويضغط على الذهب والناسداك 🔴، مع احتمال استجابة معاكسة بحسب عوائد السندات والسياق.\n"
                   "• إذا جاء التضخم دون التوقع الموثق: قد يدعم الذهب والناسداك 🔵 عند تأكيد حركة الأسعار.")
    elif event.get("classification")=="توظيف":
        scenarios=("• نتيجة توظيف أعلى من التوقع: قد تدعم الدولار، لكن أثرها على الأسهم يتوقف على الأجور والبطالة وتوقعات الفائدة.\n"
                   "• نتيجة أقل من التوقع: قد تضعف الدولار، ولا تعني شراء الناسداك تلقائياً.")
    else:
        scenarios=("• سيناريو صعود محتمل عند مفاجأة داعمة للأصل وتأكيد حركة الشموع.\n"
                   "• سيناريو هبوط محتمل عند مفاجأة معاكسة وتأكيد حركة الشموع.")
    if event.get("event_type")=="RELEASED" and event.get("actual_verified") is True:
        try:
            actual=float(event["actual"]);forecast=float(event["consensus"])
            if not math.isfinite(actual) or not math.isfinite(forecast):raise ValueError("nonfinite")
            effect=("النتيجة أعلى من المتوقع" if actual>forecast else
                    "النتيجة أقل من المتوقع" if actual<forecast else "مطابقة للتوقع")
        except (TypeError,ValueError,KeyError):
            effect="تعذر التحقق من الفرق العددي"
        scenarios=("📊 الفعلي: "+str(event["actual"])+" | المتوقع: "+str(event["consensus"])+"\n"
                   +effect+"\n⚠️ الاتجاه النهائي للذهب أو الناسداك لا يثبت من المفاجأة وحدها؛ يلزم تأكيد حركة السعر.")
    when=_stamp(event["source_time"]).astimezone(ZoneInfo("Asia/Muscat")).strftime("%Y-%m-%d %H:%M")
    forecast=str(event["consensus"]) if event.get("consensus") is not None else "غير متوفر من مصدر موثق"
    previous=str(event["previous"]) if event.get("previous") is not None else "غير متوفر"
    return ("📰 سيناريوهات خبر اقتصادي | "+event["classification"]+"\n━━━━━━━━━━━━━━━━━━\n"
            "📌 الحدث: "+event["title"]+"\n⏰ الموعد: "+when+" (مسقط)\n"
            "📊 التوقع: "+forecast+"\n📉 السابق: "+previous+"\n"
            "🔮 سيناريوهات مشروطة:\n"+scenarios+"\n"
            +("⚠️ تمت مقارنة الأرقام الموثقة؛ لا تكفي وحدها لتأكيد اتجاه التداول." if event.get("event_type")=="RELEASED" else "⚠️ لا توجد مقارنة فعلية مع المتوقع أو إشارة شراء/بيع مؤكدة قبل صدور بيانات موثقة؛ التأثير غير مصنف رسمياً إن لم يرد تقييم موثق."))
