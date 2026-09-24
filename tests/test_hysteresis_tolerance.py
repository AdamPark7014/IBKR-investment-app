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


def _mk(len_days: int = 60) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=len_days)
    px = pd.Series(100.0 + 0.1 * np.arange(len_days), index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    return {"SPY": df}


def test_hysteresis_allows_initial_entry_blocks_micro_rebalances() -> None:
    data = _mk()
    res = backtest(
        data=data,
        strategy=AlwaysLong(),
        commission_cfg=CommissionConfig(),
        slippage_cfg=SlippageConfig(),
        rebalance_band_pct=0.02,
    )
    # Expect exactly one trade (initial entry)
    assert res.stats.trade_count == 1

