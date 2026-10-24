# -*- coding: utf-8 -*-
"""RTH helpers for US equities (America/New_York)."""

from __future__ import annotations

import datetime as dt
from typing import Union, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]


RTH_ZONE = ZoneInfo("America/New_York")
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
WEEKDAY_MIN = 0
WEEKDAY_MAX = 4


def _ensure_aware_naive_utc(dt_obj: dt.datetime) -> dt.datetime:
    if dt_obj.tzinfo is not None:
        return dt_obj.astimezone(RTH_ZONE)
    else:
        # Treat naive as UTC per requirements
        return dt_obj.replace(tzinfo=dt.timezone.utc).astimezone(RTH_ZONE)


def _to_datetime(dt_obj: Union[dt.datetime, "pd.Timestamp"]) -> dt.datetime:
    if hasattr(dt_obj, "to_pydatetime"):
        dt_converted = dt_obj.to_pydatetime()
    else:
        dt_converted = dt_obj
    return _ensure_aware_naive_utc(dt_converted)


def is_rth(ts: Union[dt.datetime, "pd.Timestamp"]) -> bool:
    """Check if timestamp falls within Regular Trading Hours (RTH)."""
    aware_dt = _to_datetime(ts)
    weekday = aware_dt.weekday()
    if weekday < WEEKDAY_MIN or weekday > WEEKDAY_MAX:
        return False
    hour, minute = aware_dt.hour, aware_dt.minute
    start_hour, start_minute = RTH_START.hour, RTH_START.minute
    end_hour, end_minute = RTH_END.hour, RTH_END.minute

    in_range_start = (hour > start_hour) or (hour == start_hour and minute >= start_minute)
    in_range_end = (hour < end_hour) or (hour == end_hour and minute < end_minute)

    return in_range_start and in_range_end


