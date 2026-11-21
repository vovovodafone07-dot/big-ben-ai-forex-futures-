"""Research-only trade journal: confirmed signals are not real broker fills.

Monitors closed matching-provider M5 bars strictly AFTER a published setup.
Ambiguous intrabar TP/SL collisions never resolve into fake profitable fills.
"""
import hashlib,json,math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS native_trade_journal (
      id TEXT PRIMARY KEY, symbol TEXT NOT NULL, mode TEXT NOT NULL,
      side TEXT NOT NULL, entry REAL NOT NULL, sl REAL NOT NULL,
      targets_json TEXT NOT NULL, announced_at TEXT NOT NULL,
      announced_candle TEXT NOT NULL, state TEXT NOT NULL,
      last_bar TEXT, tp_count INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL, evidence_json TEXT NOT NULL
    )""")

def key(plan):
    # Deliberately omit current candle timestamp, superficial status, confidence and
    # recomputed R-multiples. A fresh structural entry or SL is a NEW research setup.
    basic={name:plan.get(name) for name in ("symbol","mode","technical_direction","entry","sl")}
    basic["structural_level"]=(plan.get("confirmation") or {}).get("level")
    return hashlib.sha256(json.dumps(basic,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def store(db,plan,postgres=False,now=None):
    if plan.get("status")!="READY" or not (plan.get("confirmation") or {}).get("confirmed"):
        return None
    if plan.get("technical_direction") not in ("BUY","SELL") or len(plan.get("targets") or [])!=3:
        return None
    if not isinstance(plan.get("source_time"),str):return None
    marker="%s" if postgres else "?"
    now=(now or datetime.now(timezone.utc)).isoformat()
    ident=key(plan)
    args=(ident,plan["symbol"],plan["mode"],plan["technical_direction"],
          float(plan["entry"]),float(plan["sl"]),
          json.dumps([t["price"] for t in plan["targets"]]),now,plan["source_time"],
          "مراقبة دخول افتراضي",None,0,now,json.dumps({"source":plan["provider"],"note":"لا يمثل تنفيذ وسيط"}))
    command="INSERT INTO native_trade_journal(id,symbol,mode,side,entry,sl,targets_json,announced_at,announced_candle,state,last_bar,tp_count,updated_at,evidence_json) VALUES ("+",".join([marker]*14)+") ON CONFLICT(id) DO NOTHING"
    result=db.execute(command,args)
    return ident if result.rowcount==1 else None

def _dt(x):
    d=datetime.fromisoformat(str(x).replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("missing timezone")
    return d.astimezone(timezone.utc)

def follow(db,symbol,rows,postgres=False,now=None):
    now=now or datetime.now(timezone.utc)
    m="%s" if postgres else "?"
    records=db.execute("SELECT id,side,entry,sl,targets_json,announced_candle,state,last_bar,tp_count FROM native_trade_journal WHERE symbol="+m+
                        " AND state NOT IN ('الهدف الثالث تحقق','وقف الخسارة تحقق','نتيجة غير محسومة') ORDER BY announced_at DESC LIMIT 30",(symbol,)).fetchall()
    events=[]
    for ident,side,entry,sl,raw,announced,state,last_seen,previous in records:
        try:targets=[float(x) for x in json.loads(raw)];start=_dt(last_seen or announced)
        except (ValueError,TypeError):continue
        for rawbar in sorted(rows,key=lambda r:str(r[0] if not isinstance(r,dict) else r["time"])):
            try:
                stamp,op,high,low,close=rawbar[:5] if not isinstance(rawbar,dict) else (rawbar["time"],rawbar["open"],rawbar["high"],rawbar["low"],rawbar["close"])
                stamp=_dt(stamp);high,low,close=map(float,(high,low,close))
            except (TypeError,ValueError,KeyError):continue
            age=(now-stamp).total_seconds()
            if stamp<=start or age<300 or not math.isfinite(high+low+close):continue
            entered=state!="مراقبة دخول افتراضي"
            touched_entry=low<=entry<=high
            if not entered and not touched_entry:continue
            if not entered:state="دخل النطاق افتراضياً";entered=True
            stop_hit=low<=sl if side=="BUY" else high>=sl
            hit=sum(1 for t in targets if (high>=t if side=="BUY" else low<=t))
            hit=max(hit,previous)
            # SL and targets in the same bar: unresolvable execution order.
            if stop_hit and hit>previous:
                label="نتيجة غير محسومة"
            elif stop_hit:
                label="وقف الخسارة تحقق"
            elif hit>previous:
                label="الهدف "+["الأول","الثاني","الثالث"][hit-1]+" تحقق"
            else:
                label=state
            if label!=state or (state=="مراقبة دخول افتراضي" and touched_entry):
                events.append({"kind":"management","id":ident,"symbol":symbol,"state":label,
                    "close":close,"source_time":stamp.isoformat(),
                    "note":"متابعة افتراضية من شموع مغلقة لا تثبت تعبئة حقيقية، وقد تُحسم أحداث داخل الشمعة بصعوبة"})
            state=label;previous=hit;start=stamp
            db.execute("UPDATE native_trade_journal SET state="+m+",last_bar="+m+",tp_count="+m+",updated_at="+m+
                " WHERE id="+m,(state,stamp.isoformat(),previous,now.isoformat(),ident))
            if label in ("الهدف الثالث تحقق","وقف الخسارة تحقق","نتيجة غير محسومة"):break
    return events

def management_message(e,now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Muscat"))
    return ("🎯 تحديث إدارة صفقة بحثية | "+e["symbol"]+"\n━━━━━━━━━━━━━━━━━━\n"
            "📌 الحالة: "+e["state"]+"\n"
            "💰 سعر إغلاق الشمعة: "+str(e["close"])+"\n"
            "⏱️ الوقت: "+now.strftime("%Y-%m-%d %H:%M:%S")+" مسقط\n"
            "⚠️ متابعة افتراضية؛ لا يوجد تنفيذ وسيط مؤكد")

def recent(db,limit=50):
    rows=db.execute("SELECT id,symbol,mode,side,entry,sl,targets_json,state,tp_count,announced_at,updated_at FROM native_trade_journal ORDER BY announced_at DESC LIMIT "+str(min(100,max(1,int(limit))))).fetchall()
    return [{"id":r[0],"symbol":r[1],"mode":r[2],"side":r[3],"entry":r[4],"sl":r[5],
             "targets":json.loads(r[6]),"state":r[7],"tp_count":r[8],"announced_at":r[9],"updated_at":r[10]} for r in rows]
