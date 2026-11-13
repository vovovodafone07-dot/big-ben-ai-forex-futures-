"""Describe stored webhook evidence without predicting prices or issuing new trades."""
import json
import math
from datetime import datetime, timezone

def analyze_events(rows, now=None):
    now = now or datetime.now(timezone.utc)
    by_symbol = {}
    for symbol, kind, source_time, payload in rows:
        if kind != "HEARTBEAT":
            continue
        try:
            data = json.loads(payload)
            stamp = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                continue
            stamp = stamp.astimezone(timezone.utc)
            if symbol in by_symbol and stamp <= by_symbol[symbol][0]:
                continue
            by_symbol[symbol] = (stamp, data)
        except (ValueError, TypeError, AttributeError):
            continue
    result = []
    for symbol, (stamp, data) in sorted(by_symbol.items()):
        age = (now - stamp).total_seconds()
        fresh = 0 <= age < 720
        biases = {tf: data.get(tf) for tf in ("m15", "h1", "h4")}
        complete = all(type(v) in (int, float) and v in (-1, 0, 1) for v in biases.values())
        direction = "UNKNOWN"
        if fresh and complete:
            direction = "BULLISH" if all(v == 1 for v in biases.values()) else "BEARISH" if all(v == -1 for v in biases.values()) else "MIXED"
        price = data.get("close")
        if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
            price = None
        confirmed = ["آخر وقت مصدر: " + stamp.isoformat()]
        if fresh and complete:
            confirmed.append("قيم M15/H1/H4 مستلمة من المؤشر؛ لم تُحسب بصورة مستقلة")
        if not fresh:
            confirmed.append("البيانات قديمة أو مستقبلية؛ لا تدعم وصف الاتجاه الحالي")
        result.append({
            "symbol": symbol, "source_time": stamp.isoformat(),
            "received_at": data.get("received_at"), "age_seconds": round(age),
            "state": "CONNECTED" if fresh else "UNKNOWN",
            "market_state": "UNKNOWN", "source": "TradingView heartbeat",
            "observed_m5_close": price, "htf_bias": biases,
            "current_bias": direction, "confirmed_information": confirmed,
            "evidence_score": None, "new_signal": None,
            "scenarios": ["يتطلب سيناريو الدخول إشارة BUY/SELL موثقة مع Entry/SL/TP",
                          "توافق الفريمات وحده لا يثبت اختراقًا أو احتمال نجاح"],
        })
    return {"generated_at": now.isoformat(), "mode": "observed_evidence_only",
            "symbols": result, "count": len(result),
            "limitations": ["Heartbeat freshness does not verify a real-time quote entitlement",
                            "No inference of market closure without an exchange calendar",
                            "No independent ICT/SMC analysis or Pine parity asserted"]}
