from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from ibtrader.data.crosscheck import check_freshness, cross_check, last_completed_session

ET = ZoneInfo("America/New_York")


def _df(days, closes):
    return pd.DataFrame({"close": closes}, index=pd.to_datetime(days))


def test_last_completed_session_rules() -> None:
    # Mon 2026-11-09 before the close → previous Friday.
    assert last_completed_session(datetime(2026, 11, 9, 12, 0, tzinfo=ET)) == date(2026, 11, 6)
    # After close + grace → today.
    assert last_completed_session(datetime(2026, 11, 9, 16, 45, tzinfo=ET)) == date(2026, 11, 9)
    # Saturday → Friday.
    assert last_completed_session(datetime(2026, 11, 7, 10, 0, tzinfo=ET)) == date(2026, 11, 6)
    # Thanksgiving 2026-11-26 is closed → Wednesday.
    assert last_completed_session(datetime(2026, 11, 26, 18, 0, tzinfo=ET)) == date(2026, 11, 25)


def test_freshness_blocks_stale_symbol() -> None:
    now = datetime(2026, 11, 9, 17, 0, tzinfo=ET)
    frames = {"SPY": _df(["2026-11-06", "2026-11-09"], [1, 2]), "TLT": _df(["2026-11-06"], [1])}
    res = check_freshness(frames, now)
    assert not res.ok and res.stale == {"TLT": "2026-11-06"}


def test_cross_check() -> None:
    a = {"SPY": _df(["2026-11-06", "2026-11-09"], [500.0, 501.0])}
    same = {"SPY": _df(["2026-11-09"], [501.05])}
    assert cross_check(a, same).ok  # 1 bp
    off = {"SPY": _df(["2026-11-09"], [505.0])}
    res = cross_check(a, off)
    assert not res.ok and res.mismatches[0]["diff_bps"] > 70
    assert cross_check(a, {}).ok
    assert not cross_check(a, {}, require_secondary=True).ok
