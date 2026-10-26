"""NYSE regular trading hours, with the exchange's holidays and early closes.

Rules (NYSE Rule 7.2 and the published holiday schedules):

* Holidays: New Year's Day, Martin Luther King Jr. Day (3rd Mon of Jan), Washington's Birthday
  (3rd Mon of Feb), Good Friday, Memorial Day (last Mon of May), Juneteenth (from 2022),
  Independence Day, Labor Day (1st Mon of Sep), Thanksgiving (4th Thu of Nov) and Christmas.
  A holiday on Saturday is observed the Friday before, on Sunday the Monday after — except
  New Year's Day on a Saturday, which is not observed (the Friday is the last day of the
  year and stays open).
* Early closes at 13:00 New York: July 3 when it is a Monday–Thursday, the day after
  Thanksgiving, and December 24 when it is a Monday–Thursday.
* One-off closures announced by the exchange (national days of mourning, Sandy) are listed in
  ``SPECIAL_CLOSURES``; a future one has to be added by hand.

Naive timestamps are New York wall time; aware ones are converted (DST included).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any, FrozenSet
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)

#: Unscheduled full-day closures (exchange announcements).
SPECIAL_CLOSURES: FrozenSet[date] = frozenset(
    {
        date(2001, 9, 11),
        date(2001, 9, 12),
        date(2001, 9, 13),
        date(2001, 9, 14),
        date(2004, 6, 11),  # President Reagan
        date(2007, 1, 2),  # President Ford
        date(2012, 10, 29),  # Hurricane Sandy
        date(2012, 10, 30),
        date(2018, 12, 5),  # President G. H. W. Bush
        date(2025, 1, 9),  # President Carter
    }
)


def _as_et(ts: Any) -> datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if not isinstance(ts, datetime):
        raise TypeError(f"expected datetime-like, got {type(ts)!r}")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    return ts.astimezone(ET)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """``n``-th ``weekday`` (Mon=0) of the month; ``n=-1`` = the last one."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous / Meeus–Jones–Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> FrozenSet[date]:
    """Full-day NYSE holidays of ``year`` (observed dates) plus ``SPECIAL_CLOSURES`` in that year."""
    days = set()
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:  # Saturday New Year's Day is not observed
        days.add(_observed(new_year))
    days.add(_nth_weekday(year, 1, 0, 3))  # MLK
    days.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday
    days.add(_easter(year) - timedelta(days=2))  # Good Friday
    days.add(_nth_weekday(year, 5, 0, -1))  # Memorial Day
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))  # Juneteenth
    days.add(_observed(date(year, 7, 4)))
    days.add(_nth_weekday(year, 9, 0, 1))  # Labor Day
    days.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
    days.add(_observed(date(year, 12, 25)))
    days |= {d for d in SPECIAL_CLOSURES if d.year == year}
    return frozenset(d for d in days if d.year == year)


@lru_cache(maxsize=None)
def nyse_early_closes(year: int) -> FrozenSet[date]:
    """13:00 closes: July 3 and December 24 on Monday–Thursday, and the day after Thanksgiving."""
    days = {_nth_weekday(year, 11, 3, 4) + timedelta(days=1)}
    for d in (date(year, 7, 3), date(year, 12, 24)):
        if d.weekday() <= 3:
            days.add(d)
    return frozenset(d for d in days if d not in nyse_holidays(year))


def is_trading_day(d: Any) -> bool:
    """True on a NYSE session day (weekday that is not a holiday or special closure)."""
    day = d.date() if isinstance(d, datetime) else d
    if hasattr(day, "to_pydatetime"):
        day = day.to_pydatetime().date()
    return day.weekday() < 5 and day not in nyse_holidays(day.year)


def session_close(d: date) -> time:
    """Close time (New York) of a trading day: 13:00 on early-close days, else 16:00."""
    return _EARLY_CLOSE if d in nyse_early_closes(d.year) else _RTH_CLOSE


def is_rth(ts: Any) -> bool:
    """True inside the NYSE regular session [09:30, close) New York, on a trading day."""
    et = _as_et(ts)
    day = et.date()
    if not is_trading_day(day):
        return False
    return _RTH_OPEN <= et.time() < session_close(day)


def next_rth_open(ts: Any) -> datetime:
    """Next 09:30 New York open at or after ``ts`` (the same day if before the open)."""
    et = _as_et(ts)
    d = et.date()
    if not (is_trading_day(d) and et.time() < _RTH_OPEN):
        d = d + timedelta(days=1)
        while not is_trading_day(d):
            d = d + timedelta(days=1)
    return datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)


__all__ = [
    "ET",
    "SPECIAL_CLOSURES",
    "is_rth",
    "is_trading_day",
    "next_rth_open",
    "nyse_early_closes",
    "nyse_holidays",
    "session_close",
]
