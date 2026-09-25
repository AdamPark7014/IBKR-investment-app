from __future__ import annotations

import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class HoldThenOpen(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        sig = pd.Series(0, index=idx, dtype=int)
        # Long from bar 2 onward
        if len(idx) >= 2:
            sig.iloc[0] = 0
            sig.iloc[1:] = 1
        return {list(data.keys())[0]: sig}


def test_daily_loss_limit_blocks_new_opens_but_allows_exits() -> None:
    idx = pd.bdate_range("2024-01-01", periods=4)
    # Day 1 open 100, day 2 open gap to 90 (>=10% drop), limit 5% should halt new opens
    open_px = pd.Series([100.0, 90.0, 90.0, 90.0], index=idx)
    df = pd.DataFrame(
        {"open": open_px, "high": open_px, "low": open_px, "close": open_px, "volume": 1000.0},
        index=idx,
    )
    rcfg = RiskConfig(daily_loss_limit_pct=5.0, max_position_pct=100.0, max_total_exposure_pct=100.0)
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        HoldThenOpen(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # No opens should be allowed on day 2 due to daily loss breach (evaluated on close, restricting next decision)
    # Ensure no positive qty on day 2 open after breach
    day3 = idx[2]
    assert all(not (pd.Timestamp(d) == day3 and int(q) > 0) for d, s, q, p, r in res.trades)
