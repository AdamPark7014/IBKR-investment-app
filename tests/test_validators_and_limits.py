from __future__ import annotations

import pandas as pd
import pytest

from ibtrader.config import RiskConfig
from ibtrader.data.validators import validate_timeseries_strict


def test_validator_rejects_rows_with_missing_ohlcv() -> None:
    idx = pd.bdate_range("2024-01-01", periods=10)
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        index=idx,
    )
    df.iloc[3, df.columns.get_loc("open")] = float("nan")
    ok, msg = validate_timeseries_strict(df)
    assert not ok and "faltantes" in msg.lower()


def test_negative_limits_fail_fast() -> None:
    with pytest.raises(Exception):
        _ = RiskConfig(daily_loss_limit_pct=-1.0)
    with pytest.raises(Exception):
        _ = RiskConfig(cumulative_loss_limit_pct=-0.1)
    with pytest.raises(Exception):
        _ = RiskConfig(drawdown_limit_pct=-10.0)
    with pytest.raises(Exception):
        _ = RiskConfig(stop_loss_per_position_pct=-5.0)
    with pytest.raises(Exception):
        _ = RiskConfig(cooldown_bars=-1)
