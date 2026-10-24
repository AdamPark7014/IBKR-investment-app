"""Núcleo risk parity por cajas (Bridgewater, *The All Weather Story*): cada caja recibe el mismo
presupuesto de riesgo (o el de ``box_budgets``) y, dentro de la caja, cada instrumento aporta el
mismo riesgo (inverse-vol). Fase 2 del playbook, anexo 3.

El "riesgo" aquí es el ingenuo, sin correlaciones: ``Σ w_i · vol_i`` por caja. Es la aproximación
conservadora (miembros de una caja como si estuvieran perfectamente correlacionados) y la que no
necesita estimar una matriz de covarianzas, que es justo lo que DeMiguel et al. desaconsejan sin
regularizar. Las correlaciones entran después vía el IDM (``portfolio.multiplier``) o vía HRP.

Todo es point-in-time: en la fecha t solo se usan retornos hasta t inclusive.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("ibtrader.portfolio.boxes")

TRADING_DAYS = 252


def _valid_vols(vol_annual: pd.Series, boxes: Mapping[str, str]) -> pd.Series:
    """Vols finitas y positivas de símbolos que tienen caja; el resto queda fuera."""
    v = pd.to_numeric(vol_annual, errors="coerce").astype(float)
    values = v.to_numpy(dtype=float)
    has_box = np.array([str(s) in boxes for s in v.index], dtype=bool)
    keep = has_box & np.isfinite(values) & (values > 0)
    dropped = [str(s) for s, k in zip(v.index, keep) if not k]
    if dropped:
        log.debug("box_weights_excluidos symbols=%s", dropped)
    return v[keep]


def _box_budgets(present: List[str], box_budgets: Optional[Mapping[str, float]]) -> Dict[str, float]:
    """Presupuesto por caja presente, renormalizado a 1. Sin ``box_budgets`` → igual por caja."""
    if not present:
        return {}
    if box_budgets is None:
        share = 1.0 / len(present)
        return {b: share for b in present}
    raw = {b: max(0.0, float(box_budgets.get(b, 0.0))) for b in present}
    total = sum(raw.values())
    if total <= 0:
        log.warning("box_budgets sin presupuesto positivo para las cajas presentes %s; uso igual por caja", present)
        share = 1.0 / len(present)
        return {b: share for b in present}
    return {b: x / total for b, x in raw.items()}


def box_inverse_vol_weights(
    vol_annual: pd.Series,
    boxes: Mapping[str, str],
    box_budgets: Optional[Mapping[str, float]] = None,
) -> pd.Series:
    """Pesos de capital con presupuesto de riesgo igual por caja e inverse-vol dentro de la caja.

    ``w_i = (b_k / n_k) / vol_i`` normalizado a suma 1, donde ``k`` es la caja de ``i``, ``b_k`` su
    presupuesto y ``n_k`` cuántos miembros válidos tiene. Así ``Σ_{i∈k} w_i·vol_i ∝ b_k`` (mismo riesgo
    por caja) y dentro de la caja ``w_i ∝ 1/vol_i``.

    Los símbolos con vol NaN, cero o negativa, o sin caja en ``boxes``, quedan fuera del índice del
    resultado. Con ningún símbolo válido devuelve una serie vacía.
    """
    vols = _valid_vols(vol_annual, boxes)
    if vols.empty:
        return pd.Series(dtype=float, name="weight")
    members: Dict[str, List[str]] = {}
    for sym in vols.index:
        members.setdefault(str(boxes[str(sym)]), []).append(str(sym))
    budgets = _box_budgets(sorted(members), box_budgets)
    raw: Dict[str, float] = {}
    for box, syms in members.items():
        per_member = budgets[box] / len(syms)
        for s in syms:
            raw[s] = per_member / float(vols[s])
    w = pd.Series(raw, dtype=float).reindex([str(s) for s in vols.index])
    total = float(w.sum())
    if total > 0:
        w = w / total
    w.name = "weight"
    return w


def rolling_box_weights(
    returns: pd.DataFrame,
    boxes: Mapping[str, str],
    lookback: int = 252,
    min_periods: int = 126,
    step: int = 21,
    box_budgets: Optional[Mapping[str, float]] = None,
) -> pd.DataFrame:
    """Pesos por caja recalculados cada ``step`` barras con vol anualizada rolling (ddof 0, ×√252).

    La rejilla de recálculo se ancla en la primera barra (posiciones 0, step, 2·step, …), así que
    recortar ``returns`` a una fecha t no cambia los pesos hasta t. Entre recálculos los pesos se
    mantienen (forward-fill). Las filas anteriores al primer recálculo con datos son NaN; a partir de
    ahí, un símbolo sin vol válida en esa fecha pesa 0.
    """
    if step < 1:
        raise ValueError("step debe ser >= 1")
    if lookback < 1 or min_periods < 1:
        raise ValueError("lookback y min_periods deben ser >= 1")
    cols = [str(c) for c in returns.columns]
    rets = returns.astype(float)
    rets.columns = pd.Index(cols)
    vol = rets.rolling(lookback, min_periods=min_periods).std(ddof=0) * math.sqrt(TRADING_DAYS)
    rows: Dict[object, pd.Series] = {}
    for i in range(0, len(rets.index), step):
        w = box_inverse_vol_weights(vol.iloc[i], boxes, box_budgets)
        if w.empty:
            continue
        rows[rets.index[i]] = w.reindex(cols).fillna(0.0)
    out = pd.DataFrame(np.nan, index=rets.index, columns=cols, dtype=float)
    if rows:
        grid = pd.DataFrame.from_dict(rows, orient="index")
        out.loc[grid.index, cols] = grid[cols].to_numpy(dtype=float)
        out = out.ffill()
    return out
