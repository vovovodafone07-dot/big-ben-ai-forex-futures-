"""Authenticated TradingView symbol discovery, separate from market-data entitlement.

Call record_symbol only AFTER existing /v1/tradingview/events authentication and
payload validation. Discovery is not permission to create a trade or send Telegram.
"""
import json
import re
from datetime import datetime, timezone

SYMBOL_RE = re.compile(r"^[A-Z0-9_]{2,40}:[A-Z0-9_.!/-]{1,50}$")
ALLOWED_KINDS = {"cfd", "futures", "forex", "crypto", "other"}


def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS tradingview_discovered_symbols (
        symbol TEXT PRIMARY KEY,
        asset_class TEXT NOT NULL,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        event_count INTEGER NOT NULL DEFAULT 1,
        feed_verified INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL
    )""")


def record_symbol(db, payload, *, authenticated=False, postgres=False, now=None):
    """Observes a symbol from a fully authenticated, validated alert.

    Does NOT elevate data permissions or mark a future as trade-ready.
    """
    if authenticated is not True:
        raise PermissionError("إشارة TradingView غير موثقة")
    if not isinstance(payload, dict):
        raise ValueError("حمولة التنبيه غير صالحة")
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("يجب تحديد رمز مؤهل باسم مصدره مثل OANDA:EURUSD")
    kind = str(payload.get("asset_class") or "other").lower()
    if kind not in ALLOWED_KINDS:
        kind = "other"
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    marker = "%s" if postgres else "?"
    query = """INSERT INTO tradingview_discovered_symbols
        (symbol,asset_class,first_seen,last_seen,event_count,feed_verified,enabled,source)
        VALUES (?,?,?,?,1,0,0,'TradingView Webhook')
        ON CONFLICT(symbol) DO UPDATE SET
        last_seen=excluded.last_seen,
        event_count=tradingview_discovered_symbols.event_count+1"""
    if postgres:
        query = query.replace("?,?,?,?", "%s,%s,%s,%s")
    db.execute(query, (symbol, kind, stamp, stamp))
    return {"symbol": symbol, "asset_class": kind,
            "state": "مكتشف، ينتظر التحقق من اتصال الأسعار"}


def discovered(db, limit=500):
    limit = max(1, min(int(limit), 1000))
    rows = db.execute("""SELECT symbol,asset_class,first_seen,last_seen,event_count,
        feed_verified,enabled FROM tradingview_discovered_symbols
        ORDER BY last_seen DESC LIMIT """ + str(limit)).fetchall()
    return [{"symbol": r[0], "asset_class": r[1], "first_seen": r[2],
             "last_seen": r[3], "event_count": r[4],
             "feed_verified": bool(r[5]), "enabled": bool(r[6])} for r in rows]


def _clean(s):
    return str(s or "").strip()


def trade_card(plan, now=None):
    """Arabic trade-only text. Caller MUST enforce market gate and dedup."""
    if plan.get("status") != "READY" or not (plan.get("confirmation") or {}).get("confirmed"):
        raise ValueError("شروط الصفقة غير مؤكدة")
    direction = plan.get("technical_direction")
    if direction not in ("BUY", "SELL"):
        raise ValueError("اتجاه غير صالح")
    t = plan.get("targets") or []
    if len(t) != 3:
        raise ValueError("ثلاثة أهداف مطلوبة")
    for name in ("symbol", "entry", "sl"):
        if plan.get(name) is None:
            raise ValueError("بيانات صفقة غير مكتملة")
    marker = "🔵 توصية شراء" if direction == "BUY" else "🔴 توصية بيع"
    class_name = {"futures": "عقود آجلة", "cfd": "عقود فروقات",
                  "forex": "فوركس"}.get(plan.get("asset_class"), "أصل متداول")
    when = (now or datetime.now(timezone.utc)).isoformat()
    cond = plan.get("conditions") or []
    conditions = [str(x)[:140] for x in cond if str(x).strip()][:3]
    if not conditions:
        conditions = ["تأكيد البنية الفنية وإغلاق شمعة الدخول"]
    return "\n".join([
        f"{marker} | {plan['symbol']} ({class_name})",
        "━━━━━━━━━━━━━━━━━━",
        f"📌 نوع الصفقة: {'شراء' if direction == 'BUY' else 'بيع'}",
        f"🎯 الدخول: {plan['entry']}",
        f"🛑 وقف الخسارة (SL): {plan['sl']}",
        "✅ الأهداف:",
        *[f"• الهدف {i} (TP{i}): {x['price']}" for i,x in enumerate(t,1)],
        "📋 شروط الدخول:",
        *[f"• {x}" for x in conditions],
        f"⏱️ الوقت: {when}",
        "⚠️ مستويات تحليلية؛ لا تمثل تنفيذ صفقة لدى وسيط",
    ])


def analysis_card(event, now=None):
    """Companion message, distinct from trade card."""
    when = (now or datetime.now(timezone.utc)).isoformat()
    return "\n".join([
        f"📈 تحديث تحليل فني: {_clean(event.get('symbol'))}",
        "━━━━━━━━━━━━━━━━━━",
        f"🧭 الاتجاه العام: {_clean(event.get('trend')) or 'غير محسوم'}",
        f"💧 الحدث المرصود: {_clean(event.get('event')) or 'لا يوجد حدث مؤكد'}",
        f"📍 المنطقة الرئيسية: {_clean(event.get('zone')) or 'لم تتأكد منطقة فنية'}",
        f"🎯 السيناريو المتوقع: {_clean(event.get('scenario')) or 'لا توجد شروط كافية لتحديد مسار مرجح'}",
        f"⏱️ الوقت: {when}",
    ])


def tracked_catalog(db,watched,connected,postgres=False):
    """Owner-selected/discovered metadata, never a claim of live feed access."""
    verified={row['symbol']:row for row in connected}
    symbols={symbol for symbol in watched if isinstance(symbol,str) and SYMBOL_RE.fullmatch(symbol)}
    symbols.update(row['symbol'] for row in discovered(db,1000))
    symbols.update(verified)
    rows=[]
    for symbol in sorted(symbols):
        if symbol in verified:
            rows.append(dict(verified[symbol]));continue
        rows.append({'symbol':symbol,'label':symbol,'connected':False,'fresh':False,
            'market_state':'مضاف للمتابعة؛ مصدر الأسعار غير متصل أو غير موثق',
            'asset_class':'other','source':'قائمة المالك أو تنبيه موثق'})
    return rows
