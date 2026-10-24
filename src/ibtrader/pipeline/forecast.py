"""Forecast scaling and capping (pysystemtrade ``sysquant/estimators/forecast_scalar.py``).

A raw forecast is multiplied by a *forecast scalar* so that its long-run average absolute
value is ``target_abs`` (10 by convention), then capped at ``+/- cap`` (20).

Point-in-time: the pooled scalar at ``t`` is an expanding mean, so it only uses raw forecasts up
to ``t``. The only deliberate exception is the optional backfill of the warm-up period with the
first valid scalar, which is what pysystemtrade does and only affects the first ``min_periods``
observations.
"""

from __future__ import annotations

from typing import Mapping, Union

import numpy as np
import pandas as pd


def _align_point_in_time(values: pd.Series, index: pd.Index) -> pd.Series:
    """Reindex ``values`` to ``index`` carrying the last known value forward (never backward)."""
    s = values.astype(float).sort_index()
    union = s.index.union(index)
    aligned: pd.Series = s.reindex(union).ffill().reindex(index)
    return aligned


def estimate_forecast_scalar(
    raw_by_symbol: Mapping[str, pd.Series],
    target_abs: float = 10.0,
    min_periods: int = 500,
    backfill: bool = True,
) -> pd.Series:
    """Pooled forecast scalar across symbols for one rule.

    ``scalar_t = target_abs / mean_expanding_t(median_cross_section(|raw|))``:

    * per date, the cross-sectional median of ``|raw|`` over the symbols that have a value;
    * expanding mean over time with ``min_periods`` observations;
    * before ``min_periods`` the scalar is NaN; with ``backfill=True`` it is filled backwards with
      the first valid value (all-NaN if the history never reaches ``min_periods``, in which case
      the caller may fall back to :data:`ibtrader.pipeline.rules.FIXED_FORECAST_SCALARS`).

    The index is the union of the symbols' indices.
    """
    if len(raw_by_symbol) == 0:
        raise ValueError("raw_by_symbol must not be empty")
    if target_abs <= 0:
        raise ValueError("target_abs must be > 0")
    if min_periods < 1:
        raise ValueError("min_periods must be >= 1")
    frame = pd.DataFrame({sym: s.astype(float) for sym, s in raw_by_symbol.items()}).sort_index()
    cross_median = frame.abs().median(axis=1, skipna=True)
    expanding_mean = cross_median.expanding(min_periods=min_periods).mean()
    scalar = (float(target_abs) / expanding_mean).replace([np.inf, -np.inf], np.nan)
    if backfill:
        scalar = scalar.bfill()
    out: pd.Series = scalar.astype(float)
    out.name = "forecast_scalar"
    return out


def scale_and_cap(raw: pd.Series, scalar: Union[float, pd.Series], cap: float = 20.0) -> pd.Series:
    """``clip(raw * scalar, -cap, cap)``.

    A Series ``scalar`` is aligned to ``raw.index`` carrying its last known value forward.
    """
    if cap <= 0:
        raise ValueError("cap must be > 0")
    r = raw.astype(float)
    if isinstance(scalar, pd.Series):
        mult = _align_point_in_time(scalar, r.index)
    else:
        mult = float(scalar)
    out: pd.Series = (r * mult).clip(lower=-float(cap), upper=float(cap))
    out.name = raw.name
    return out
