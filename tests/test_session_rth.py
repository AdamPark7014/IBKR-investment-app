from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from ibtrader.execution.session import is_rth, next_rth_open

NY = ZoneInfo("America/New_York")


def test_is_rth_weekday_open() -> None:
    ts = datetime(2024, 6, 12, 10, 0, tzinfo=NY)  # Wed
    assert is_rth(ts) is True


def test_is_rth_at_open_inclusive() -> None:
    ts = datetime(2024, 6, 12, 9, 30, tzinfo=NY)
    assert is_rth(ts) is True


def test_is_rth_at_close_exclusive() -> None:
    ts = datetime(2024, 6, 12, 16, 0, tzinfo=NY)
    assert is_rth(ts) is False


def test_is_rth_before_open() -> None:
    ts = datetime(2024, 6, 12, 9, 29, tzinfo=NY)
    assert is_rth(ts) is False


def test_is_rth_weekend() -> None:
    ts = datetime(2024, 6, 15, 12, 0, tzinfo=NY)  # Sat
    assert is_rth(ts) is False


def test_is_rth_naive_is_new_york_time() -> None:
    # Naive timestamps are read as America/New_York wall time (session.py), not UTC: the old test
    # said "naive treated as UTC" and only passed because 14:00 is inside the session either way.
    # 13:00 naive is open in New York but would be 09:00 EDT (closed) if it were UTC.
    assert is_rth(datetime(2024, 6, 12, 13, 0)) is True
    for hour, minute in ((9, 0), (9, 30), (12, 0), (15, 59), (16, 0), (20, 30)):
        naive = datetime(2024, 6, 12, hour, minute)
        assert is_rth(naive) is is_rth(naive.replace(tzinfo=NY)), (hour, minute)
    assert is_rth(datetime(2024, 6, 12, 9, 29)) is False
    assert is_rth(datetime(2024, 6, 12, 9, 30)) is True
    assert is_rth(datetime(2024, 6, 12, 15, 59)) is True
    assert is_rth(datetime(2024, 6, 12, 16, 0)) is False


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2024, 6, 12, 13, 29, tzinfo=timezone.utc), False),  # 09:29 EDT (UTC-4)
        (datetime(2024, 6, 12, 13, 30, tzinfo=timezone.utc), True),  # 09:30 EDT
        (datetime(2024, 6, 12, 19, 59, tzinfo=timezone.utc), True),  # 15:59 EDT
        (datetime(2024, 6, 12, 20, 0, tzinfo=timezone.utc), False),  # 16:00 EDT
        (datetime(2024, 1, 10, 14, 29, tzinfo=timezone.utc), False),  # 09:29 EST (UTC-5)
        (datetime(2024, 1, 10, 14, 30, tzinfo=timezone.utc), True),  # 09:30 EST
        (datetime(2024, 1, 10, 20, 59, tzinfo=timezone.utc), True),  # 15:59 EST
        (datetime(2024, 1, 10, 21, 0, tzinfo=timezone.utc), False),  # 16:00 EST
        (datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc), True),  # day after the DST switch: 09:30 EDT
        (datetime(2024, 11, 4, 13, 30, tzinfo=timezone.utc), False),  # day after DST ends: 08:30 EST
    ],
)
def test_is_rth_aware_utc_follows_new_york_dst(utc: datetime, expected: bool) -> None:
    assert is_rth(utc) is expected


def test_is_rth_mexico_city_clock() -> None:
    # Adam's machine runs on America/Mexico_City (UTC-6, no DST since 2022): 08:30 CDMX = 10:30 EDT.
    cdmx = ZoneInfo("America/Mexico_City")
    assert is_rth(datetime(2024, 6, 12, 8, 30, tzinfo=cdmx)) is True
    assert is_rth(datetime(2024, 6, 12, 7, 0, tzinfo=cdmx)) is False  # 09:00 EDT
    assert is_rth(datetime(2024, 1, 10, 14, 30, tzinfo=cdmx)) is True  # 15:30 EST
    assert is_rth(datetime(2024, 1, 10, 15, 0, tzinfo=cdmx)) is False  # 16:00 EST


def test_next_rth_open_before_open_same_day() -> None:
    ts = datetime(2024, 6, 12, 8, 0, tzinfo=NY)
    assert next_rth_open(ts) == datetime(2024, 6, 12, 9, 30, tzinfo=NY)


def test_next_rth_open_after_open_next_day() -> None:
    ts = datetime(2024, 6, 12, 10, 0, tzinfo=NY)
    assert next_rth_open(ts) == datetime(2024, 6, 13, 9, 30, tzinfo=NY)


def test_next_rth_open_friday_afternoon() -> None:
    ts = datetime(2024, 6, 14, 17, 0, tzinfo=NY)
    assert next_rth_open(ts) == datetime(2024, 6, 17, 9, 30, tzinfo=NY)


def test_is_rth_pandas_timestamp() -> None:
    pd = pytest.importorskip("pandas")
    ts = pd.Timestamp("2024-06-12 10:00", tz="America/New_York")
    assert is_rth(ts) is True
