from __future__ import annotations

import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        return {list(data.keys())[0]: pd.Series(1, index=idx, dtype=int)}


class AlwaysShort(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        return {list(data.keys())[0]: pd.Series(-1, index=idx, dtype=int)}


def test_stoploss_false_positive_no_trigger() -> None:
    # Stop = 2%; actual loss at close is -0.8% -> must NOT trigger stop
    idx = pd.bdate_range("2024-05-01", periods=4)
    open_px = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    close_px = pd.Series([100.0, 99.2, 100.0, 100.0], index=idx).astype(float)  # -0.8% at day 2 close
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame({"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0}, index=idx)
    rcfg = RiskConfig(stop_loss_per_position_pct=2.0, cooldown_bars=1, killswitch_file="./data/NO_KILL")
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # Ensure no trade labeled as stop_loss occurs
    assert all(reason != "stop_loss" for *_, reason in res.trades)


def test_stoploss_short_symmetry_triggers_on_rise() -> None:
    # For short, stop at +2% above entry: entry ~100, close at 103 (>102) should schedule stop and exit next open
    idx = pd.bdate_range("2024-06-01", periods=4)
    open_px = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    close_px = pd.Series([100.0, 103.0, 100.0, 100.0], index=idx).astype(float)
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame({"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0}, index=idx)
    rcfg = RiskConfig(stop_loss_per_position_pct=2.0, cooldown_bars=1, killswitch_file="./data/NO_KILL")
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysShort(),
        CommissionConfig(),
        SlippageConfig(),
        direction="short_only",
        risk_manager=rm,
    )
    # Expect at least one positive qty (buy to cover) due to stop-loss with reason stop_loss
    assert any(int(q) > 0 and reason == "stop_loss" for *_, q, _, reason in res.trades)
