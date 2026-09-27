"""DSR diagnostic over the SMA research grid (selected best vs chance)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from ..config import AppSettings
from .dsr import deflated_sharpe_ratio
from .runner import SMA_GRID_CANDIDATES, run_sma_research


def run_sma_grid_dsr(
    settings: AppSettings,
    data: Mapping[str, Any],
    symbol: str,
    candidates: Sequence[tuple] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    precomputed: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Deflate the best OOS Sharpe among SMA grid trials.

    Uses measured variance of trial Sharpes (Bailey/LdP). If ``precomputed``
    SMA research rows are provided, avoids a second walk-forward pass.
    """
    rows = (
        list(precomputed)
        if precomputed is not None
        else run_sma_research(
            settings,
            data,
            symbol,
            candidates=list(candidates) if candidates is not None else list(SMA_GRID_CANDIDATES),
            direction=direction,
            n_folds=n_folds,
        )
    )
    trial_sharpes: List[float] = []
    best: Optional[Dict[str, Any]] = None
    best_sr = float("-inf")
    for r in rows:
        oos = r.get("oos") or {}
        sh = oos.get("sharpe")
        try:
            sh_f = float(sh) if sh is not None else float("nan")
        except (TypeError, ValueError):
            sh_f = float("nan")
        if sh_f == sh_f:
            trial_sharpes.append(sh_f)
            if sh_f > best_sr:
                best_sr = sh_f
                best = r
    if best is None or not trial_sharpes:
        return {
            "dsr": float("nan"),
            "note": "no finite trial Sharpes for DSR",
            "n_trials": len(rows),
        }

    oos = best.get("oos") or {}
    # Approximate T from trade_count proxy is weak; prefer equity length if present.
    n_obs = int(oos.get("n_obs") or oos.get("trade_count") or 60)
    # If stitched returns skew/kurt unavailable, assume mild non-normality.
    skew = float(oos.get("skew") or 0.0)
    kurt = float(oos.get("kurtosis") or 3.0)
    # Better T: use years*252 from cagr/sharpe path length heuristics if present
    if oos.get("bars") is not None:
        try:
            n_obs = max(int(oos["bars"]), 2)
        except (TypeError, ValueError):
            pass

    dsr = deflated_sharpe_ratio(
        float(best_sr),
        n_obs=n_obs,
        n_trials=len(trial_sharpes),
        trial_sharpes=trial_sharpes,
        skew=skew,
        kurtosis=kurt,
    )
    dsr["selected_candidate_id"] = best.get("candidate_id")
    dsr["selected_params"] = best.get("params")
    dsr["trial_sharpes"] = trial_sharpes
    dsr["symbol"] = symbol
    return dsr


def moments_from_returns(rets: Sequence[float]) -> Dict[str, float]:
    """Skew / Pearson kurtosis / n_obs helper for richer DSR inputs."""
    arr = np.asarray(list(rets), dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return {"n_obs": int(len(arr)), "skew": 0.0, "kurtosis": 3.0}
    # Pearson kurtosis = m4 / m2^2 (Normal → 3)
    m2 = float(np.mean((arr - arr.mean()) ** 2))
    m3 = float(np.mean((arr - arr.mean()) ** 3))
    m4 = float(np.mean((arr - arr.mean()) ** 4))
    skew = m3 / (m2**1.5) if m2 > 0 else 0.0
    kurt = m4 / (m2**2) if m2 > 0 else 3.0
    return {"n_obs": int(len(arr)), "skew": float(skew), "kurtosis": float(kurt)}
