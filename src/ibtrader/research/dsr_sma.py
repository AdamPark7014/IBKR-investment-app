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
    n_trials: Optional[int] = None,
) -> Dict[str, Any]:
    """Deflate the best OOS Sharpe among SMA grid trials.

    Uses measured variance of trial Sharpes (Bailey/LdP). If ``precomputed``
    SMA research rows are provided, avoids a second walk-forward pass.

    ``n_trials`` is the real number of configurations evaluated in the whole
    research run (every family and grid variant, not only this SMA grid). The
    DSR benchmark ``SR0`` grows with ``N``; the suite passes its own count so
    the deflation is not understated. When omitted, ``N`` is the number of
    finite trial Sharpes in ``rows`` (the grid itself); the larger of the two
    is always used.
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
    n_eff = max(int(n_trials) if n_trials is not None else 0, len(trial_sharpes))
    if best is None or not trial_sharpes:
        return {
            "dsr": float("nan"),
            "note": "no finite trial Sharpes for DSR",
            "n_trials": max(n_eff, len(rows)),
            "n_grid_trials": len(rows),
        }

    oos = best.get("oos") or {}
    # T = stitched daily OOS bars (walk-forward ``bars``). Trade count is NOT a sample size:
    # without ``bars`` the DSR is marked insufficient instead of guessing.
    try:
        n_obs = max(int(oos.get("bars") or oos.get("n_obs") or 0), 0)
    except (TypeError, ValueError):
        n_obs = 0
    skew = float(oos.get("skew") or 0.0)
    kurt = float(oos.get("kurtosis") or 3.0)
    if n_obs < 3:
        return {
            "dsr": float("nan"),
            "note": "no daily OOS bar count for DSR (insufficient_obs)",
            "insufficient_obs": True,
            "n_obs": n_obs,
            "n_trials": n_eff,
            "n_grid_trials": len(trial_sharpes),
            "high_conviction": False,
        }

    # Walk-forward Sharpes are annualised: convert with periods_per_year so SR and T match.
    dsr = deflated_sharpe_ratio(
        float(best_sr),
        n_obs=n_obs,
        n_trials=n_eff,
        trial_sharpes=trial_sharpes,
        skew=skew,
        kurtosis=kurt,
        periods_per_year=252.0,
    )
    dsr["n_grid_trials"] = len(trial_sharpes)
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
