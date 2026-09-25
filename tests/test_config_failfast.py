from __future__ import annotations

import os
import pytest

from ibtrader.config import AppSettings


def test_rebalance_band_pct_out_of_range_raises() -> None:
    from ibtrader.backtest.engine import backtest
    from ibtrader.strategy.sma_crossover import SMACrossover
    from ibtrader.config import CommissionConfig, SlippageConfig
    import pandas as pd
    idx = pd.bdate_range("2024-01-01", periods=30)
    px = pd.Series(100.0 + range(30), index=idx).astype(float)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0},
        index=idx,
    )
    with pytest.raises(ValueError):
        backtest({"SPY": df}, SMACrossover(5, 10, False), CommissionConfig(), SlippageConfig(), rebalance_band_pct=1.2)


def test_invalid_env_type_raises(monkeypatch) -> None:
    # Wrong type for integer should raise on settings load
    monkeypatch.setenv("RISK__MAX_ORDERS_PER_DAY", "abc")
    with pytest.raises(Exception):
        _ = AppSettings()

