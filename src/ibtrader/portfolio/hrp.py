"""Hierarchical Risk Parity (López de Prado, *Building Diversified Portfolios that Outperform
Out-of-Sample*, JPM 2016). Tres pasos: (1) árbol jerárquico sobre la distancia
``sqrt(0.5·(1−ρ))``, (2) cuasi-diagonalización (orden de hojas) y (3) bisección recursiva
repartiendo capital en proporción inversa a la varianza de cada mitad.

Diferencia deliberada con la receta literal: el orden de hojas se canoniza (a cada nivel va a la
izquierda el hijo cuyo símbolo alfabéticamente menor es menor), de modo que los pesos no dependen
del orden en que lleguen las columnas. La receta original hereda ese orden de los ids internos de
scipy y, al bisecar por la mitad una lista, dos permutaciones de las mismas columnas podían dar
pesos distintos. Sigue siendo una cuasi-diagonalización válida: hojas correlacionadas quedan juntas.

Con covarianza degenerada (NaN, varianza cero) no revienta: cae a inverse-variance.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.spatial.distance import pdist

log = logging.getLogger("ibtrader.portfolio.hrp")


def _inverse_variance_weights(cov: pd.DataFrame) -> pd.Series:
    """Pesos ∝ 1/σ² (los activos con varianza no finita o ≤ 0 pesan 0; si no hay ninguno válido, iguales)."""
    var = np.diag(cov.to_numpy(dtype=float)).astype(float)
    ok = np.isfinite(var) & (var > 0)
    w = np.zeros(len(var), dtype=float)
    if not ok.any():
        w[:] = 1.0 / max(len(var), 1)
    else:
        inv = 1.0 / var[ok]
        w[ok] = inv / inv.sum()
    return pd.Series(w, index=cov.index, dtype=float, name="weight")


def _cluster_variance(cov: pd.DataFrame, items: List[str]) -> float:
    sub = cov.loc[items, items]
    w = _inverse_variance_weights(sub).to_numpy(dtype=float)
    return float(w @ sub.to_numpy(dtype=float) @ w)


def _canonical_leaves(node: Any, labels: List[str]) -> List[str]:
    if node.is_leaf():
        return [labels[int(node.id)]]
    left = _canonical_leaves(node.get_left(), labels)
    right = _canonical_leaves(node.get_right(), labels)
    if min(right) < min(left):
        left, right = right, left
    return left + right


def quasi_diagonal_order(corr: pd.DataFrame, linkage_method: str = "single") -> List[str]:
    """Orden de hojas del árbol jerárquico (cuasi-diagonalización), canonizado por nombre."""
    labels = [str(c) for c in corr.columns]
    if len(labels) <= 1:
        return labels
    rho = corr.to_numpy(dtype=float)
    dist = np.sqrt(np.clip(0.5 * (1.0 - rho), 0.0, None))
    np.fill_diagonal(dist, 0.0)
    # LdP pasa la matriz de distancias a linkage, que mide la distancia euclídea entre sus columnas
    # ("distancia de distancias"); aquí se hace explícito para no disparar el aviso de scipy.
    condensed = pdist(dist, metric="euclidean")
    link = linkage(condensed, method=linkage_method)
    return _canonical_leaves(to_tree(link), labels)


def _recursive_bisection(cov: pd.DataFrame, order: List[str]) -> pd.Series:
    w = pd.Series(1.0, index=order, dtype=float)
    clusters: List[List[str]] = [list(order)]
    while clusters:
        nxt: List[List[str]] = []
        for c in clusters:
            if len(c) < 2:
                continue
            half = len(c) // 2
            left, right = c[:half], c[half:]
            v_left = _cluster_variance(cov, left)
            v_right = _cluster_variance(cov, right)
            total = v_left + v_right
            alpha = 1.0 - v_left / total if (math.isfinite(total) and total > 0) else 0.5
            w[left] = w[left] * alpha
            w[right] = w[right] * (1.0 - alpha)
            nxt.append(left)
            nxt.append(right)
        clusters = nxt
    return w


def _fallback(cov: pd.DataFrame, reason: str) -> pd.Series:
    log.warning("hrp_fallback_inverse_variance reason=%s", reason)
    return _inverse_variance_weights(cov)


def hrp_weights(returns: pd.DataFrame, linkage_method: str = "single") -> pd.Series:
    """Pesos HRP (positivos, suman 1) a partir de una ventana de retornos (columnas = símbolos).

    Con una sola columna devuelve 1.0. Con covarianza o correlación no finitas (columna constante,
    NaN) cae a inverse-variance en vez de reventar.
    """
    cols = [str(c) for c in returns.columns]
    if not cols:
        return pd.Series(dtype=float, name="weight")
    if len(cols) == 1:
        return pd.Series([1.0], index=cols, dtype=float, name="weight")
    rets = returns.astype(float)
    rets.columns = pd.Index(cols)
    cov = rets.cov()
    corr = rets.corr()
    if not (np.isfinite(cov.to_numpy(dtype=float)).all() and np.isfinite(corr.to_numpy(dtype=float)).all()):
        return _fallback(cov, "covarianza_o_correlacion_no_finita")
    try:
        order = quasi_diagonal_order(corr, linkage_method)
        w = _recursive_bisection(cov, order).reindex(cols)
    except Exception as e:  # scipy puede rechazar matrices patológicas
        return _fallback(cov, f"{type(e).__name__}: {e}")
    values = w.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or values.sum() <= 0:
        return _fallback(cov, "pesos_no_validos")
    out = w / float(values.sum())
    out.name = "weight"
    return out


def rolling_hrp_weights(
    returns: pd.DataFrame,
    lookback: int = 504,
    min_periods: int = 252,
    step: int = 21,
    linkage_method: str = "single",
) -> pd.DataFrame:
    """HRP recalculado cada ``step`` barras sobre la ventana ``lookback`` (point-in-time).

    Rejilla anclada en la primera barra (0, step, 2·step, …), forward-fill entre recálculos y NaN
    antes del primer recálculo con ``min_periods`` barras. En cada recálculo solo entran los símbolos
    con al menos ``min_periods`` retornos no nulos en la ventana; los demás pesan 0 en esa fecha.
    """
    if step < 1:
        raise ValueError("step debe ser >= 1")
    if lookback < 2 or min_periods < 2:
        raise ValueError("lookback y min_periods deben ser >= 2")
    cols = [str(c) for c in returns.columns]
    rets = returns.astype(float)
    rets.columns = pd.Index(cols)
    rows: Dict[object, pd.Series] = {}
    for i in range(0, len(rets.index), step):
        window = rets.iloc[max(0, i + 1 - lookback) : i + 1]
        counts = window.notna().sum()
        use = [c for c in cols if int(counts[c]) >= min_periods]
        if not use:
            continue
        sub = window[use].dropna(how="any")
        if len(sub) < min_periods:
            continue
        w = hrp_weights(sub, linkage_method=linkage_method)
        rows[rets.index[i]] = w.reindex(cols).fillna(0.0)
    out = pd.DataFrame(np.nan, index=rets.index, columns=cols, dtype=float)
    if rows:
        grid = pd.DataFrame.from_dict(rows, orient="index")
        out.loc[grid.index, cols] = grid[cols].to_numpy(dtype=float)
        out = out.ffill()
    return out
