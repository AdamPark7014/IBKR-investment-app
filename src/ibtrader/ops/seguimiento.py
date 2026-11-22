"""Seguimiento: ¿paper hizo lo que el modelo esperaba?

Compara el retorno diario de la cuenta de paper con el del modelo ideal: los pesos objetivo del día
anterior aplicados al retorno de cada ETF, sin costes ni topes por orden. Mientras la cartera se está
llenando (topes por orden) o si hay días sin ejecutar, paper se queda atrás y aquí se ve cuánto.

No decide nada: es un informe. Con menos de ``MIN_DAYS`` días en común el veredicto es
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


def paper_returns(points: Sequence[Mapping[str, Any]]) -> pd.Series:
    """Retorno diario de paper: el último punto de capital de cada día."""
    if not points:
        return pd.Series(dtype=float)
    eq = pd.Series([float(p["equity"]) for p in points],
                   index=pd.to_datetime([str(p["ts"])[:10] for p in points]))
    eq = eq.groupby(level=0).last().sort_index()
    return eq.pct_change().dropna().astype(float)


def compare(paper: pd.Series, model: pd.Series) -> Dict[str, Any]:
    """Retorno acumulado de cada uno, diferencia, error de seguimiento anual y correlación."""
    frame = pd.DataFrame({"paper": paper, "modelo": model}).dropna()
    n = int(len(frame))
    out: Dict[str, Any] = {"n_dias": n, "minimo_dias": MIN_DAYS}
    if n == 0:
        return {**out, "veredicto": "insuficiente", "nota": "no hay días en común entre paper y el modelo"}
    p, m = frame["paper"].to_numpy(dtype=float), frame["modelo"].to_numpy(dtype=float)
    diff = p - m
    te = float(diff.std(ddof=1)) * math.sqrt(TRADING_DAYS) if n > 1 else float("nan")
    corr = float(np.corrcoef(p, m)[0, 1]) if n > 2 and p.std() > 0 and m.std() > 0 else float("nan")
    out.update({
        "desde": str(frame.index.min().date()), "hasta": str(frame.index.max().date()),
        "retorno_paper": float(np.prod(1.0 + p) - 1.0),
        "retorno_modelo": float(np.prod(1.0 + m) - 1.0),
        "diferencia": float(np.prod(1.0 + p) - np.prod(1.0 + m)),
        "error_seguimiento_anual": te,
        "correlacion": corr,
        "limite_error_seguimiento": TRACKING_ERROR_LIMIT,
    })
    if n < MIN_DAYS:
        out["veredicto"] = "insuficiente"
        out["nota"] = f"{n} días en común: hacen falta {MIN_DAYS} para opinar"
    elif te > TRACKING_ERROR_LIMIT:
        out["veredicto"] = "revisar"
        out["nota"] = "paper no sigue al modelo: mira días sin ejecutar, topes por orden y órdenes sin llenar"
    else:
        out["veredicto"] = "sigue_al_modelo"
    return out


__all__ = ["MIN_DAYS", "TRACKING_ERROR_LIMIT", "compare", "model_returns", "paper_returns"]
