from __future__ import annotations

from typing import Dict
import math

import numpy as np
import pandas as pd


def annualize_vol(daily_vol: float) -> float:
    return float(daily_vol * math.sqrt(252.0))


def volatility_target_weights(
    price_data: Dict[str, pd.DataFrame], target_annual_vol: float = 0.15, lookback: int = 20
) -> Dict[str, float]:
    vols = {}
    for sym, df in price_data.items():
        rets = df["close"].pct_change().dropna()
        if len(rets) < lookback:
            continue
        v = float(rets.rolling(lookback).std(ddof=0).iloc[-1])
        vols[sym] = v
    if not vols:
        return {sym: 0.0 for sym in price_data.keys()}
    inv_vol = {sym: 1.0 / max(v, 1e-6) for sym, v in vols.items()}
    total = sum(inv_vol.values())
    raw_w = {sym: w / total for sym, w in inv_vol.items()}
    # Scale to target vol approximately (ignoring correlations)
    scale = target_annual_vol / annualize_vol(
        np.sqrt(sum((raw_w[sym] * vols[sym]) ** 2 for sym in raw_w))
    )
    return {sym: raw_w.get(sym, 0.0) * scale for sym in price_data.keys()}


def risk_parity_weights(
    cov: pd.DataFrame, max_weight: float = 0.3, tol: float = 1e-6, max_iter: int = 10_000
) -> pd.Series:
    """
    Simple iterative risk parity (equal risk contribution).
    """
    n = cov.shape[0]
    w = np.ones(n) / n
    cov_values = cov.values
    for _ in range(max_iter):
        portfolio_var = float(w @ cov_values @ w)
        mrc = cov_values @ w  # marginal risk contribution
        rc = w * mrc
        target_rc = portfolio_var / n
        grad = rc - target_rc
        w -= 0.01 * grad
        w = np.clip(w, 0.0, max_weight)
        w /= w.sum() or 1.0
        if np.linalg.norm(grad) < tol:
            break
    return pd.Series(w, index=cov.index)


def cap_concentration(weights: Dict[str, float], max_weight: float = 0.3) -> Dict[str, float]:
    w = {k: min(max_weight, max(0.0, float(v))) for k, v in weights.items()}
    s = sum(w.values()) or 1.0
    return {k: v / s for k, v in w.items()}

