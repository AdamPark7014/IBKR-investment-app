"""Multiplicador de diversificación (Carver / pysystemtrade): ``DM = 1 / sqrt(w' C w)`` con la
matriz de correlaciones flooreada (``corr_floor``) y diagonal 1, recortado a ``[1, dm_max]``.

Usado como IDM (instrument diversification multiplier) en la etapa de cartera: la misma fórmula
que el FDM de la combinación de forecasts, con ``dm_max`` 2.5 por defecto (anexo 7, "Qué adoptar").
"""

from __future__ import annotations

import logging
import math
from typing import Union

import numpy as np
import pandas as pd

log = logging.getLogger("ibtrader.portfolio.multiplier")

WeightsLike = Union[pd.Series, pd.DataFrame]


def _floored_corr(corr: pd.DataFrame, corr_floor: float) -> np.ndarray:
    """Correlaciones con suelo ``corr_floor`` y diagonal 1.

    Las entradas no finitas (pares sin historia común) se rellenan con la media de las
    correlaciones fuera de la diagonal que sí existen (limpieza de pysystemtrade) o con el suelo si
    no hay ninguna.
    """
    c = corr.to_numpy(dtype=float).copy()
    n = c.shape[0]
    off = ~np.eye(n, dtype=bool)
    finite_off = off & np.isfinite(c)
    fill = float(c[finite_off].mean()) if finite_off.any() else float(corr_floor)
    filled: np.ndarray = np.asarray(np.where(np.isfinite(c), c, fill), dtype=float)
    floored: np.ndarray = np.asarray(np.maximum(filled, corr_floor), dtype=float)
    np.fill_diagonal(floored, 1.0)
    return floored


def diversification_multiplier(
    corr: pd.DataFrame,
    weights: pd.Series,
    corr_floor: float = 0.0,
    dm_max: float = 2.5,
) -> float:
    """``1/sqrt(w'Cw)`` recortado a ``[1, dm_max]``; con varianza no positiva devuelve 1.0."""
    if dm_max < 1.0:
        raise ValueError("dm_max debe ser >= 1")
    if corr.empty:
        return 1.0
    w = pd.to_numeric(weights.reindex(corr.index), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    c = _floored_corr(corr, corr_floor)
    var = float(w @ c @ w)
    if not math.isfinite(var) or var <= 0.0:
        return 1.0
    dm = 1.0 / math.sqrt(var)
    return float(min(max(dm, 1.0), dm_max))


def instrument_div_multiplier(
    subsystem_returns: pd.DataFrame,
    weights: pd.Series,
    corr_floor: float = 0.0,
    dm_max: float = 2.5,
) -> float:
    """IDM con la correlación de los retornos de los subsistemas sobre toda la ventana recibida."""
    corr = subsystem_returns.astype(float).corr()
    return diversification_multiplier(corr, weights, corr_floor=corr_floor, dm_max=dm_max)


def _weights_frame(weights: WeightsLike, index: pd.Index, columns: pd.Index) -> pd.DataFrame:
    if isinstance(weights, pd.DataFrame):
        w = weights.astype(float)
        w.columns = pd.Index([str(c) for c in w.columns])
        w = w.reindex(index.union(w.index)).ffill().reindex(index)
        return w.reindex(columns=columns).fillna(0.0)
    s = pd.to_numeric(weights, errors="coerce")
    s.index = pd.Index([str(c) for c in s.index])
    row = s.reindex(columns).fillna(0.0).to_numpy(dtype=float)
    return pd.DataFrame(np.tile(row, (len(index), 1)), index=index, columns=columns)


def rolling_idm(
    subsystem_returns: pd.DataFrame,
    weights: WeightsLike,
    min_periods: int = 250,
    step: int = 21,
    ewma_span: int = 125,
    corr_floor: float = 0.0,
    dm_max: float = 2.5,
) -> pd.Series:
    """IDM point-in-time: correlación expandiendo recalculada cada ``step`` barras con los pesos de
    esa fecha, mantenida entre recálculos, suavizada con EWMA ``ewma_span`` y 1.0 antes de que haya
    ``min_periods`` barras.
    """
    if step < 1:
        raise ValueError("step debe ser >= 1")
    if min_periods < 2:
        raise ValueError("min_periods debe ser >= 2")
    rets = subsystem_returns.astype(float)
    rets.columns = pd.Index([str(c) for c in rets.columns])
    idx = rets.index
    w_df = _weights_frame(weights, idx, rets.columns)
    raw = pd.Series(np.nan, index=idx, dtype=float)
    for i in range(0, len(idx), step):
        if i + 1 < min_periods:
            continue
        corr = rets.iloc[: i + 1].corr(min_periods=min_periods)
        raw.iloc[i] = diversification_multiplier(corr, w_df.iloc[i], corr_floor=corr_floor, dm_max=dm_max)
    if raw.notna().any():
        smooth = raw.ffill().ewm(span=ewma_span, adjust=True).mean()
    else:
        smooth = raw
    out = smooth.fillna(1.0).clip(lower=1.0, upper=dm_max)
    out.name = "idm"
    return out
