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
    idx = pd.bdate_range("2024-01-01", periods=5)
    # Enter at day 2 open; day 3 closes at 94 (< -5%), so day 4 must be halted for new opens
    open_px = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    close_px = pd.Series([100.0, 100.0, 94.0, 94.0, 94.0], index=idx)
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame({"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0}, index=idx)
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
    # Ensure no positive qty on day 4 open after breach at day 3 close
    day4 = idx[3]
    assert all(not (pd.Timestamp(d) == day4 and int(q) > 0) for d, s, q, p, r in res.trades)
