from __future__ import annotations

import os
import tempfile

from ibtrader.config import RiskConfig
from ibtrader.risk.manager import RiskManager, RiskState


def test_risk_manager_position_and_killswitch() -> None:
    state = RiskState(starting_equity_today=100_000.0)
    with tempfile.TemporaryDirectory() as td:
        ks = os.path.join(td, "KILL")
        cfg = RiskConfig(
            max_position_pct=5.0,
            max_total_exposure_pct=100.0,
            daily_loss_limit_pct=10.0,
            max_orders_per_day=1,
            allowed_symbols=["SPY"],
            killswitch_file=ks,
        )
        rm = RiskManager(cfg, state)
        # Position too large
        ok, msg = rm.approve_order(
            symbol="SPY", equity=100_000.0, price=500.0, quantity=2000, current_positions_value=0.0
        )
        assert not ok and "Tamaño de posición" in msg
        # Killswitch blocks
        with open(ks, "w", encoding="utf-8") as f:
            f.write("HALT")
        ok, msg = rm.approve_order(
            symbol="SPY", equity=100_000.0, price=500.0, quantity=10, current_positions_value=0.0
        )
        assert not ok and "Kill switch" in msg

