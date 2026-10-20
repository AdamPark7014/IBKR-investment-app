from __future__ import annotations

from ibtrader.config import RiskConfig
from ibtrader.risk.manager import RiskManager, RiskState


def test_killswitch_path_error_is_fail_closed(monkeypatch, tmp_path) -> None:
    ks = tmp_path / "KILL_SWITCH"
    cfg = RiskConfig(killswitch_file=str(ks))
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))

    def boom(_path: str) -> bool:
        raise OSError("permission denied")

    monkeypatch.setattr("os.path.exists", boom)
    assert rm.killswitch_active() is True
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=100_000.0,
        price=100.0,
        quantity=10,
        current_positions_value=0.0,
        current_position_qty=0,
    )
    assert ok is False
    assert "Kill" in msg or "kill" in msg.lower()


def test_emergency_flag_cannot_open_new_position(tmp_path) -> None:
    cfg = RiskConfig(killswitch_file=str(tmp_path / "KILL_SWITCH"))
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=100_000.0,
        price=100.0,
        quantity=10,
        current_positions_value=0.0,
        current_position_qty=0,
        is_emergency=True,
    )
    assert ok is False
    assert "aumentar" in msg.lower() or "exposición" in msg.lower()


def test_stop_flag_cannot_increase_exposure(tmp_path) -> None:
    cfg = RiskConfig(killswitch_file=str(tmp_path / "KILL_SWITCH"))
    rm = RiskManager(cfg, RiskState(starting_equity_today=100_000.0))
    ok, msg = rm.approve_order(
        symbol="SPY",
        equity=100_000.0,
        price=100.0,
        quantity=5,
        current_positions_value=1000.0,
        current_position_qty=10,
        is_stop=True,
    )
    assert ok is False
    assert "aumentar" in msg.lower() or "exposición" in msg.lower()
