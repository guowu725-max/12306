#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pure helpers for daily scheduling and confirmation expiry."""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple


_DAILY_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")


def china_now() -> datetime:
    """Return a naive China Standard Time timestamp, matching existing models."""
    return datetime.utcnow() + timedelta(hours=8)


def resolve_train_date(
    train_date: str,
    date_strategy: str,
    date_offset_days: int,
    now: Optional[datetime] = None,
) -> str:
    """Resolve the effective travel date for a task run."""
    strategy = (date_strategy or "fixed").strip().lower()
    if strategy == "fixed":
        try:
            datetime.strptime(train_date, "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ValueError("fixed date strategy requires YYYY-MM-DD train_date") from exc
        return train_date

    if strategy == "offset":
        try:
            offset = int(date_offset_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("date_offset_days must be an integer") from exc
        if offset < 0:
            raise ValueError("date_offset_days cannot be negative")
        base = now or china_now()
        return (base.date() + timedelta(days=offset)).isoformat()

    raise ValueError(f"unsupported date strategy: {date_strategy}")


def parse_daily_start_time(value: str) -> Tuple[int, int]:
    """Parse strict HH:MM into hour/minute suitable for APScheduler cron."""
    match = _DAILY_TIME_RE.fullmatch(value or "")
    if not match:
        raise ValueError("daily_start_time must use HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("daily_start_time is outside valid clock range")
    return hour, minute


def clamp_confirmation_expiry(value: int) -> int:
    """Limit a confirmation window to the approved 15-300 second range."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 60
    return max(15, min(300, seconds))
