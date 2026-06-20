"""Cron expression validation, timezone checks, and next-fire computation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

DEFAULT_TIMEZONE = "Asia/Shanghai"
MISFIRE_GRACE_SECONDS = 60


def validate_timezone(tz: str) -> Optional[str]:
    try:
        ZoneInfo(tz)
        return None
    except ZoneInfoNotFoundError:
        return f"unknown timezone: {tz!r}"


def validate_cron(expr: str, tz: str = DEFAULT_TIMEZONE) -> Optional[str]:
    tz_err = validate_timezone(tz)
    if tz_err is not None:
        return tz_err
    try:
        CronTrigger.from_crontab(expr, timezone=tz)
        return None
    except Exception as exc:
        return str(exc)


def compute_next_fires(
    expr: str,
    tz: str = DEFAULT_TIMEZONE,
    *,
    n: int = 3,
    after: Optional[datetime] = None,
) -> list[datetime]:
    trigger = CronTrigger.from_crontab(expr, timezone=tz)
    fires: list[datetime] = []
    previous: Optional[datetime] = None
    now = after or datetime.now(timezone.utc)
    for _ in range(max(n, 0)):
        nxt = trigger.get_next_fire_time(previous, now)
        if nxt is None:
            break
        fires.append(nxt)
        previous = nxt
        now = nxt
    return fires


def misfire_grace_time(policy: str) -> Optional[int]:
    """APScheduler misfire grace: ``skip`` drops late ticks; ``catch_up`` always runs."""
    if policy == "catch_up":
        return None
    return MISFIRE_GRACE_SECONDS


__all__ = [
    "DEFAULT_TIMEZONE",
    "MISFIRE_GRACE_SECONDS",
    "compute_next_fires",
    "misfire_grace_time",
    "validate_cron",
    "validate_timezone",
]
