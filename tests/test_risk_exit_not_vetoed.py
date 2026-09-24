from __future__ import annotations

from ibtrader.config import RiskConfig
from ibtrader.risk.manager import RiskManager, RiskState


def test_exit_not_vetoed_by_exposure() -> None:
    state = RiskState(starting_equity_today=100_000.0)
    cfg = RiskConfig(
        max_position_pct=5.0,
        max_total_exposure_pct=10.0,  # very tight
        daily_loss_limit_pct=50.0,
        max_orders_per_day=10,
        allowed_symbols=["SPY"],
        killswitch_file="./data/NO_KILL",
    )
    rm = RiskManager(cfg, state)
    # Large exposure but reducing long position -> should be allowed
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=100_000.0,
        price=500.0,
        quantity=-10,  # reduce
        current_positions_value=200_000.0,  # > exposure limit
        current_position_qty=100,  # long position
    )
    assert ok, msg
