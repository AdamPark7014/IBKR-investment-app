"""Trading rules producing *raw* forecasts (pysystemtrade ``ewmac`` plus a multi-horizon TSMOM).

A raw forecast is a dimensionless number: price-unit numerator divided by the daily price
volatility from :mod:`ibtrader.pipeline.vol`. Raw forecasts are later scaled so that their
average absolute value is 10 (:mod:`ibtrader.pipeline.forecast`).

Everything here is point-in-time: the value at ``t`` only uses prices up to ``t``.
"""

from __future__ import annotations

import re
from typing import Dict, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

#: EWMAC variations (fast span, slow span); slow = 4 x fast as in Carver.
EWMAC_SPEEDS: Dict[str, Tuple[int, int]] = {
    "ewmac2_8": (2, 8),
    "ewmac4_16": (4, 16),
    "ewmac8_32": (8, 32),
    "ewmac16_64": (16, 64),
    "ewmac32_128": (32, 128),
    "ewmac64_256": (64, 256),
}

#: Fixed forecast scalars (raw forecast -> average |forecast| = 10).
#:
#: EWMAC values are the pysystemtrade defaults (``systems/provided/rules/ewmac.py`` /
#: ``sysdata/config/defaults.yaml``). ``tsmom_1_3_12`` is not in pysystemtrade; its value was
#: estimated with :func:`ibtrader.pipeline.forecast.estimate_forecast_scalar` (pooled
#: cross-sectional median, ``min_periods=500``) on 40 synthetic geometric random walks of 5 000
#: business days each (seeds 0..39, zero drift, 1 %/day volatility, start 100) using
#: :func:`tsmom_multi` with the default lookbacks and :func:`ibtrader.pipeline.vol.price_vol_daily`
#: with defaults; the final value of the pooled scalar was 17.98, rounded to 18.0.
#:
#: Cross-checks: for a pure random walk with known volatility the three normalised returns are
#: N(0, 1) with correlations ``sqrt(L_i / L_j)``, so their mean has sd ~0.80; the median of its
#: absolute value is ~0.54 (scalar ~18.6) and the mean ~0.64 (scalar ~15.7). The pooled estimator
#: uses the median, hence ~18. Real data with trends has larger |raw|, so the real-data value
#: should be lower (on the same walks ``ewmac16_64`` estimates 5.47 against pysystemtrade's 3.75
#: on real futures, i.e. ~30 % lower); prefer the estimated pooled scalar when history allows.
FIXED_FORECAST_SCALARS: Dict[str, float] = {
    "ewmac2_8": 10.6,
    "ewmac4_16": 7.5,
    "ewmac8_32": 5.3,
    "ewmac16_64": 3.75,
    "ewmac32_128": 2.65,
    "ewmac64_256": 1.87,
    "tsmom_1_3_12": 18.0,
}

#: Rules used by default: the slow EWMAC speeds survive costs (Man AHL) plus multi-horizon TSMOM.
DEFAULT_RULES: Tuple[str, ...] = ("ewmac16_64", "ewmac32_128", "ewmac64_256", "tsmom_1_3_12")

#: Default lookbacks for ``tsmom_1_3_12`` (1, 3 and 12 months in business days).
TSMOM_DEFAULT_LOOKBACKS: Tuple[int, ...] = (21, 63, 252)

_EWMAC_NAME = re.compile(r"^ewmac(\d+)_(\d+)$")


def ewmac(price: pd.Series, vol_price: pd.Series, fast: int, slow: int) -> pd.Series:
    """Raw EWMAC forecast: ``(EWMA_fast(price) - EWMA_slow(price)) / vol_price``.

    ``vol_price`` is the daily volatility in price units (:func:`ibtrader.pipeline.vol.price_vol_daily`).
    Spans are ``fast`` and ``slow``. Division by a zero volatility yields NaN, not inf.
    """
    if fast < 1 or slow < 1:
        raise ValueError("fast and slow spans must be >= 1")
    if fast >= slow:
        raise ValueError("fast span must be smaller than slow span")
    px = price.astype(float)
    fast_ewma = px.ewm(span=fast, min_periods=1, adjust=True).mean()
    slow_ewma = px.ewm(span=slow, min_periods=1, adjust=True).mean()
    raw = (fast_ewma - slow_ewma) / vol_price.astype(float)
    out: pd.Series = raw.replace([np.inf, -np.inf], np.nan)
    out.name = f"ewmac{fast}_{slow}"
    return out


def tsmom_multi(
    price: pd.Series,
    vol_price: pd.Series,
    lookbacks: Tuple[int, ...] = TSMOM_DEFAULT_LOOKBACKS,
) -> pd.Series:
    """Raw multi-horizon time-series momentum.

    For each lookback ``L``: ``(price - price.shift(L)) / (vol_price * sqrt(L))``. The result is the
    simple average over the lookbacks that are available at each date (partial history uses the
    shorter horizons only); NaN where none is available.
    """
    if len(lookbacks) == 0:
        raise ValueError("lookbacks must not be empty")
    if any(lb < 1 for lb in lookbacks):
        raise ValueError("lookbacks must be >= 1")
    px = price.astype(float)
    vol = vol_price.astype(float)
    cols = {}
    for lb in lookbacks:
        comp = (px - px.shift(lb)) / (vol * float(np.sqrt(lb)))
        cols[f"L{lb}"] = comp.replace([np.inf, -np.inf], np.nan)
    frame = pd.DataFrame(cols)
    out: pd.Series = frame.mean(axis=1, skipna=True)
    out.name = "tsmom_" + "_".join(str(lb) for lb in lookbacks)
    return out


def run_rule(name: str, price: pd.Series, vol_price: pd.Series) -> pd.Series:
    """Dispatch a rule by name: ``ewmacF_S`` (any speeds) or ``tsmom_1_3_12``."""
    if name == "tsmom_1_3_12":
        return tsmom_multi(price, vol_price, TSMOM_DEFAULT_LOOKBACKS)
    if name in EWMAC_SPEEDS:
        fast, slow = EWMAC_SPEEDS[name]
        return ewmac(price, vol_price, fast, slow)
    m = _EWMAC_NAME.match(name)
    if m is not None:
        return ewmac(price, vol_price, int(m.group(1)), int(m.group(2)))
    raise ValueError(f"unknown rule name: {name!r}")


def run_rules(
    prices: Mapping[str, pd.Series],
    vols: Mapping[str, pd.Series],
    rules: Sequence[str],
) -> Dict[str, Dict[str, pd.Series]]:
    """Run every rule on every symbol: ``{rule: {symbol: raw_forecast}}``.

    ``vols`` must contain the price-unit daily volatility for every symbol in ``prices``.
    """
    missing = [sym for sym in prices if sym not in vols]
    if missing:
        raise KeyError(f"missing volatility for symbols: {missing}")
    out: Dict[str, Dict[str, pd.Series]] = {}
    for rule in rules:
        per_symbol: Dict[str, pd.Series] = {}
        for sym, px in prices.items():
            per_symbol[sym] = run_rule(rule, px, vols[sym])
        out[rule] = per_symbol
    return out
