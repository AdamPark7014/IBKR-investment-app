from __future__ import annotations

from datetime import datetime

from ibtrader.execution.session import ET, is_rth, next_rth_open


def test_is_rth_weekday_open() -> None:
    ts = datetime(2024, 6, 3, 14, 0, tzinfo=ET)  # Monday
    assert is_rth(ts) is True


def test_is_rth_before_open() -> None:
    ts = datetime(2024, 6, 3, 9, 0, tzinfo=ET)
    assert is_rth(ts) is False


def test_is_rth_weekend() -> None:
    ts = datetime(2024, 6, 1, 12, 0, tzinfo=ET)  # Saturday
    assert is_rth(ts) is False


def test_next_rth_open_friday_after() -> None:
    ts = datetime(2024, 6, 7, 17, 0, tzinfo=ET)  # Friday after close
    nxt = next_rth_open(ts)
    assert nxt.weekday() == 0  # Monday
    assert nxt.hour == 9 and nxt.minute == 30
