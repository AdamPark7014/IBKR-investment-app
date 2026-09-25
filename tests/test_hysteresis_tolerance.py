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
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0},
        index=idx,
    )
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


def test_tolerance_cases() -> None:
    data = _mk(5)
    from ibtrader.strategy.base import Strategy
    class Target100(Strategy):
        def generate_signals(self, data):
            import pandas as pd
            # Always 100% long equivalent via +1
            idx = next(iter(data.values())).index
            return {"SPY": pd.Series(1, index=idx)}
    from ibtrader.backtest.engine import backtest
    from ibtrader.config import CommissionConfig, SlippageConfig
    # 100 vs 100 -> 0 orders beyond initial
    res = backtest(data, Target100(), CommissionConfig(), SlippageConfig(), rebalance_band_pct=0.0)
    # initial entry only
    assert res.stats.trade_count == 1

