from __future__ import annotations

import numpy as np
import pandas as pd


def volatility_target_weight(
    returns: pd.Series, target_vol_annual: float = 0.10, lookback: int = 20
) -> float:
    """
    Compute volatility-targeted position weight (0..1) based on recent realized vol.
    """
    ann = np.sqrt(252.0)
    vol = float(returns.tail(lookback).std(ddof=0) * ann) or 1e-9
    w = max(0.0, min(1.0, target_vol_annual / vol))
    return float(w)
