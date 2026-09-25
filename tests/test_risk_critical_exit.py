from __future__ import annotations

from ibtrader.config import RiskConfig
from ibtrader.risk.manager import RiskManager, RiskState


def test_critical_exit_cumulative_loss_close_allowed() -> None:
    # Initial capital 100k, open position, cumulative loss >=5%, lock active; close accepted, position -> 0
    state = RiskState(
        starting_equity_today=100_000.0,
        first_equity=100_000.0,
        peak_equity=100_000.0,
    )
    cfg = RiskConfig(
        max_position_pct=100.0,
        max_total_exposure_pct=100.0,
        daily_loss_limit_pct=5.0,
        cumulative_loss_limit_pct=5.0,
        drawdown_limit_pct=10.0,
        max_orders_per_day=50,
        killswitch_file="./data/NO_KILL",
    )
    rm = RiskManager(cfg, state)
    rm.on_new_day("2024-01-01", 100_000.0)
    # Equity drops by 6% vs first_equity → restrict
    ok, _ = rm.check_cumulative_loss(94_000.0)
    assert not ok
    # Attempt to CLOSE an open 100-share long
    ok, msg = rm.approve_order(
        "SPY",
        equity=94_000.0,
        price=94.0,
        quantity=-100,
        current_positions_value=9_400.0,
        current_position_qty=100,
    )
    assert ok, msg

def test_partial_exit_and_stop_emergency_allowed() -> None:
    state = RiskState(
        starting_equity_today=100_000.0,
        first_equity=100_000.0,
        peak_equity=100_000.0,
    )
    cfg = RiskConfig(
        max_position_pct=100.0,
        max_total_exposure_pct=100.0,
        daily_loss_limit_pct=5.0,
        cumulative_loss_limit_pct=5.0,
        drawdown_limit_pct=10.0,
        max_orders_per_day=50,
        killswitch_file="./data/NO_KILL",
    )
    rm = RiskManager(cfg, state)
    rm.on_new_day("2024-01-02", 100_000.0)
    # Trigger daily loss
    ok, _ = rm.check_daily_loss(94_000.0)
    assert not ok
    # Partial exit allowed
    ok, msg = rm.approve_order(
        "SPY",
        equity=94_000.0,
        price=94.0,
        quantity=-10,
        current_positions_value=9_400.0,
        current_position_qty=100,
    )
    assert ok, msg
    # Stop-loss allowed
    ok, msg = rm.approve_order(
        "SPY",
        equity=94_000.0,
        price=93.0,
        quantity=-5,
        current_positions_value=9_300.0,
        current_position_qty=90,
        is_stop=True,
    )
    assert ok, msg
    # Emergency exit allowed
    ok, msg = rm.approve_order(
        "SPY",
        equity=93_000.0,
        price=93.0,
        quantity=-90,
        current_positions_value=8_370.0,
        current_position_qty=90,
        is_emergency=True,
    )
    assert ok, msg

