"""Volatility estimation for the signal pipeline (pysystemtrade ``mixed_vol_calc`` adapted to ETFs).

All functions are pure, point-in-time and stateless: the value at date ``t`` only uses
prices up to and including ``t``. Warm-up periods are left as NaN (no backfill), so the
caller never mistakes "not enough history" for "zero risk".
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

#: Business days per year, as in pysystemtrade (``BUSINESS_DAYS_IN_YEAR``); ``sqrt(256) = 16``.
BUSINESS_DAYS_IN_YEAR: int = 256


def price_vol_daily(
    price: pd.Series,
    span: int = 35,
    long_years: int = 10,
    mix_long: float = 0.3,
    min_periods: int = 10,
    floor_quantile: float = 0.05,
) -> pd.Series:
    """Daily volatility of price *differences*, in price units.

    Steps (each one causal):

    1. ``vol_ewma``: EWMA standard deviation (``span``) of ``price.diff()``.
    2. Long-run mean of that vol over the last ``long_years`` years (``long_years * 256`` bars,
       expanding while there is less history). Mixed as
       ``(1 - mix_long) * vol_ewma + mix_long * long_mean``.
    3. Floor: the mixed vol is clipped from below at the ``floor_quantile`` quantile of its own
       history up to ``t`` (expanding quantile, never looks ahead). ``floor_quantile=0`` makes the
       floor the running minimum, i.e. a no-op.

    Returns NaN during the warm-up (first ``min_periods`` bars) and wherever the price is NaN.
    """
    if span < 1:
        raise ValueError("span must be >= 1")
    if min_periods < 1:
        raise ValueError("min_periods must be >= 1")
    if not 0.0 <= mix_long <= 1.0:
        raise ValueError("mix_long must be in [0, 1]")
    if not 0.0 <= floor_quantile <= 1.0:
        raise ValueError("floor_quantile must be in [0, 1]")

    px = price.astype(float)
    diffs = px.diff()
    vol_ewma = diffs.ewm(span=span, min_periods=min_periods, adjust=True).std()

    long_window = max(int(long_years * BUSINESS_DAYS_IN_YEAR), 1)
    long_mean = vol_ewma.rolling(window=long_window, min_periods=1).mean()
    mixed = (1.0 - mix_long) * vol_ewma + mix_long * long_mean

    floor = mixed.expanding(min_periods=min_periods).quantile(floor_quantile)
    # Where the floor is undefined (warm-up) do not clip; NaN in ``mixed`` stays NaN.
    floored = mixed.clip(lower=floor.fillna(-np.inf))
    out: pd.Series = floored.replace([np.inf, -np.inf], np.nan)
    out.name = "price_vol_daily"
    return out


def pct_vol_daily(price: pd.Series, **kwargs: Any) -> pd.Series:
    """Daily volatility as a fraction of price (``0.01`` means 1 % per day).

    ``kwargs`` are forwarded to :func:`price_vol_daily`.
    """
    px = price.astype(float)
    vol = price_vol_daily(px, **kwargs)
    out: pd.Series = (vol / px).replace([np.inf, -np.inf], np.nan)
    out.name = "pct_vol_daily"
    return out
