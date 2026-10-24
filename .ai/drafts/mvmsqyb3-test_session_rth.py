from __future__ import annotations

from datetime import datetime
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


def test_is_rth_naive_utc_converted() -> None:
    # 14:00 naive treated as UTC → 10:00 EDT on Wed 2024-06-12
    ts = datetime(2024, 6, 12, 14, 0)
    assert is_rth(ts) is True


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