from __future__ import annotations

from ibtrader.config import RiskConfig
from ibtrader.risk.manager import RiskManager, RiskState


def test_exit_allowed_during_crash_gap() -> None:
    # Simulate a day with crash causing daily loss breach
    state = RiskState(starting_equity_today=100_000.0)
    cfg = RiskConfig(
        max_position_pct=100.0,
        max_total_exposure_pct=100.0,
        daily_loss_limit_pct=5.0,
        max_orders_per_day=50,
        killswitch_file="./data/NO_KILL",
    )
    rm = RiskManager(cfg, state)
    rm.on_new_day("2024-01-02", 100_000.0)
    # Equity after crash
    ok, _ = rm.check_daily_loss(94_000.0)
    assert not ok
    # Attempt to exit long 100 shares at crash day -> allowed
    ok, msg = rm.approve_order(
        "SPY",
        94_000.0,
        90.0,
        -100,
        current_positions_value=9_000.0,
        current_position_qty=100,
    )
    assert ok, msg

