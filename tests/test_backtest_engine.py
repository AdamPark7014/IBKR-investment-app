from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, SlippageConfig
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        out = {}
        for sym, df in data.items():
            out[sym] = pd.Series(1, index=df.index)
        return out


def test_backtest_runs_and_returns_metrics() -> None:
    idx = pd.date_range("2020-01-01", periods=100, freq="B")
    prices = pd.DataFrame(
        {
            "open": 100 + np.arange(100),
            "high": 101 + np.arange(100),
            "low": 99 + np.arange(100),
            "close": 100 + np.arange(100),
            "volume": 1_000_000,
        },
        index=idx,
    )
    data = {"SPY": prices}
    result = backtest(
        data=data,
        strategy=AlwaysLong(),
        commission_cfg=CommissionConfig(),
        slippage_cfg=SlippageConfig(),
    )
    assert result.stats.cagr > 0.0
    # With cost-aware hysteresis enabled, initial entry should still occur (trade_count >= 1)
    result_hyst = backtest(
        data=data,
        strategy=AlwaysLong(),
        commission_cfg=CommissionConfig(),
        slippage_cfg=SlippageConfig(),
        benefit_bps=1.0,
        risk_cost_bps=0.5,
    )
    assert result_hyst.stats.trade_count >= 1
    assert len(result.equity_curve) == 100




