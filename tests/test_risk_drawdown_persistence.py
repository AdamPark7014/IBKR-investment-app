from __future__ import annotations

import pandas as pd

from ibtrader.backtest.engine import backtest
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
    # Price falls steadily triggering drawdown > 1% early and never recovers
    idx = pd.bdate_range("2024-02-01", periods=6)
    vals = [100.0, 98.0, 97.0, 96.0, 95.0, 94.0]
    px = pd.Series(vals, index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    cfg = RiskConfig(drawdown_limit_pct=1.0, killswitch_file="./data/NO_KILL")
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysOpen(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # Expect either zero opens or an initial open followed by blocks; in any case, after breach, no increases/open
    # Concretely assert no positive qty occurs after the second date (breach happens early)
    breach_day = idx[2]
    assert all(not (pd.Timestamp(d) >= breach_day and int(q) > 0) for d, s, q, p, r in res.trades)

