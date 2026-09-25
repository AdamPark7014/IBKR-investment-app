from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, SlippageConfig
from ibtrader.strategy.base import Strategy


class FlipDaily(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        sig = pd.Series(1, index=idx)
        sig.iloc[::2] = -1  # alternate long/short
        return {"SPY": sig}


def _mk(len_days: int = 40) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=len_days)
    px = pd.Series(100.0 + 0.05 * np.arange(len_days), index=idx).astype(float)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0},
        index=idx,
    )
    return {"SPY": df}


def test_high_turnover_increases_costs() -> None:
    data = _mk()
    res = backtest(data, FlipDaily(), CommissionConfig(), SlippageConfig())
    assert res.stats.total_commission > 0.0
    assert res.stats.trade_count > 10
