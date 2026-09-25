from __future__ import annotations

import pandas as pd

from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysOpen(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        # Try to be long every day after first
        sig = pd.Series(0, index=idx, dtype=int)
        if len(idx) >= 2:
            sig.iloc[1:] = 1
        return {list(data.keys())[0]: sig}


def test_drawdown_persistence_blocks_opens_across_days() -> None:
    # Simulate across days directly on the RiskManager to assert persistent restriction
    cfg = RiskConfig(drawdown_limit_pct=1.0, killswitch_file="./data/NO_KILL")
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))
    # Day 1 start
    rm.on_new_day("2024-02-01", 100_000.0)
    # Day 1 close falls to 98k (drawdown > 1% from 100k peak)
    rm.update_equity(98_000.0)
    # Day 2 start at 98k (still below peak); drawdown restriction should be active
    rm.on_new_day("2024-02-02", 98_000.0)
    # Attempt to open a new position should be blocked by drawdown restriction
    ok, _ = rm.approve_order(
        symbol="SPY",
        equity=98_000.0,
        price=100.0,
        quantity=10,
        current_positions_value=0.0,
        current_position_qty=0,
    )
    assert not ok

