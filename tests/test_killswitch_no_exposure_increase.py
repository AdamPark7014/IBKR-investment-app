from __future__ import annotations

import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class Oscillate(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        # Alternate signals to try to cause opens/increases
        sig = pd.Series(0, index=idx, dtype=int)
        for i in range(1, len(idx)):
            sig.iloc[i] = 1 if i % 2 == 1 else -1
        return {list(data.keys())[0]: sig}


def test_no_exposure_increase_while_kill_or_halt_active(monkeypatch) -> None:
    idx = pd.bdate_range("2024-03-01", periods=12)
    px = pd.Series(100.0, index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    cfg = RiskConfig(killswitch_file="./data/NO_KILL")
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))
    # Force killswitch_active to always True
    monkeypatch.setattr(rm, "killswitch_active", lambda: True)
    res = backtest(
        {"SPY": df},
        Oscillate(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # Assert no positive qty fills occurred (no exposure-increasing orders)
    assert all(int(q) <= 0 for *_, q, _, _ in res.trades)

