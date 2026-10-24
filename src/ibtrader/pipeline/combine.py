"""Combining several scaled forecasts into one (pysystemtrade ``forecast_combine``).

``f_comb = clip(FDM * sum_i w_i f_i, -cap, cap)`` where the forecast diversification multiplier
``FDM = 1 / sqrt(w' C w)`` compensates for the averaging of imperfectly correlated forecasts.

Point-in-time: correlations are expanding (data up to ``t`` only), recomputed every ``step``
bars and carried forward; the EWMA smoothing is causal.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence, Union

import numpy as np
import pandas as pd


def equal_weights(rule_names: Sequence[str]) -> Dict[str, float]:
    """``1 / n`` for every rule name (empty dict for no rules)."""
    names = list(rule_names)
    if not names:
        return {}
    w = 1.0 / float(len(names))
    return {name: w for name in names}


def _select_columns(forecasts: pd.DataFrame, weights: Mapping[str, float]) -> List[str]:
    cols = [str(c) for c in forecasts.columns if c in weights]
    if not cols:
        raise ValueError("no forecast column has a weight")
    return cols


def _normalised_weights(cols: Sequence[str], weights: Mapping[str, float]) -> np.ndarray:
    w = np.array([float(weights[c]) for c in cols], dtype=float)
    if np.any(w < 0):
        raise ValueError("weights must be >= 0")
    total = float(w.sum())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return w / total


def _align_point_in_time(values: pd.Series, index: pd.Index) -> pd.Series:
    s = values.astype(float).sort_index()
    union = s.index.union(index)
    aligned: pd.Series = s.reindex(union).ffill().reindex(index)
    return aligned


def forecast_div_multiplier(
    forecasts: pd.DataFrame,
    weights: Mapping[str, float],
    corr_floor: float = 0.0,
    dm_max: float = 2.5,
    min_periods: int = 250,
    ewma_span: int = 125,
    step: int = 21,
) -> pd.Series:
    """Forecast diversification multiplier, one value per date.

    * columns of ``forecasts`` are rules; only those with a weight are used, weights renormalised;
    * expanding correlation matrix recomputed every ``step`` bars (``min_periods`` pairwise obs.);
      NaN correlations are treated as 1 (conservative), off-diagonals floored at ``corr_floor``;
    * ``FDM = 1 / sqrt(w' C w)`` clipped to ``[1, dm_max]``, carried forward between recalculations,
      EWMA-smoothed (``ewma_span``), clipped again, and the warm-up is filled with 1.0.

    A single rule gives a constant 1.0.
    """
    if dm_max < 1.0:
        raise ValueError("dm_max must be >= 1")
    if min_periods < 2:
        raise ValueError("min_periods must be >= 2")
    if step < 1:
        raise ValueError("step must be >= 1")
    cols = _select_columns(forecasts, weights)
    df = forecasts[cols].astype(float)
    index = df.index
    if len(cols) == 1:
        return pd.Series(1.0, index=index, dtype=float, name="fdm")

    w = _normalised_weights(cols, weights)
    n = len(df)
    raw = np.full(n, np.nan, dtype=float)
    for i in range(min_periods - 1, n, step):
        window = df.iloc[: i + 1]
        corr = window.corr(min_periods=min_periods).to_numpy(dtype=float)
        corr = np.where(np.isnan(corr), 1.0, corr)
        corr = np.maximum(corr, float(corr_floor))
        np.fill_diagonal(corr, 1.0)
        var = float(w @ corr @ w)
        fdm_i = float(dm_max) if var <= 0.0 else 1.0 / float(np.sqrt(var))
        raw[i] = min(max(fdm_i, 1.0), float(dm_max))

    stepped = pd.Series(raw, index=index, dtype=float).ffill()
    smoothed = stepped.ewm(span=ewma_span, adjust=True).mean()
    out: pd.Series = smoothed.clip(lower=1.0, upper=float(dm_max)).fillna(1.0)
    out.name = "fdm"
    return out


def combine_forecasts(
    forecasts: pd.DataFrame,
    weights: Mapping[str, float],
    fdm: Union[float, pd.Series],
    cap: float = 20.0,
) -> pd.Series:
    """``clip(fdm * sum_i w_i f_i, -cap, cap)``.

    Weights are renormalised to 1 over the rules present: columns that have a weight and, per
    date, rules whose forecast is not NaN (a rule still in warm-up does not dilute the others).
    Dates where no rule has a value are NaN. A Series ``fdm`` is aligned carrying forward.
    """
    if cap <= 0:
        raise ValueError("cap must be > 0")
    cols = _select_columns(forecasts, weights)
    w = _normalised_weights(cols, weights)
    df = forecasts[cols].astype(float)
    w_row = pd.Series(w, index=cols, dtype=float)

    present = df.notna()
    w_eff = present.astype(float).mul(w_row, axis=1)
    w_sum = w_eff.sum(axis=1)
    w_norm = w_eff.div(w_sum.where(w_sum > 0.0), axis=0)
    combined = (df.fillna(0.0) * w_norm).sum(axis=1, min_count=1)

    if isinstance(fdm, pd.Series):
        mult = _align_point_in_time(fdm, combined.index)
    else:
        mult = float(fdm)
    out: pd.Series = (combined * mult).clip(lower=-float(cap), upper=float(cap))
    out.name = "combined_forecast"
    return out
