"""General FX session clock for dashboard visibility; not a contract-hours oracle."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MUSCAT = ZoneInfo("Asia/Muscat")


def _next_weekday(dt, weekday, hour, minute=0):
    delta = (weekday - dt.weekday()) % 7
    candidate = (dt + timedelta(days=delta)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= dt:
        candidate += timedelta(days=7)
    return candidate


def status(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    # General FX weekly window: Sunday 22:00 UTC through Friday 22:00 UTC.
    weekday, seconds = now.weekday(), now.hour * 3600 + now.minute * 60 + now.second
    weekly_open = ((0 <= weekday <= 3) or
                   (weekday in (4, 5) and seconds < 22 * 3600) or
                   (weekday == 6 and seconds >= 22 * 3600))
    if weekly_open:
        next_close = now.replace(hour=22, minute=0, second=0, microsecond=0)
        days_ahead = 4 - weekday if weekday <= 4 else 6
        next_close += timedelta(days=days_ahead)
        state, target, label = "OPEN", next_close, "الإغلاق الأسبوعي العام"
    else:
        target = _next_weekday(now, 6, 22)
        state, label = "CLOSED", "الافتتاح الأسبوعي العام"
    daily_rollover = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if daily_rollover <= now:
        daily_rollover += timedelta(days=1)
    return {
        "state": state,
        "scope": "general_forex_window",
        "warning": "ساعات العقود الآجلة تختلف حسب البورصة والعقد؛ تحقق من TradingView قبل التداول.",
        "now_utc": now.isoformat(),
        "now_muscat": now.astimezone(MUSCAT).isoformat(),
        "target_utc": target.isoformat(),
        "target_muscat": target.astimezone(MUSCAT).isoformat(),
        "target_label": label,
        "seconds_remaining": max(0, int((target - now).total_seconds())),
        "next_daily_rollover_utc": daily_rollover.isoformat(),
        "next_daily_rollover_muscat": daily_rollover.astimezone(MUSCAT).isoformat(),
    }
