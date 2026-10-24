from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
_RTH_START = time(9, 30)
_RTH_END = time(16, 0)

def _to_ny(ts):
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if not isinstance(ts, datetime):
        raise TypeError(f"expected datetime or Timestamp, got {type(ts)!r}")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(NY)

def is_rth(ts):
    dt = _to_ny(ts)
    if dt.weekday() > 4:
        return False
    t = dt.timetz().replace(tzinfo=None)
    return _RTH_START <= t < _RTH_END

def next_rth_open(ts):
    dt = _to_ny(ts)
    open_today = datetime.combine(dt.date(), _RTH_START, tzinfo=NY)
    if dt.weekday() <= 4 and dt < open_today:
        return open_today
    d = dt.date() + timedelta(days=1)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return datetime.combine(d, _RTH_START, tzinfo=NY)