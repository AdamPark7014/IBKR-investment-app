from __future__ import annotations

from ibtrader.config import RiskConfig
from ibtrader.risk.manager import RiskManager, RiskState


def test_fsm_blocks_open_in_restricted_allows_reduce_close() -> None:
    state = RiskState(starting_equity_today=100_000.0)
    cfg = RiskConfig(
        max_position_pct=5.0,
        max_total_exposure_pct=10.0,
        daily_loss_limit_pct=5.0,
        max_orders_per_day=50,
        killswitch_file="./data/NO_KILL",
    )
    rm = RiskManager(cfg, state)
    rm.on_new_day("2024-01-01", 100_000.0)
    # Enter restricted by simulating daily loss
    ok, _ = rm.check_daily_loss(current_equity=94_000.0)
    assert not ok
    # Opening a new position should be blocked
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=94_000.0,
        price=100.0,
        quantity=10,
        current_positions_value=0.0,
        current_position_qty=0,
    )
    assert not ok and "no permitida" in msg.lower()
    # Increasing existing long should be blocked
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=94_000.0,
        price=100.0,
        quantity=10,
        current_positions_value=10_000.0,
        current_position_qty=100,
    )
    assert not ok
    # Reducing should be allowed
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=94_000.0,
        price=100.0,
        quantity=-10,
        current_positions_value=10_000.0,
        current_position_qty=100,
    )
    assert ok, msg
    # Closing should be allowed
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=94_000.0,
        price=100.0,
        quantity=-100,
        current_positions_value=10_000.0,
        current_position_qty=100,
    )
    assert ok, msg

