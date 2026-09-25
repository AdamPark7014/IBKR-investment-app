from __future__ import annotations

from pathlib import Path

import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        return {list(data.keys())[0]: pd.Series(1, index=idx, dtype=int)}


def _mk_prices_with_stop() -> pd.DataFrame:
    # Day 1 open=100 -> enter; day 2 open=90 (stop 5%); then 100
    idx = pd.bdate_range("2024-03-01", periods=4)
    opens = [100.0, 90.0, 100.0, 100.0]
    px = pd.Series(opens, index=idx).astype(float)
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)


def test_engine_stop_loss_forces_exit_and_cooldown() -> None:
    df = _mk_prices_with_stop()
    rcfg = RiskConfig(stop_loss_per_position_pct=5.0, cooldown_bars=1, killswitch_file="./data/NO_KILL")
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # Expect at least one negative delta (exit) due to stop on day 2
    assert any(int(q) < 0 for *_, q, _ in res.trades)
    # Position should be zero on stop day and next day due to cooldown
    pos = res.positions["SPY"].astype(int)
    assert pos.iloc[2] == 0
    assert pos.iloc[3] == 0


def test_engine_emergency_exit_flattens_and_blocks_reentry(tmp_path) -> None:
    idx = pd.bdate_range("2024-04-01", periods=5)
    px = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    ks = Path(tmp_path) / "KILL_SWITCH"
    ks.write_text("HALT", encoding="utf-8")
    rcfg = RiskConfig(
        killswitch_file=str(ks),
        emergency_flatten_on_kill=True,
        killswitch_action="flatten",
        cooldown_bars=2,
    )
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # With kill active from start, opens are vetoed; ensure no positive qty trades
    assert all(int(q) <= 0 for *_, q, _ in res.trades)
    # Positions remain flat through the series
    assert res.positions["SPY"].abs().sum() == 0

