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
    # Activate killswitch using an isolated tmp path (never touch real ./data/KILL_SWITCH)
    ks = tmp_path / "KILL_SWITCH"
    ks.write_text("HALT", encoding="utf-8")
    cfg = RiskConfig(killswitch_file=str(ks))
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
    assert all(int(q) <= 0 for *_, q, _, _ in res.trades)
    # Now test that an existing position can be flattened while kill is ACTIVE.
    # We first allow entry (kill OFF initially), then activate kill for subsequent bars.
    os.remove(ks)
    rcfg2 = RiskConfig(
        stop_loss_per_position_pct=5.0,
        cooldown_bars=1,
        killswitch_file=str(ks),
        emergency_flatten_on_kill=True,
        killswitch_action="flatten",
    )
    rm2 = RiskManager(rcfg2, RiskState(starting_equity_today=100_000.0))
    # Deterministic dynamic activation: OFF on days <= t2, ON from t3 onward
    idx = df.index
    from pandas import Timestamp
    def ks_active():
        cur = rm2.state.current_date
        return bool(cur and Timestamp(cur) >= idx[2])
    monkeypatch.setattr(rm2, "killswitch_active", ks_active)
    # Create a drop to also be eligible for stop loss if needed
    df2 = df.copy()
    df2.iloc[2, df2.columns.get_loc("close")] = df2.iloc[1]["close"] * 0.90
    # Assert kill is OFF before run
    from ibtrader.risk.state_machine import Intent
    ok_before, msg_before = rm2.check_killswitch(Intent.OPEN)
    assert ok_before, f"pre-run kill-switch should be off: {msg_before}"
    res2 = backtest(
        {"SPY": df2.iloc[:4]},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm2,
    )
    # Expect at least one negative delta (flatten/exit) while kill is ACTIVE
    assert any(int(q) < 0 for *_, q, _ in res2.trades)


def test_killswitch_flatten_vs_block_new_only(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Prepare price series with an existing open, then activate kill-switch
    idx = pd.bdate_range("2024-01-01", periods=4)
    px = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    ks = tmp_path / "KILL_SWITCH"
    # Case 1: killswitch_action=flatten -> positions are liquidated at next open
    ks.write_text("HALT", encoding="utf-8")
    rcfg_flat = RiskConfig(killswitch_file=str(ks), emergency_flatten_on_kill=True, killswitch_action="flatten")
    rm_flat = RiskManager(rcfg_flat, RiskState(starting_equity_today=100_000.0))
    res_flat = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm_flat,
    )
    # No opens (vetoed) but if any position existed it would be flattened; start flat => 0 trades
    assert all(int(q) <= 0 for *_, q, _ in res_flat.trades)
    # Case 2: killswitch_action=block_new_only -> no forced flatten, but new opens still blocked
    os.remove(ks)
    rcfg_block = RiskConfig(
        killswitch_file=str(ks),
        emergency_flatten_on_kill=False,
        killswitch_action="block_new_only",
    )
    rm_block = RiskManager(rcfg_block, RiskState(starting_equity_today=100_000.0))
    ks.write_text("HALT", encoding="utf-8")
    res_block = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm_block,
    )
    assert len(res_block.trades) == 0

def test_killswitch_applies_after_open_existing_position(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deterministic dynamic activation: patch RiskManager.check_killswitch to turn on at/after day 3
    idx = pd.bdate_range("2024-06-01", periods=5)
    px = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx)
    rcfg = RiskConfig(
        killswitch_file="./data/NO_KILL",
        emergency_flatten_on_kill=True,
        killswitch_action="flatten",
        cooldown_bars=1,
    )
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    # Patch method to use current_date for deterministic activation
    from pandas import Timestamp
    def ks_active():
        cur = rm.state.current_date
        return bool(cur and Timestamp(cur) >= idx[3])
    monkeypatch.setattr(rm, "killswitch_active", ks_active)
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    # Expect an entry (>0) then an emergency flatten (<0)
    qtys = [int(q) for *_, q, _, _ in res.trades]
    assert any(q > 0 for q in qtys) and any(q < 0 for q in qtys)
