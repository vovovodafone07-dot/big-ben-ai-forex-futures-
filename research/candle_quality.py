"""Strict M5 history validation. Calendar gaps are reported, never filled."""
import math
from datetime import datetime, timezone

class DataQualityError(ValueError):
    pass

def validate_candles(rows, now=None):
    now = now or datetime.now(timezone.utc)
    normalized = []
    previous = None
    gaps = []
    for index, row in enumerate(rows):
        try:
            stamp = datetime.fromisoformat(str(row["time"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timezone required")
            stamp = stamp.astimezone(timezone.utc)
            if (now - stamp).total_seconds() < 300:
                raise ValueError("future or unclosed M5 candle")
            values = {key: float(row[key]) for key in ("open", "high", "low", "close")}
            if any(isinstance(row[key], bool) for key in values):
                raise ValueError("boolean OHLC")
            if not all(math.isfinite(value) and value > 0 for value in values.values()):
                raise ValueError("nonfinite or nonpositive OHLC")
            if values["high"] < max(values.values()) or values["low"] > min(values.values()):
                raise ValueError("invalid OHLC bounds")
            if previous is not None:
                seconds = (stamp - previous).total_seconds()
                if seconds < 300 or seconds % 300 != 0:
                    raise ValueError("duplicate, unordered or non-M5 cadence")
                if seconds > 300:
                    gaps.append({"after": previous.isoformat(), "before": stamp.isoformat(),
                                 "missing_intervals": int(seconds / 300) - 1,
                                 "classification": "calendar_unverified"})
            normalized.append({"time": stamp.isoformat(), **values})
            previous = stamp
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise DataQualityError("Invalid candle at row " + str(index + 1) + ": " + str(error)) from error
    return normalized, {"candles": len(normalized), "gaps": gaps,
                        "calendar_verified": False, "synthetic_bars_created": 0}
