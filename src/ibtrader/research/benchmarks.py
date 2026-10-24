"""Benchmarks del playbook (anexos 3 y 7): 60/40 (AOR), All Weather estático en ETFs (RPAR),
carteras aleatorias long-only (Clenow) y un índice externo cargado de CSV (SG Trend, si Adam lo
descarga a mano; aquí no se baja nada de internet).

Las carteras de pesos fijos se rebalancean al cierre del último día de cada periodo (``"M"``,
``"Q"``, cualquier alias de periodo de pandas, o ``"never"`` = buy & hold) pagando ``cost_bps`` por
unidad de turnover (``Σ|w_real − w_objetivo|``, compras y ventas sumadas) sobre el valor de la
cartera. La asignación inicial se hace al cierre de la primera barra común y no paga costo.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

log = logging.getLogger("ibtrader.research.benchmarks")

PERIODS_PER_YEAR = 252

ALL_WEATHER_STATIC: Dict[str, float] = {"SPY": 0.30, "TLT": 0.40, "IEF": 0.15, "GLD": 0.075, "PDBC": 0.075}


def _period_labels(index: pd.Index, rebalance: str) -> np.ndarray:
    """Etiqueta de periodo (entero) por barra; ``never`` → un solo periodo."""
    if str(rebalance).lower() == "never":
        return np.zeros(len(index), dtype=np.int64)
    try:
        periods = pd.DatetimeIndex(index).to_period(rebalance)
    except Exception as e:
        raise ValueError(
            f"rebalance={rebalance!r} no es 'never' ni un alias de periodo de pandas (M, Q, W, Y)"
        ) from e
    codes, _ = pd.factorize(periods)
    return np.asarray(codes, dtype=np.int64)


def _simulate_fixed_weights(gross: np.ndarray, weights: np.ndarray, labels: np.ndarray, cost_rate: float) -> np.ndarray:
    """Retornos diarios (T × P) de P carteras de pesos fijos rebalanceadas al cierre del último día
    de cada periodo.

    ``gross`` es ``1 + r`` (T × N), ``weights`` (P × N) con filas que suman 1 y ``labels`` (T) el
    periodo de cada barra de retorno. Dentro de un periodo el valor por activo crece con el
    acumulado de ``gross``; al cerrar el periodo se mide el turnover contra el objetivo, se paga el
    costo y se vuelve a los pesos objetivo. El último día de la muestra no se rebalancea.
    """
    n_days, _ = gross.shape
    n_port = weights.shape[0]
    out = np.empty((n_days, n_port), dtype=float)
    value = np.ones(n_port, dtype=float)
    start = 0
    while start < n_days:
        end = start + 1
        while end < n_days and labels[end] == labels[start]:
            end += 1
        cum = np.cumprod(gross[start:end], axis=0)
        val = (cum @ weights.T) * value
        prev = np.vstack([value[None, :], val[:-1]])
        out[start:end] = val / prev - 1.0
        if end < n_days:
            last = cum[-1]
            actual = (last[None, :] * weights) / (last @ weights.T)[:, None]
            turnover = np.abs(actual - weights).sum(axis=1)
            new_value = val[-1] * (1.0 - turnover * cost_rate)
            out[end - 1] = new_value / prev[-1] - 1.0
            value = new_value
        start = end
    return out


def _clean_prices(prices: pd.DataFrame, symbols: List[str]) -> pd.DataFrame:
    px = prices[symbols].astype(float).ffill().dropna(how="any")
    if len(px) < 2:
        raise ValueError("hacen falta al menos dos barras con precio para todos los símbolos")
    return px


def rebalanced_portfolio_returns(
    prices: pd.DataFrame,
    weights: Mapping[str, float],
    rebalance: str = "M",
    cost_bps: float = 5.0,
) -> pd.Series:
    """Retornos diarios de una cartera de pesos fijos rebalanceada por periodo con costo por turnover.

    Los símbolos ausentes de ``prices`` se descartan, los presentes se renormalizan a suma 1 y la lista
    descartada queda en ``.attrs["dropped"]`` (``.attrs["weights"]`` guarda los pesos efectivos).
    La ventana empieza en la primera barra con precio para todos los presentes.
    """
    if cost_bps < 0:
        raise ValueError("cost_bps debe ser >= 0")
    cols = {str(c): c for c in prices.columns}
    present = [str(s) for s in weights if str(s) in cols]
    dropped = [str(s) for s in weights if str(s) not in cols]
    if not present:
        raise ValueError(f"ninguno de los símbolos {list(weights)} está en prices")
    w = np.array([float(weights[s]) for s in present], dtype=float)
    if (w < 0).any() or not np.isfinite(w).all():
        raise ValueError("los pesos deben ser finitos y >= 0")
    if w.sum() <= 0:
        raise ValueError("los pesos presentes suman 0")
    w = w / w.sum()
    px = _clean_prices(prices.rename(columns={v: k for k, v in cols.items()}), present)
    rets = px.pct_change(fill_method=None).iloc[1:]
    labels = _period_labels(rets.index, rebalance)
    out = _simulate_fixed_weights((1.0 + rets).to_numpy(dtype=float), w[None, :], labels, cost_bps * 1e-4)[:, 0]
    series = pd.Series(out, index=rets.index, dtype=float, name="portfolio")
    series.attrs["dropped"] = dropped
    series.attrs["weights"] = {s: float(x) for s, x in zip(present, w)}
    series.attrs["rebalance"] = rebalance
    series.attrs["cost_bps"] = float(cost_bps)
    if dropped:
        log.warning("benchmark_symbols_ausentes dropped=%s presentes=%s", dropped, present)
    return series


def sixty_forty(
    prices: pd.DataFrame,
    equity: str = "SPY",
    bonds: str = "IEF",
    rebalance: str = "M",
    cost_bps: float = 5.0,
) -> pd.Series:
    """60/40 (proxy de AOR) rebalanceado."""
    s = rebalanced_portfolio_returns(prices, {equity: 0.60, bonds: 0.40}, rebalance=rebalance, cost_bps=cost_bps)
    s.name = "60_40"
    return s


def all_weather_static(prices: pd.DataFrame, rebalance: str = "M", cost_bps: float = 5.0) -> pd.Series:
    """All Weather estático en ETFs (proxy de RPAR): 30 % SPY, 40 % TLT, 15 % IEF, 7,5 % GLD, 7,5 % PDBC."""
    s = rebalanced_portfolio_returns(prices, ALL_WEATHER_STATIC, rebalance=rebalance, cost_bps=cost_bps)
    s.name = "all_weather_static"
    return s


def random_long_only_portfolios(
    prices: pd.DataFrame,
    n: int = 1000,
    seed: int = 0,
    rebalance: str = "M",
    cost_bps: float = 5.0,
) -> pd.DataFrame:
    """``n`` carteras long-only con pesos Dirichlet(1) fijos en el tiempo (Clenow), una columna cada una.

    Los pesos quedan en ``.attrs["weights"]`` (DataFrame carteras × símbolos) y la semilla en
    ``.attrs["seed"]``. Reproducible por ``seed``.
    """
    if n < 1:
        raise ValueError("n debe ser >= 1")
    if cost_bps < 0:
        raise ValueError("cost_bps debe ser >= 0")
    cols = [str(c) for c in prices.columns]
    if not cols:
        raise ValueError("prices sin columnas")
    rng = np.random.default_rng(seed)
    w = rng.dirichlet(np.ones(len(cols)), size=n)
    px = prices.copy()
    px.columns = pd.Index(cols)
    px = _clean_prices(px, cols)
    rets = px.pct_change(fill_method=None).iloc[1:]
    labels = _period_labels(rets.index, rebalance)
    out = _simulate_fixed_weights((1.0 + rets).to_numpy(dtype=float), w, labels, cost_bps * 1e-4)
    names = [f"rand_{k:04d}" for k in range(n)]
    df = pd.DataFrame(out, index=rets.index, columns=names, dtype=float)
    df.attrs["weights"] = pd.DataFrame(w, index=names, columns=cols)
    df.attrs["seed"] = int(seed)
    df.attrs["rebalance"] = rebalance
    df.attrs["cost_bps"] = float(cost_bps)
    return df


def returns_stats(returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR) -> Dict[str, float]:
    """Sharpe (media/desv ddof 0 × √ppy, rf 0), CAGR, vol, max_dd (fracción negativa), total y n_days."""
    r = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    n = int(len(r))
    nan = float("nan")
    if n == 0:
        return {"sharpe": nan, "cagr": nan, "vol": nan, "max_dd": nan, "total_return": nan, "n_days": 0.0}
    equity = (1.0 + r).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    cagr = (1.0 + total) ** (periods_per_year / n) - 1.0 if (1.0 + total) > 0 else -1.0
    std = float(r.std(ddof=0))
    if std < 1e-15:  # serie constante: el ruido de punto flotante no es dispersión
        std = 0.0
    vol = std * math.sqrt(periods_per_year)
    sharpe = float(r.mean() / std * math.sqrt(periods_per_year)) if (n >= 2 and std > 0) else nan
    max_dd = float((equity / equity.cummax() - 1.0).min())
    return {
        "sharpe": sharpe,
        "cagr": float(cagr),
        "vol": vol,
        "max_dd": max_dd,
        "total_return": total,
        "n_days": float(n),
    }


def sharpe_percentile(value: float, sharpes: Sequence[float]) -> float:
    """Porcentaje (0–100) de Sharpes de la muestra estrictamente menores que ``value``."""
    arr = np.asarray(list(sharpes), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0 or not math.isfinite(float(value)):
        return float("nan")
    return float(100.0 * np.mean(arr < float(value)))


def load_external_index_csv(path: str) -> pd.Series:
    """Serie de retornos diarios desde un CSV ``fecha, valor`` (por ejemplo el SG Trend descargado a mano).

    Toma como fecha la columna llamada date/fecha/time/timestamp (o la primera) y como nivel la
    primera columna numérica restante (prefiriendo value/close/index/nav/level/price). Ordena, quita
    duplicados (gana el último) y devuelve ``pct_change`` con ``.attrs["source"]``.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"índice externo no encontrado: {p}")
    df = pd.read_csv(p)
    if df.shape[1] < 2:
        raise ValueError(f"{p}: hacen falta al menos dos columnas (fecha, valor)")
    names = {str(c).strip().lower(): c for c in df.columns}
    date_col = next((names[k] for k in ("date", "fecha", "time", "timestamp") if k in names), df.columns[0])
    preferred = [names[k] for k in ("value", "close", "index", "nav", "level", "price") if k in names]
    candidates = [c for c in preferred + list(df.columns) if c != date_col]
    value_col = None
    for c in candidates:
        if pd.to_numeric(df[c], errors="coerce").notna().any():
            value_col = c
            break
    if value_col is None:
        raise ValueError(f"{p}: ninguna columna numérica de valor")
    dates = pd.DatetimeIndex(pd.to_datetime(df[date_col], errors="coerce"))
    values = pd.to_numeric(df[value_col], errors="coerce").to_numpy(dtype=float)
    levels = pd.Series(values, index=dates)
    levels = levels[~levels.index.isna()].dropna().sort_index()
    levels = levels[~levels.index.duplicated(keep="last")]
    if len(levels) < 2:
        raise ValueError(f"{p}: menos de dos niveles válidos")
    rets = levels.pct_change(fill_method=None).iloc[1:]
    rets.name = p.stem
    rets.attrs["source"] = str(p)
    rets.attrs["value_column"] = str(value_col)
    rets.attrs["n_levels"] = int(len(levels))
    return rets
