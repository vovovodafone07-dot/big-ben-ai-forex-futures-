"""Optional arithmetic scalp scenarios attached to original TradingView signals.
No new entry signals, strategy edits, execution, or profitability estimates.
"""
import importlib.util
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_CEILING
from pathlib import Path

try:
    from . import instruments as _instruments
except (ImportError, ValueError):
    try:
        import instruments as _instruments
    except ImportError:
        _ispec = importlib.util.spec_from_file_location("scalping_instruments", Path(__file__).with_name("instruments.py"))
        _instruments = importlib.util.module_from_spec(_ispec)
        _ispec.loader.exec_module(_instruments)


def _normalize_symbol(value):
    return _instruments.normalize(value)

def levels(data, scalp_rr=1):
    try:
        if isinstance(scalp_rr, bool):
            raise ValueError()
        rr = Decimal(str(scalp_rr))
        if not rr.is_finite() or not Decimal("0.5") <= rr <= Decimal("3"):
            raise ValueError()
        side = data["event"]
        if side not in ("BUY", "SELL"):
            raise ValueError()
        numbers = []
        for key in ("entry", "sl", "tp", "rr"):
            if isinstance(data[key], bool):
                raise ValueError()
            number = Decimal(str(data[key]))
            if not number.is_finite() or number <= 0 or not math.isfinite(float(number)):
                raise ValueError()
            numbers.append(number)
        entry, stop, target, original_rr = numbers
        if not (stop < entry < target if side == "BUY" else target < entry < stop):
            raise ValueError()
        risk = abs(entry - stop)
        measured_rr = abs(target - entry) / risk
        if abs(measured_rr - original_rr) > max(Decimal(".03"), original_rr * Decimal(".03")):
            raise ValueError()
        # A scalp target must stay at or before the original full target.
        requested_rr = min(rr, measured_rr)
        scalp_target = entry + (risk * requested_rr if side == "BUY" else -risk * requested_rr)
        tick = data.get("tick_size")
        tick_verified = False
        if tick is not None:
            if isinstance(tick, bool):
                raise ValueError()
            tick = Decimal(str(tick))
            if not tick.is_finite() or tick <= 0:
                raise ValueError()
            # Round toward entry, never beyond the requested reward.
            mode = ROUND_FLOOR if side == "BUY" else ROUND_CEILING
            scalp_target = (scalp_target / tick).to_integral_value(rounding=mode) * tick
            tick_verified = True
        if not (entry < scalp_target <= target if side == "BUY" else target <= scalp_target < entry):
            raise ValueError()
        return {"full_trade": {"entry": float(entry), "sl": float(stop), "tp": float(target),
                               "rr": float(original_rr), "actual_rr": float(measured_rr)},
                "scalp": {"entry": float(entry), "sl": float(stop), "tp": float(scalp_target),
                          "rr": float(abs(scalp_target-entry)/risk),
                          "requested_rr": float(rr), "tick_size_verified": False,
                          "tick_size_provided": tick_verified,
                          "mode": "hypothetical_alternative"},
                "shared_risk": True}
    except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError) as error:
        raise ValueError("invalid_scalp_parameters_or_signal") from error

def scenarios(rows, scalp_rr=1, now=None):
    # Validate settings even when there are no signals.
    levels({"event":"BUY","entry":100,"sl":99,"tp":103,"rr":3},scalp_rr)
    now = now or datetime.now(timezone.utc)
    events = []
    for symbol, event, source_time, payload in rows:
        try:
            symbol = _normalize_symbol(symbol)
            stamp = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                continue
            data = json.loads(payload)
            if not isinstance(data, dict):
                continue
            events.append((stamp.astimezone(timezone.utc),symbol,event,data))
        except (ValueError, TypeError, AttributeError):
            continue
    events.sort(key=lambda item:item[0],reverse=True)
    chosen=set()
    result=[]
    rejected={"stale_or_future":0,"invalid_levels":0,"closed_observed":0}
    for stamp,symbol,side,data in events:
        if side not in ("BUY","SELL") or symbol in chosen:
            continue
        chosen.add(symbol)
        age=(now-stamp).total_seconds()
        if age<0 or age>=720:
            rejected["stale_or_future"]+=1
            continue
        try:
            pair=levels({**data,"event":side},scalp_rr)
        except ValueError:
            rejected["invalid_levels"]+=1
            continue
        closed=False
        scalp_reached=False
        for ht,hs,he,hdata in events:
            if hs!=symbol or he!="HEARTBEAT" or not stamp<ht<=now:
                continue
            try:
                close=Decimal(str(hdata["close"]))
                if not close.is_finite() or close<=0:
                    continue
                full=pair["full_trade"]
                scalp_target=Decimal(str(pair["scalp"]["tp"]))
                if (close>=scalp_target if side=="BUY" else close<=scalp_target):
                    scalp_reached=True
                if (close<=Decimal(str(full["sl"])) or close>=Decimal(str(full["tp"]))) if side=="BUY" else (close>=Decimal(str(full["sl"])) or close<=Decimal(str(full["tp"]))):
                    closed=True
                    break
            except (KeyError,InvalidOperation,ValueError,TypeError):
                continue
        if closed:
            rejected["closed_observed"]+=1
            continue
        result.append({"event_id":data.get("event_id"),"symbol":symbol,"event":side,
                       "strategy_version":data.get("strategy_version","unreported"),
                       "source_time":stamp.isoformat(),"received_at":data.get("received_at"),
                       "age_seconds":int(age),"timeframe":data.get("timeframe"),
                       "timeframe_verified":data.get("timeframe") in ("5","M5","5m"),
                       "scalp_outcome":"target_close_observed" if scalp_reached else "unresolved",
                       **pair})
    return {"mode":"optional_scenarios_from_received_signals","scalp_rr":float(scalp_rr),
            "generated_at":now.isoformat(),"signals":result,"count":len(result),
            "excluded":rejected,"display_max_age_seconds":720,
            "limitations":["السكالب بديل حسابي، وليس إشارة مستقلة أو هدفًا مثبتًا بالباك تيست",
                           "الخياران يشتركان في الدخول والوقف؛ فتحهما معًا يضاعف التعرض",
                           "السبريد والعمولة والانزلاق غير محسوبة",
                           "لم يتم التحقق من الأسعار الحالية أو حجم التيك إلا إذا ورد في المصدر",
                           "إغلاق M5 لا يثبت ترتيب لمس الوقف والهدف داخل الشمعة"]}
