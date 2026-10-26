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


# --------------------------------------------------------------------------- NYSE holidays / early closes

NYSE_HOLIDAYS = {
    # Published NYSE schedules.
    2024: ["2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19", "2024-07-04",
           "2024-09-02", "2024-11-28", "2024-12-25"],
    2025: ["2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
           "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25"],
    2026: ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
           "2026-09-07", "2026-11-26", "2026-12-25"],
    2027: ["2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
           "2027-09-06", "2027-11-25", "2027-12-24"],
}
NYSE_EARLY_CLOSES = {
    2024: ["2024-07-03", "2024-11-29", "2024-12-24"],
    2025: ["2025-07-03", "2025-11-28", "2025-12-24"],
    2026: ["2026-11-27", "2026-12-24"],  # July 3 2026 is the observed holiday itself
    2027: ["2027-11-26"],  # Dec 24 2027 is the observed Christmas
}


@pytest.mark.parametrize("year", sorted(NYSE_HOLIDAYS))
def test_nyse_holidays_match_the_published_schedule(year: int) -> None:
    from datetime import date

    from ibtrader.execution.session import nyse_holidays

    assert sorted(nyse_holidays(year)) == [date.fromisoformat(d) for d in NYSE_HOLIDAYS[year]]


@pytest.mark.parametrize("year", sorted(NYSE_EARLY_CLOSES))
def test_nyse_early_closes(year: int) -> None:
    from datetime import date

    from ibtrader.execution.session import nyse_early_closes

    assert sorted(nyse_early_closes(year)) == [date.fromisoformat(d) for d in NYSE_EARLY_CLOSES[year]]


def test_saturday_new_year_is_not_observed() -> None:
    from datetime import date

    from ibtrader.execution.session import is_trading_day, nyse_holidays

    # Jan 1 2028 is a Saturday: NYSE stays open on Friday Dec 31 2027.
    assert date(2027, 12, 31) not in nyse_holidays(2027)
    assert is_trading_day(date(2027, 12, 31))
    assert all(d.year == 2028 for d in nyse_holidays(2028))
    assert date(2028, 1, 1) not in nyse_holidays(2028)


def test_is_rth_closed_on_holidays_and_after_early_close() -> None:
    assert is_rth(datetime(2026, 11, 26, 11, 0, tzinfo=NY)) is False  # Thanksgiving
    assert is_rth(datetime(2026, 4, 3, 11, 0, tzinfo=NY)) is False  # Good Friday
    assert is_rth(datetime(2025, 1, 9, 11, 0, tzinfo=NY)) is False  # special closure (Carter)
    assert is_rth(datetime(2026, 11, 27, 12, 59, tzinfo=NY)) is True  # day after Thanksgiving…
    assert is_rth(datetime(2026, 11, 27, 13, 0, tzinfo=NY)) is False  # …closes at 13:00
    assert is_rth(datetime(2025, 7, 3, 13, 30, tzinfo=NY)) is False
    assert is_rth(datetime(2025, 7, 2, 15, 30, tzinfo=NY)) is True


def test_next_rth_open_skips_holidays() -> None:
    # Thanksgiving evening → Friday open; Good Friday → Monday open; Juneteenth eve → day after.
    assert next_rth_open(datetime(2026, 11, 25, 18, 0, tzinfo=NY)) == datetime(2026, 11, 27, 9, 30, tzinfo=NY)
    assert next_rth_open(datetime(2026, 4, 2, 17, 0, tzinfo=NY)) == datetime(2026, 4, 6, 9, 30, tzinfo=NY)
    assert next_rth_open(datetime(2026, 6, 19, 8, 0, tzinfo=NY)) == datetime(2026, 6, 22, 9, 30, tzinfo=NY)
    assert next_rth_open(datetime(2026, 6, 18, 8, 0, tzinfo=NY)) == datetime(2026, 6, 18, 9, 30, tzinfo=NY)


def test_simulated_broker_does_not_fill_on_a_holiday() -> None:
    from ibtrader.broker.base import Order
    from ibtrader.broker.simulated import SimulatedBroker, SimulatedMarketState
    from ibtrader.config import CommissionConfig, SlippageConfig

    thanksgiving_noon = datetime(2026, 11, 26, 12, 0, tzinfo=NY)
    b = SimulatedBroker(
        SimulatedMarketState(last_prices={"SPY": 100.0}, equity=10_000.0),
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        require_rth=True,
        now_fn=lambda: thanksgiving_noon,
    )
    b.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="MKT"))
    assert b.get_positions() == {}
