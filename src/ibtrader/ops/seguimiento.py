"""Seguimiento: ¿paper hizo lo que el modelo esperaba?

Compara el retorno de la cuenta de paper con el del modelo ideal: los pesos objetivo del día
anterior aplicados al retorno de cada ETF, sin costes ni topes por orden. Mientras la cartera se está
llenando (topes por orden) o si hay días sin ejecutar, paper se queda atrás y aquí se ve cuánto.

No decide nada: es un informe. Con menos de ``MIN_DAYS`` intervalos en común el veredicto es
``insuficiente``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from ..config import AppSettings
from ..data.universe import UniverseSpec

TRADING_DAYS = 252
MIN_DAYS = 20
#: Error de seguimiento anual por encima del cual hay que revisar por qué paper no sigue al modelo.
TRACKING_ERROR_LIMIT = 0.03


def model_returns(settings: AppSettings, data: Mapping[str, pd.DataFrame],
                  spec: Optional[UniverseSpec] = None) -> pd.Series:
    """Retorno diario del modelo ideal (solo estrategia ``pipeline``): ``Σ peso_{t-1} · retorno_t``."""
    from ..engine.targets import _system_config
    from ..pipeline.system import run_system

    if str(settings.strategy.name).lower() != "pipeline":
        raise ValueError("el seguimiento solo está definido para STRATEGY__NAME=pipeline")
    closes = pd.DataFrame({s: pd.Series(df["close"], dtype=float) for s, df in data.items()}).sort_index()
    closes.index = pd.DatetimeIndex(closes.index)
    out = run_system(closes, _system_config(settings, sorted(data), spec))
    if out.warmup_end is None:
        return pd.Series(dtype=float)
    w = out.target_weights.reindex(columns=closes.columns).fillna(0.0)
    rets = closes.ffill().pct_change().fillna(0.0)
    model = (w.shift(1).fillna(0.0) * rets).sum(axis=1)
    return model.loc[out.warmup_end:].iloc[1:].astype(float)


def paper_equity(points: Sequence[Mapping[str, Any]]) -> pd.Series:
    """Capital de paper por día: el último punto de cada fecha."""
    if not points:
        return pd.Series(dtype=float)
    eq = pd.Series([float(p["equity"]) for p in points],
                   index=pd.to_datetime([str(p["ts"])[:10] for p in points]))
    return eq.groupby(level=0).last().sort_index().astype(float)


def compare(equity: pd.Series, model: pd.Series) -> Dict[str, Any]:
    """Paper contra el modelo, **intervalo por intervalo** entre puntos de capital consecutivos.

    Paper tiene huecos (días sin corrida): el salto entre dos puntos se compara con el retorno
    compuesto del modelo en esas mismas fechas, no con un solo día. El error de seguimiento se anualiza
    con la duración media de los intervalos.
    """
    out: Dict[str, Any] = {"n_intervalos": 0, "minimo_intervalos": MIN_DAYS}
    eq = equity.dropna().sort_index()
    m = model.dropna().sort_index()
    rows = []
    for d0, d1 in zip(eq.index[:-1], eq.index[1:]):
        seg = m.loc[(m.index > d0) & (m.index <= d1)]
        if len(seg) == 0:
            continue
        rows.append((d1, float(eq.loc[d1] / eq.loc[d0] - 1.0), float(np.prod(1.0 + seg.to_numpy(dtype=float)) - 1.0),
                     len(seg)))
    n = len(rows)
    out["n_intervalos"] = n
    if n == 0:
        return {**out, "veredicto": "insuficiente", "nota": "no hay intervalos en común entre paper y el modelo"}
    p = np.array([r[1] for r in rows])
    mm = np.array([r[2] for r in rows])
    days = float(np.mean([r[3] for r in rows]))
    diff = p - mm
    te = float(diff.std(ddof=1)) * math.sqrt(TRADING_DAYS / days) if n > 1 else float("nan")
    corr = float(np.corrcoef(p, mm)[0, 1]) if n > 2 and p.std() > 0 and mm.std() > 0 else float("nan")
    out.update({
        "desde": str(eq.index[0].date()), "hasta": str(rows[-1][0].date()),
        "dias_por_intervalo": days,
        "retorno_paper": float(np.prod(1.0 + p) - 1.0),
        "retorno_modelo": float(np.prod(1.0 + mm) - 1.0),
        "diferencia": float(np.prod(1.0 + p) - np.prod(1.0 + mm)),
        "error_seguimiento_anual": te,
        "correlacion": corr,
        "limite_error_seguimiento": TRACKING_ERROR_LIMIT,
    })
    if n < MIN_DAYS:
        out["veredicto"] = "insuficiente"
        out["nota"] = f"{n} intervalos en común: hacen falta {MIN_DAYS} para opinar"
    elif te > TRACKING_ERROR_LIMIT:
        out["veredicto"] = "revisar"
        out["nota"] = "paper no sigue al modelo: mira días sin ejecutar, topes por orden y órdenes sin llenar"
    else:
        out["veredicto"] = "sigue_al_modelo"
    return out


__all__ = ["MIN_DAYS", "TRACKING_ERROR_LIMIT", "compare", "model_returns", "paper_equity"]
