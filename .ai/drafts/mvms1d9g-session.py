from __future__ import annotations
import calendar
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

NYTZ = ZoneInfo("America/New_York")
RTH_OPEN = 9 * 60 + 30  # 09:30 in minutes
RTH_CLOSE = 16 * 60     # 16:00 in minutes
WEEKDAYS = range(0, 5)

def _normalize_ts(ts):
    if ts is None:
        return None
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()
    else:
        dt = ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(NYTZ)

def is_rth(ts):
    dt = _normalize_ts(ts)
    if dt is None:
        return False
    wd = dt.weekday()
    if wd not in WEEKDAYS:
        return False
    current_minutes = (dt.hour * 60) + dt.minute
    return RTH_OPEN <= current_minutes < RTH_CLOSE

def next_rth_open(ts):
    dt = _normalize_ts(ts)
    if dt is None:
        raise ValueError("Invalid timestamp")
    wd = dt.weekday()
    if dt.hour > 16 or (dt.hour == 16 and dt.minute >= 0):
        days_ahead = 2 - wd if dt.weekday() < 5 else 5 - wd + 2
        next_date = dt.date() + timedelta(days=days_ahead)
    elif dt.hour > 9 or (dt.hour == 9 and dt.minute > 30):
        days_ahead = 1 - wd if dt.weekday() < 4 else 5 - wd
        next_date = dt.date() + timedelta(days=days_ahead)
    else:
        next_date = dt.date()
    
    target_time = datetime.combine(next_date, time(9, 30), tzinfo=NYTZ)
    
    if next_rth_open(target_time):
        return target_time
    
    if wd < 5:
        next_monday = (7 - (dt.weekday() + 1)) % 7 + 1
        next_date = dt.date() + timedelta(days=next_monday - wd)
        return datetime.combine(next_date, time(9, 30), tzinfo=NYTZ)
    
    if wd == 5: # Saturday
        return datetime.combine(dt.date() + timedelta(days=2), time(9, 30), tzinfo=NYTZ)
    
    return datetime.combine(dt.date() + timedelta(days=1), time(9, 30), tzinfo=NYTZ)