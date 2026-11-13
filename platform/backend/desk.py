"""Instrument analysis and specialist evidence. Only received signals can be trades."""
import hashlib
import importlib.util
import json
import math
from datetime import datetime,timezone
from pathlib import Path

def sibling(name):
    spec=importlib.util.spec_from_file_location("desk_"+name,Path(__file__).with_name(name+".py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

scalping=sibling("scalping")
instruments=sibling("instruments")
SYMBOLS=instruments.SYMBOLS
CHECKS={"trigger_buy":"اختراق وإعادة اختبار للشراء","trigger_sell":"اختراق وإعادة اختبار للبيع",
    "ready":"عدم وجود صفقة مفتوحة واجتياز الكولداون","htf_long":"فلتر الفريمات العليا للشراء",
    "htf_short":"فلتر الفريمات العليا للبيع","ha_long":"تأكيد Heikin Ashi للشراء",
    "ha_short":"تأكيد Heikin Ashi للبيع","volatility_ok":"فلتر هدوء ATR",
    "risk_buy_ok":"مسافة وقف الشراء ضمن حدود الاستراتيجية","risk_sell_ok":"مسافة وقف البيع ضمن حدود الاستراتيجية",
    "hybrid_buy_ok":"عدد أدلة الشراء المطلوب","hybrid_sell_ok":"عدد أدلة البيع المطلوب",
    "direction_buy_ok":"السماح باتجاه الشراء","direction_sell_ok":"السماح باتجاه البيع",
    "cisd_buy":"CISD شراء — تجاوز افتتاح الشمعة السابقة المعاكسة",
    "cisd_sell":"CISD بيع — كسر افتتاح الشمعة السابقة المعاكسة",
    "smt_buy":"SMT شراء — اختلاف قاع مع رمز المقارنة",
    "smt_sell":"SMT بيع — اختلاف قمة مع رمز المقارنة"}

def normalize(value):
    return instruments.normalize(value)

def condition_checks(telemetry):
    raw=telemetry.get("checks") if isinstance(telemetry.get("checks"),dict) else {}
    filters=telemetry.get("filters") if isinstance(telemetry.get("filters"),dict) else {}
    optional={"ha_long":"use_ha","ha_short":"use_ha","volatility_ok":"use_atr_floor","hybrid_buy_ok":"use_hybrid","hybrid_sell_ok":"use_hybrid","smt_buy":"enable_smt","smt_sell":"enable_smt"}
    return [{"key":key,"label":label,"state":"DISABLED" if filters.get(optional.get(key)) is False else "PASSED" if raw.get(key) is True else "FAILED" if raw.get(key) is False else "UNKNOWN"} for key,label in CHECKS.items()]

def analyze(symbol,rows,news,now=None):
    symbol=normalize(symbol);now=now or datetime.now(timezone.utc)
    parsed=[]
    for market,kind,stamp,payload in rows:
        if market!=symbol or kind not in ("BUY","SELL","HEARTBEAT"):continue
        try:
            dt=datetime.fromisoformat(stamp.replace("Z","+00:00"));data=json.loads(payload)
            if dt.tzinfo is None or not isinstance(data,dict):continue
            parsed.append((dt,kind,data))
        except (ValueError,TypeError,AttributeError):continue
    parsed.sort(key=lambda x:x[0],reverse=True)
    latest=parsed[0] if parsed else None
    fresh=bool(latest and 0<=(now-latest[0]).total_seconds()<720)
    data=latest[2] if latest else {}
    telemetry=data.get("analysis") if isinstance(data.get("analysis"),dict) else {}
    raw_checks=telemetry.get("checks") if isinstance(telemetry.get("checks"),dict) else {}
    checks=condition_checks(telemetry)
    # Reuse the same freshness/outcome/geometry policy as the paired scalp endpoint.
    paired=scalping.scenarios([row for row in rows if row[0]==symbol],1,now=now)
    signals=[s for s in paired["signals"] if s["symbol"]==symbol]
    signal=signals[0] if fresh and signals else None
    if signal:
        reference=next((item[2] for item in parsed if item[2].get("event_id")==signal["event_id"]),data)
        telemetry=reference.get("analysis") if isinstance(reference.get("analysis"),dict) else {}
        raw_checks=telemetry.get("checks") if isinstance(telemetry.get("checks"),dict) else {}
        checks=condition_checks(telemetry)
    reasons=[]
    if not latest:reasons.append("لم تصل بيانات TradingView لهذا الرمز بعد")
    elif not fresh:reasons.append("آخر بيانات الرمز قديمة؛ لا تصدر صفقة حديثة منها")
    if not signal:reasons.append("لا توجد إشارة BUY/SELL حديثة وصالحة من الاستراتيجية؛ القرار انتظار")
    if not raw_checks:reasons.append("النسخة الحالية لم ترسل تفاصيل شروط الدخول بعد؛ لا تُفترض تحققها")
    if signal:
        reasons.extend(["إشارة فعلية مستلمة من TradingView","مستويات الدخول والوقف والهدف متسقة مع اتجاه الصفقة وRR","لم يُرصد إغلاق M5 يتجاوز الهدف أو الوقف في نافذة الفحص"])
    relevant=[n for n in news.get("news",[]) if n.get("feed_fresh") and n.get("feed_state")=="CONNECTED"][:6]
    calendar=[e for e in news.get("calendar",[]) if e.get("feed_fresh") and e.get("feed_state")=="CONNECTED"]
    upcoming=[e for e in calendar if 0<=(datetime.fromisoformat(e["time"])-now).total_seconds()<=3600]
    # News data does not change the production Pine strategy or manufacture a trade.
    scenarios=[{"condition":"خبر أقوى من إجماع موثق","scenario":"تُراجع استجابة السعر والسيولة بعد الإصدار؛ لا يضمن الخبر اتجاهًا ثابتًا"},
        {"condition":"خبر أضعف من إجماع موثق","scenario":"تُنتظر إعادة اختبار ومستويات صحيحة من المؤشر قبل الدخول"},
        {"condition":"بيانات متعارضة أو غياب إجماع موثق","scenario":"لا يوجد توقع رقمي معتمد؛ السيناريو بحثي والانتظار متاح"}]
    decision=signal["event"] if signal else "WAIT"
    failed=[c["label"] for c in checks if c["state"]=="FAILED"]
    if fresh and raw_checks and not signal:
        reasons.extend("لم يتحقق: "+label for label in failed[:6])
    roles=[{"role":"market_data","state":"COMPLETED","output":"بيانات حديثة مستلمة" if fresh else "بيانات غير كافية أو قديمة"},
        {"role":"signal_quality","state":"COMPLETED","output":"؛ ".join(reasons)},
        {"role":"risk","state":"COMPLETED","output":"الصفقة الكاملة والسكالب بديلان بنفس الدخول والوقف؛ لا تُجمع المخاطرتان"},
        {"role":"news","state":"COMPLETED","output":"أخبار موثقة متاحة؛ لا يوجد إجماع رقمي متصل" if relevant else "لا توجد خلاصة أخبار حديثة مؤكدة"},
        {"role":"backtesting","state":"COMPLETED","output":"المحاكاة التاريخية منفصلة عن قرار الإشارة الحية؛ مطابقة Pine غير مثبتة"},
        {"role":"learning","state":"COMPLETED","output":"تُراجع نتائج الإشارات المرصودة قبل اقتراح تحسين؛ لا تعديل تلقائي للاستراتيجية"},
        {"role":"validation","state":"COMPLETED","output":"تُرفض الصفقة عند غياب إشارة حديثة ومستويات سليمة"},
        {"role":"updates","state":"COMPLETED","output":"الكود الحي مرتبط بسجل المصدر؛ تحديث TradingView يحتاج مسار الحساب المدعوم واختبارات الإصدار"},
        {"role":"coordinator","state":"COMPLETED","output":decision}]
    return {"instrument":instruments.describe(symbol),"symbol":symbol,"generated_at":now.isoformat(),"decision":decision,"fresh":fresh,
        "source_time":latest[0].isoformat() if latest else None,"received_at":data.get("received_at"),
        "strategy_version":data.get("strategy_version") if isinstance(data.get("strategy_version"),str) else None,
        "bridge_version":data.get("bridge_version") if isinstance(data.get("bridge_version"),str) else None,
        "observed_close":data.get("close",data.get("entry")),"checks":checks,"reasons":reasons,
        "failed_checks":failed,"full_trade":signal["full_trade"] if signal else None,
        "scalp":signal["scalp"] if signal else None,"news":relevant,"upcoming_events":upcoming,
        "news_scenarios":scenarios,"consensus_available":False,"agent_tasks":roles,
        "broker_execution":False,"source":"TradingView authenticated events",
        "note":"Unknown conditions are not confirmed. M5 close observations are not broker fills."}


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS analysis_runs (id TEXT PRIMARY KEY,symbol TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)")

def record(connection,result,postgres=False):
    marker="%s" if postgres else "?"
    digest=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    result["run_id"]=digest
    for index,task in enumerate(result["agent_tasks"]):
        task.update(task_id=digest+":"+task["role"],completed_at=result["generated_at"],execution_type="deterministic_evidence_check",depends_on=[] if index==0 else ["market_data"])
    connection.execute("INSERT INTO analysis_runs(id,symbol,created_at,payload) VALUES ("+",".join([marker]*4)+") ON CONFLICT(id) DO NOTHING",(digest,result["symbol"],result["generated_at"],json.dumps(result)))
    return result
