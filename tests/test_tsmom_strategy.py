from __future__ import annotations

import pandas as pd

from ibtrader.strategy.tsmom import TimeSeriesMomentum


def test_tsmom_warmup_is_flat_not_risk_on() -> None:
    idx = pd.bdate_range("2024-01-01", periods=10)
    px = pd.Series(range(100, 110), index=idx, dtype=float)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx
    )
    strat = TimeSeriesMomentum(lookback=5, allow_short=True)
    sig = strat.generate_signals({"SPY": df})["SPY"]
    # First lookback bars must be flat (0)
    assert (sig.iloc[:5] == 0).all()
    # After warmup, rising prices → long
    assert int(sig.iloc[-1]) == 1


def test_tsmom_short_on_decline() -> None:
    idx = pd.bdate_range("2024-01-01", periods=10)
    px = pd.Series(range(110, 100, -1), index=idx, dtype=float)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx
    )
    strat = TimeSeriesMomentum(lookback=5, allow_short=True)
    sig = strat.generate_signals({"SPY": df})["SPY"]
    assert int(sig.iloc[-1]) == -1
