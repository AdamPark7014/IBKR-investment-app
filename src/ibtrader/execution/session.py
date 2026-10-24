from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)


def _as_et(ts: Any) -> datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if not isinstance(ts, datetime):
        raise TypeError(f"expected datetime-like, got {type(ts)!r}")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    return ts.astimezone(ET)


def is_rth(ts: Any) -> bool:
    """True Mon-Fri [09:30, 16:00) America/New_York."""
    et = _as_et(ts)
    if et.weekday() >= 5:
        return False
    t = et.time()
    return _RTH_OPEN <= t < _RTH_CLOSE


def next_rth_open(ts: Any) -> datetime:
    et = _as_et(ts)
    if et.weekday() < 5 and et.time() < _RTH_OPEN:
        return et.replace(hour=9, minute=30, second=0, microsecond=0)
    d = et.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)


__all__ = ["is_rth", "next_rth_open", "ET"]
