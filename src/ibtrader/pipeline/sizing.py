"""Volatility targeting / position sizing (pysystemtrade ``systems/positionsizing.py``) for ETFs.

ETF conventions: contract multiplier 1 and ``block_value = price * 0.01`` (the cash value of a
1 % move in one share). With a daily volatility ``pct_vol`` (fraction), the daily cash volatility
of one share is ``block_value * (pct_vol * 100) = price * pct_vol``.

Pure functions, point-in-time, fractional shares (rounding and buffering happen downstream).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: ``sqrt(256)``: converts annual cash volatility to daily.
ANNUALISATION: float = 16.0


def vol_scalar(
    price: pd.Series,
    pct_vol: pd.Series,
    capital: float,
    tau: float,
    block_value_mult: float = 0.01,
) -> pd.Series:
    """Shares held for a forecast of 10 (the "average" forecast).

    ``cash_vol_daily = capital * tau / 16``; ``block_value = price * block_value_mult``;
    ``instr_value_vol = block_value * (pct_vol * 100)``; ``vol_scalar = cash_vol_daily / instr_value_vol``.

    Example: capital 100 000, ``tau`` 0.10, price 100, ``pct_vol`` 0.01 -> 625 / 1 = 625 shares.
    NaN where the volatility is zero or undefined.
    """
    if capital <= 0:
        raise ValueError("capital must be > 0")
    if tau <= 0:
        raise ValueError("tau must be > 0")
    if block_value_mult <= 0:
        raise ValueError("block_value_mult must be > 0")
    cash_vol_daily = float(capital) * float(tau) / ANNUALISATION
    block_value = price.astype(float) * float(block_value_mult)
    instr_value_vol = block_value * (pct_vol.astype(float) * 100.0)
    out: pd.Series = (cash_vol_daily / instr_value_vol).replace([np.inf, -np.inf], np.nan)
    out.name = "vol_scalar"
    return out


def subsystem_position(vol_scalar: pd.Series, forecast: pd.Series) -> pd.Series:
    """``vol_scalar * forecast / 10`` (fractional shares; forecast 10 -> exactly ``vol_scalar``)."""
    out: pd.Series = vol_scalar.astype(float) * forecast.astype(float) / 10.0
    out.name = "subsystem_position"
    return out


def position_to_weight(shares: pd.Series, price: pd.Series, capital: float) -> pd.Series:
    """Notional weight of a position: ``shares * price / capital``."""
    if capital <= 0:
        raise ValueError("capital must be > 0")
    out: pd.Series = shares.astype(float) * price.astype(float) / float(capital)
    out.name = "weight"
    return out
