"""¿Cuánto predice cada señal? Coeficiente de información (IC) por regla y horizonte.

El IC es la correlación de rangos (Spearman) entre el pronóstico de hoy y el retorno de los
``h`` días siguientes, normalizado por la volatilidad de hoy. IC = 0 es no saber nada; IC = 1 sería
adivinar siempre. En mercados líquidos una señal buena tiene IC de 0,02 a 0,05.

Diagnóstico, no compuerta: no elige variantes ni cuenta como prueba. Sirve para ver de dónde sale
(y de dónde no sale) el poder predictivo antes de proponer una señal nueva.

Los retornos a ``h`` días se solapan, así que el error estándar se calcula con observaciones
efectivas ``n / h``. Todo es point-in-time: el pronóstico en ``t`` usa precios hasta ``t`` y el
retorno empieza en ``t + 1``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

from ..pipeline.rules import DEFAULT_RULES, run_rule
from ..pipeline.vol import pct_vol_daily, price_vol_daily

HORIZONS = (1, 5, 21, 63)


def _spearman(a: pd.Series, b: pd.Series) -> float:
    frame = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(frame) < 30:
        return float("nan")
    return float(frame["a"].rank().corr(frame["b"].rank()))


def information_coefficients(
    prices: pd.DataFrame,
    rules: Sequence[str] = tuple(DEFAULT_RULES),
    horizons: Sequence[int] = HORIZONS,
    vol_span: int = 35,
    start: Any = None,
) -> Dict[str, Any]:
    """IC agrupado (todos los símbolos) por regla y horizonte, con error estándar y estadístico t."""
    px = prices.astype(float).sort_index()
    fwd: Dict[int, Dict[str, pd.Series]] = {h: {} for h in horizons}
    fc: Dict[str, Dict[str, pd.Series]] = {r: {} for r in rules}
    for sym in px.columns:
        s = px[sym].dropna()
        if len(s) < 300:
            continue
        vol_p = price_vol_daily(s, span=vol_span)
        vol_pct = pct_vol_daily(s, span=vol_span)
        for h in horizons:
            ret = s.shift(-h) / s - 1.0
            fwd[h][sym] = (ret / (vol_pct * math.sqrt(h))).replace([np.inf, -np.inf], np.nan)
        for r in rules:
            fc[r][sym] = run_rule(r, s, vol_p)
    rows: List[Dict[str, Any]] = []
    for r in rules:
        for h in horizons:
            fs, rs = [], []
            for sym in fc[r]:
                f, y = fc[r][sym], fwd[h][sym]
                if start is not None:
                    f, y = f.loc[pd.Timestamp(start):], y.loc[pd.Timestamp(start):]
                fs.append(f)
                rs.append(y)
            if not fs:
                continue
            a, b = pd.concat(fs, ignore_index=True), pd.concat(rs, ignore_index=True)
            n = int(pd.DataFrame({"a": a, "b": b}).dropna().shape[0])
            ic = _spearman(a, b)
            # Solape de h días y correlación entre símbolos: observaciones efectivas ≈ fechas / h.
            n_dates = max(len(f.dropna()) for f in fs)
            n_eff = max(n_dates / h, 1.0)
            se = 1.0 / math.sqrt(n_eff)
            rows.append({"regla": r, "horizonte_dias": int(h), "ic": ic, "n": n, "n_efectivo": n_eff,
                         "error_estandar": se, "t": ic / se if se > 0 else float("nan")})
    return {
        "nota": ("IC = correlación de rangos entre pronóstico y retorno futuro normalizado por volatilidad. "
                 "Diagnóstico: no elige variantes."),
        "filas": rows,
    }


def per_symbol_ic(prices: pd.DataFrame, rule: str, horizon: int = 21, vol_span: int = 35) -> Mapping[str, float]:
    """IC de una regla por símbolo (para ver si el poder predictivo se concentra en pocos mercados)."""
    out: Dict[str, float] = {}
    for sym in prices.columns:
        s = prices[sym].astype(float).dropna()
        if len(s) < 300:
            continue
        f = run_rule(rule, s, price_vol_daily(s, span=vol_span))
        y = (s.shift(-horizon) / s - 1.0) / (pct_vol_daily(s, span=vol_span) * math.sqrt(horizon))
        out[str(sym)] = _spearman(f, y.replace([np.inf, -np.inf], np.nan))
    return out


__all__ = ["HORIZONS", "information_coefficients", "per_symbol_ic"]
