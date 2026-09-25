from __future__ import annotations

import pytest

from ibtrader.config import RiskConfig


def test_percent_limits_upper_bound() -> None:
    with pytest.raises(Exception):
        _ = RiskConfig(daily_loss_limit_pct=101.0)
    with pytest.raises(Exception):
        _ = RiskConfig(cumulative_loss_limit_pct=100.1)
    with pytest.raises(Exception):
        _ = RiskConfig(drawdown_limit_pct=150.0)
    with pytest.raises(Exception):
        _ = RiskConfig(stop_loss_per_position_pct=200.0)


def test_cooldown_bars_non_negative() -> None:
    with pytest.raises(Exception):
        _ = RiskConfig(cooldown_bars=-5)

