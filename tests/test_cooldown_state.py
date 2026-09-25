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


def _mk_with_stop_trigger(cooldown_after: int) -> pd.DataFrame:
    """
    Day 1 opens at 100 -> entry.
    Day 2 opens at 90 (10% drop) triggers stop (e.g., 5%).
    Subsequent days at 100 to test cooldown re-entry timing.
    """
    idx = pd.bdate_range("2024-01-01", periods=5 + cooldown_after)
    opens = [100.0, 90.0] + [100.0] * (len(idx) - 2)
    px = pd.Series(opens, index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    return df


def test_cooldown_off_by_one() -> None:
    # cooldown_bars=1 should block the very next bar only
    df = _mk_with_stop_trigger(cooldown_after=2)
    rcfg = RiskConfig(stop_loss_per_position_pct=5.0, cooldown_bars=1)
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest({"SPY": df}, AlwaysLong(), CommissionConfig(), SlippageConfig(), direction="long_only", risk_manager=rm)
    # Extract positions per day to check re-entry timing
    pos = list(res.positions["SPY"].astype(int).values)
    # Day 1: enter > 0; Day 2: stop -> 0; Day 3: cooldown active -> still 0; Day 4+: allowed to re-enter
    assert pos[0] == 0  # first day no execution
    assert pos[1] != 0  # after day 1 open fill, position reflected at close
    assert pos[2] == 0  # stopped
    assert pos[3] == 0  # cooldown blocks immediate re-entry
    # If more days exist, allow re-entry after exactly one blocked bar
    if len(pos) > 4:
        assert any(p != 0 for p in pos[4:])


def _mk_simple_uptrend(days: int = 6) -> pd.DataFrame:
    idx = pd.bdate_range("2024-02-01", periods=days)
    px = pd.Series([100.0 + i for i in range(days)], index=idx).astype(float)
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)


def test_two_backtests_in_one_process_are_identical() -> None:
    df = _mk_simple_uptrend(20)
    rcfg = RiskConfig(stop_loss_per_position_pct=0.0, cooldown_bars=0)
    rm1 = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    rm2 = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    r1 = backtest({"SPY": df}, AlwaysLong(), CommissionConfig(), SlippageConfig(), direction="long_only", risk_manager=rm1)
    r2 = backtest({"SPY": df}, AlwaysLong(), CommissionConfig(), SlippageConfig(), direction="long_only", risk_manager=rm2)
    assert list(r1.equity_curve.values) == list(r2.equity_curve.values)
    assert r1.stats.trade_count == r2.stats.trade_count
    assert r1.stats.total_commission == r2.stats.total_commission

