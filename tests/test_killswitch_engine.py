from __future__ import annotations

import os

import pandas as pd
import pytest

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        return {list(data.keys())[0]: pd.Series(1, index=idx, dtype=int)}


def _mk_series() -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=10)
    px = pd.Series(100.0, index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    return df


def test_killswitch_vetoes_opens_and_allows_flatten(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    os.makedirs("./data", exist_ok=True)
    # Activate killswitch
    with open("./data/KILL_SWITCH", "w", encoding="utf-8"):
        pass
    cfg = RiskConfig(killswitch_file="./data/KILL_SWITCH")
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))
    df = _mk_series()
    # Flat start, signal long — should NOT open due to killswitch
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # Expect zero trades because opens are vetoed
    assert len(res.trades) == 0
    # Now test flatten via stop-loss (engine forced exit), without killswitch
    os.remove("./data/KILL_SWITCH")
    rcfg2 = RiskConfig(stop_loss_per_position_pct=5.0, cooldown_bars=1, killswitch_file="./data/KILL_SWITCH")
    rm2 = RiskManager(rcfg2, RiskState(starting_equity_today=100_000.0))
    # Create a drop to trigger stop on day 3
    df2 = df.copy()
    df2.iloc[2, df2.columns.get_loc("open")] = df2.iloc[1]["open"] * 0.90
    df2.iloc[2, df2.columns.get_loc("close")] = df2.iloc[2]["open"]
    res2 = backtest(
        {"SPY": df2.iloc[:4]},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm2,
    )
    assert any(int(q) < 0 for *_, q, _ in res2.trades)
