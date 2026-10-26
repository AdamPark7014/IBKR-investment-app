"""Etapa de cartera (pysystemtrade ``systems/portfolio.py``):

    posición = posición_subsistema · w_instr · IDM

con ``long_only`` para ETFs sin cortos (o ``short_only``: solo cortos) y un tope de exposición bruta
``max_leverage`` que escala
proporcionalmente las posiciones del día que lo supere. Posiciones en acciones fraccionarias;
columnas = símbolos. Pesos e IDM se alinean por fecha con forward-fill (point-in-time).
"""

from __future__ import annotations

from typing import List, Union

import numpy as np
import pandas as pd

WeightsLike = Union[pd.Series, pd.DataFrame]
IdmLike = Union[float, pd.Series]


def _columns(frame: pd.DataFrame) -> List[str]:
    return [str(c) for c in frame.columns]


def _align_weights(weights: WeightsLike, index: pd.Index, columns: List[str]) -> pd.DataFrame:
    """Pesos como DataFrame (fechas × símbolos), forward-filled; símbolo sin peso → 0."""
    if isinstance(weights, pd.DataFrame):
        w = weights.astype(float)
        w.columns = pd.Index(_columns(w))
        w = w.reindex(index.union(w.index)).ffill().reindex(index)
        return w.reindex(columns=columns).fillna(0.0)
    s = pd.to_numeric(weights, errors="coerce")
    s.index = pd.Index([str(c) for c in s.index])
    row = s.reindex(columns).fillna(0.0).to_numpy(dtype=float)
    return pd.DataFrame(np.tile(row, (len(index), 1)), index=index, columns=columns)


def _align_idm(idm: IdmLike, index: pd.Index) -> pd.Series:
    """IDM como serie por fecha, forward-filled; antes del primer valor, 1.0."""
    if isinstance(idm, pd.Series):
        s = pd.to_numeric(idm, errors="coerce").astype(float)
        s = s.reindex(index.union(s.index)).ffill().reindex(index)
        return s.fillna(1.0)
    return pd.Series(float(idm), index=index, dtype=float)


def _align_prices(prices: pd.DataFrame, index: pd.Index, columns: List[str]) -> pd.DataFrame:
    px = prices.astype(float)
    px.columns = pd.Index(_columns(px))
    px = px.reindex(index.union(px.index)).ffill().reindex(index)
    return px.reindex(columns=columns)


def portfolio_positions(
    subsystem_positions: pd.DataFrame,
    instrument_weights: WeightsLike,
    idm: IdmLike,
    prices: pd.DataFrame,
    capital: float,
    long_only: bool = True,
    max_leverage: float = 1.0,
    short_only: bool = False,
) -> pd.DataFrame:
    """``pos = subsystem × w_instr × IDM`` en acciones, con recorte de cortos y tope de apalancamiento.

    La exposición bruta ``Σ|pos·price| / capital`` de cada día se recorta a ``max_leverage`` escalando
    todas las posiciones de ese día por el mismo factor. Un símbolo sin precio ese día no cuenta en la
    exposición. Los NaN de ``subsystem_positions`` se conservan (sin dato ≠ plano).
    """
    if not (capital > 0):
        raise ValueError("capital debe ser > 0")
    if not (max_leverage > 0):
        raise ValueError("max_leverage debe ser > 0")
    if long_only and short_only:
        raise ValueError("long_only y short_only son excluyentes")
    idx = subsystem_positions.index
    cols = _columns(subsystem_positions)
    sub = subsystem_positions.astype(float)
    sub.columns = pd.Index(cols)
    w = _align_weights(instrument_weights, idx, cols)
    m = _align_idm(idm, idx)
    pos = sub.mul(w).mul(m, axis=0)
    if long_only:
        pos = pos.clip(lower=0.0)
    if short_only:
        pos = pos.clip(upper=0.0)
    px = _align_prices(prices, idx, cols)
    notional = (pos.fillna(0.0) * px.fillna(0.0)).abs().sum(axis=1)
    gross = notional / float(capital)
    over = gross > max_leverage
    scale = pd.Series(1.0, index=idx, dtype=float)
    scale[over] = float(max_leverage) / gross[over]
    pos = pos.mul(scale, axis=0)
    pos.attrs["days_capped"] = int(over.sum())
    pos.attrs["max_gross_before_cap"] = float(gross.max()) if len(gross) else 0.0
    pos.attrs["gross_before_cap"] = gross.astype(float)
    pos.attrs["capped"] = over.astype(bool)
    return pos


def positions_to_weights(positions: pd.DataFrame, prices: pd.DataFrame, capital: float) -> pd.DataFrame:
    """Peso de cartera por símbolo: ``pos · price / capital`` (inversa de pasar de peso a acciones)."""
    if not (capital > 0):
        raise ValueError("capital debe ser > 0")
    cols = _columns(positions)
    pos = positions.astype(float)
    pos.columns = pd.Index(cols)
    px = _align_prices(prices, positions.index, cols)
    return pos.mul(px) / float(capital)


def average_abs_positions(
    vol_scalar: pd.DataFrame,
    instrument_weights: WeightsLike,
    idm: IdmLike,
) -> pd.DataFrame:
    """``|vol_scalar · w_instr · IDM|``: posición media a forecast 10, base del buffer ±10 %."""
    idx = vol_scalar.index
    cols = _columns(vol_scalar)
    vs = vol_scalar.astype(float)
    vs.columns = pd.Index(cols)
    w = _align_weights(instrument_weights, idx, cols)
    m = _align_idm(idm, idx)
    return vs.mul(w).mul(m, axis=0).abs()
