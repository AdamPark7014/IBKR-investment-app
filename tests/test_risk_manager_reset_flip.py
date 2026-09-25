from __future__ import annotations

from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.config import RiskConfig


def test_daily_reset_and_halt_allows_exit_and_next_day_trading() -> None:
    state = RiskState(starting_equity_today=100_000.0)
    cfg = RiskConfig(
        max_position_pct=100.0, max_total_exposure_pct=100.0, daily_loss_limit_pct=5.0, max_orders_per_day=50, killswitch_file="./data/NO_KILL"
    )
    rm = RiskManager(cfg, state)
    rm.on_new_day("2024-01-01", 100_000.0)
    # Trigger daily loss: simulate equity below threshold
    ok, msg = rm.approve_order(
        symbol="SPY", equity=94_000.0, price=100.0, quantity=0, current_positions_value=0.0, current_position_qty=0
    )
    assert not ok
    # While halted, allow reducing order
    ok, msg = rm.approve_order(
        symbol="SPY", equity=94_000.0, price=100.0, quantity=-10, current_positions_value=50_000.0, current_position_qty=100
    )
    assert ok
    # Next day resets and allows trading
    rm.on_new_day("2024-01-02", 100_000.0)
    ok, msg = rm.approve_order(
        symbol="SPY", equity=100_000.0, price=100.0, quantity=10, current_positions_value=0.0, current_position_qty=0
    )
    assert ok


def test_flip_uses_resulting_position_not_order_size() -> None:
    state = RiskState(starting_equity_today=100_000.0)
    cfg = RiskConfig(max_position_pct=100.0, max_total_exposure_pct=100.0, daily_loss_limit_pct=50.0, max_orders_per_day=50, killswitch_file="./data/NO_KILL")
    rm = RiskManager(cfg, state)
    rm.on_new_day("2024-01-01", 100_000.0)
    # Large flip order (from -500 to +500 shares): under restricted state should require OPEN leg permission
    # First, simulate restricted by daily loss
    ok, _ = rm.check_daily_loss(94_000.0)
    assert not ok
    ok, msg = rm.approve_order(
        symbol="SPY", equity=94_000.0, price=100.0, quantity=1000, current_positions_value=0.0, current_position_qty=-500
    )
    assert not ok  # flip open blocked under restriction
