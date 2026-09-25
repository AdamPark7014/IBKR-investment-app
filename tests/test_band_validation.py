from __future__ import annotations

import pytest
import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, SlippageConfig
from ibtrader.strategy.sma_crossover import SMACrossover


def _mk(len_days: int = 30) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=len_days)
    import numpy as np
    px = pd.Series(100.0 + np.arange(len_days, dtype=float), index=idx).astype(float)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0},
        index=idx,
    )
    return {"SPY": df}


def test_band_validation_rejects_gt_one() -> None:
    data = _mk()
    strat = SMACrossover(fast_window=5, slow_window=10, allow_short=False)
    with pytest.raises(ValueError):
        backtest(
            data=data,
            strategy=strat,
            commission_cfg=CommissionConfig(),
            slippage_cfg=SlippageConfig(),
            rebalance_band_pct=1.5,
        )
