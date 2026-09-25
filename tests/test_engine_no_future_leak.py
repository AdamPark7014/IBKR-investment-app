from __future__ import annotations

import pandas as pd
import numpy as np

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, SlippageConfig
from ibtrader.strategy.sma_crossover import SMACrossover


def _mk(len_days: int = 200) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len_days)
    close = pd.Series(100.0 + 0.1 * np.arange(len_days), index=idx).astype(float)
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1000.0}, index=idx)
    return df


def test_engine_no_future_leak_in_equity() -> None:
    base = {"SPY": _mk(300)}
    res1 = backtest(base, SMACrossover(5, 20, allow_short=False), CommissionConfig(), SlippageConfig())
    # Perturb last close heavily (future info); prior equity should remain unchanged
    modified = {"SPY": base["SPY"].copy()}
    modified["SPY"].iloc[-1] = modified["SPY"].iloc[-1] * 2.0
    res2 = backtest(modified, SMACrossover(5, 20, allow_short=False), CommissionConfig(), SlippageConfig())
    # Compare equity until second last date
    e1 = res1.equity_curve.iloc[:-1]
    e2 = res2.equity_curve.iloc[:-1]
    pd.testing.assert_series_equal(e1, e2, check_names=False)
