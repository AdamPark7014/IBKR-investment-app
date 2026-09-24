from __future__ import annotations

import pandas as pd

from ibtrader.validation.signal import validate_sma_signal
from ibtrader.config import CommissionConfig, SlippageConfig


def _mk(len_days: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len_days)
    px = pd.Series(100.0 + (idx - idx[0]).days * 0.1, index=idx).astype(float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1_000.0}, index=idx)
    return df


def test_p7_validation_uses_open_to_open_and_commission() -> None:
    data = {"SPY": _mk()}
    # Zero costs baseline
    folds0, agg0 = validate_sma_signal(
        data, "SPY", fast=5, slow=20, direction="long_only", n_splits=3, embargo=5, commission_cfg=CommissionConfig(per_share=0.0, min_per_order=0.0), slippage_cfg=SlippageConfig(bps=0.0)
    )
    # High costs penalize returns
    folds1, agg1 = validate_sma_signal(
        data, "SPY", fast=5, slow=20, direction="long_only", n_splits=3, embargo=5, commission_cfg=CommissionConfig(per_share=0.05, min_per_order=5.0), slippage_cfg=SlippageConfig(bps=10.0)
    )
    assert agg1.mean_ret <= agg0.mean_ret + 1e-12
    assert len(folds1) == len(folds0)