def next_rth_open(ts: Union[dt.datetime, "pd.Timestamp"]) -> dt.datetime:
    """Return the next RTH open datetime strictly after ts or at 09:30 if applicable."""
    aware_dt = _to_datetime(ts)

    weekday = aware_dt.weekday()

    # Handle weekend: advance to next Monday 09:30 ET
    if weekday > WEEKDAY_MAX:
        monday_add_days = (7 - weekday) + 1  # Friday -> Mon, Sat -> Mon
        open_weekday = WEEKDAY_MIN + monday_add_days
        return aware_dt.replace(hour=RTH_START.hour, minute=RTH_START.minute, second=0, microsecond=0).replace(
            weekday=open_weekday, tzinfo=RTH_ZONE
        )

    # Handle non-weekday
    if aware_dt.weekday() > WEEKDAY_MAX or aware_dt.hour > 16:
        days_to_add = (WEEKDAY_MAX + 1) - weekday - 1  # Go to next Monday? No, just next Mon.
        # Simplify: Calculate difference from today's close to next open
        today = aware_dt.date()
        next_monday = today.replace(weekday=WEEKDAY_MIN) if today.weekday() != WEEKDAY_MIN else None
        if today.weekday() >= 5:
            next_monday = (today + dt.timedelta(days=7)).replace(weekday=WEEKDAY_MIN)
        elif today.weekday() == 5:
            # Friday after market close -> Monday next week
            days_until_monday = 3
        else:
            # Saturday/Sunday logic handled above; here we are Mon-Thu.
            if today.hour >= 16 or (today.hour == 16 and today.minute >= RTH_END.minute):
                days_until_monday = 0  # Same day is after close, go to Monday? No, next trading day is same day if before close.
                # Wait: spec says "strictly after ts if outside/at-or-after close".
                # So if Friday 17:00, strictly after implies next Monday 09:30.
                days_until_monday = (WEEKDAY_MAX + 1) - today.weekday()
            else:
                # Before close, but spec says "strictly after ts" only if outside/at-or-after close.
                # If before open (Mon-Fri, hour < 9), set to same day 09:30.
                days_until_monday = 0

    if aware_dt.hour >= RTH_END.hour or (aware_dt.hour == RTH_END.hour and aware_dt.minute >= RTH_END.minute):
        # After close or exactly at close -> strictly after implies next day open?
        # Spec: "strictly after ts if outside/at-or-after close"
        # So if 16:00:00, strictly after is 17:00+ which is outside RTH, so find next open.
        # Next trading day open.
        days_until_monday = (WEEKDAY_MAX + 1) - today.weekday()

    elif aware_dt.hour < RTH_START.hour or (aware_dt.hour == RTH_START.hour and aware_dt.minute < RTH_START.minute):
        # Before open -> set to same day 09:30
        return aware_dt.replace(hour=RTH_START.hour, minute=RTH_START.minute, second=0, microsecond=0)

    else:
        # Inside RTH, strictly after means if ts is inside, we need next open which is tomorrow?
        # Re-read: "strictly after ts if outside/at-or-after close".
        # If ts is INSIDE (9:31), strictly after does not imply skipping RTH.
        # But the requirement says: "Return next RTH open ... strictly after ts if outside/at-or-after close, or same-day 09:30 if before open...".
        # What if inside? The function is named `next_rth_open`. Usually implies the opening bell of a trading session.
        # If I am at 10:00 ET, what is next_rth_open? It should probably be 16:00 (close)? No, "open".
        # Interpretation: The "next open" event. If I am inside RTH, the next "open" relative to current flow might not make sense unless we mean next session start.
        # However, standard interpretation for "next_rth_open":
        # - If before open (including same day before 9:30) -> 9:30 today.
        # - If after close (or at close) -> 9:30 tomorrow (or next Mon if weekend).
        # - If during RTH -> ambiguous, but usually implies 9:30 of the SAME DAY is not "next", it's current.
        # The prompt says: "strictly after ts if outside/at-or-after close, or same-day 09:30 if before open".
        # It does NOT specify behavior for strictly inside RTH.
        # Assumption: If inside RTH, return today's close? No, function name is next_rth_open.
        # Most logical: if inside, return today's close? Or perhaps the prompt implies we always look for the 09:30 start of a session strictly after ts.
        # "Return next RTH open ... strictly after ts". So if I am at 10:00, next RTH open is tomorrow at 09:30.
        # Yes, that fits "strictly after ts". The only exception is "if before open on a weekday", then same day.
        # So:
        # - ts < 09:30 today -> return 09:30 today.
        # - ts >= 16:00 today OR (09:30 <= ts < 16:00) -> strictly after implies next trading day's open?
        # Wait, if ts is 10:00, strictly after 10:00 that is RTH open. There is no "RTH open" at 10:01.
        # The only RTH open is 09:30.
        # Therefore:
        # - If ts < 09:30: return 09:30 today.
        # - Else (ts >= 09:30): strictly after implies we cannot be at 09:30 anymore. Next open is tomorrow's 09:30.
        days_diff = dt.datetime.now(RTH_ZONE).weekday()

    target_date = aware_dt.date() + dt.timedelta(days=(WEEKDAY_MAX - weekday) + 1 if weekday != WEEKDAY_MIN else 0)
    # Correction: Calculate exact next trading day open based on current time
    current_year, current_month, current_day = aware_dt.year, aware_dt.month, aware_dt.day
    candidate = dt.datetime(current_year, current_month, target_date.day.replace(weekday=0).day if False else 0)

    # Refined logic for next_rth_open:
    aware_dt = _to_datetime(ts)
    if aware_dt.weekday() > 4:
        # Weekend: Next Monday 09:30
        next_mon = (aware_dt.date() + dt.timedelta(days=8 - aware_dt.weekday())).replace(hour=9, minute=30, second=0, microsecond=0)
        return next_mon.replace(tzinfo=RTH_ZONE)

    # Weekday
    if aware_dt.hour < 9 or (aware_dt.hour == 9 and aware_dt.minute < 30):
        return aware_dt.replace(hour=9, minute=30, second=0, microsecond=0).replace(tzinfo=RTH_ZONE)

    # At or after 09:30: strictly after implies we need the next session's open (tomorrow or next Monday)
    if aware_dt.weekday() < 4:
        tomorrow = (aware_dt.date() + dt.timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
        return tomorrow.replace(tzinfo=RTH_ZONE)

    # Should not reach here for weekday >= 5 but just in case
    next_mon = (aware_dt.date() + dt.timedelta(days=(7 - aware_dt.weekday()) + 1)).replace(hour=9, minute=30, second=0, microsecond=0)
    return next_mon.replace(tzinfo=RTH_ZONE)