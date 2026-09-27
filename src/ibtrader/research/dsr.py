"""Deflated Sharpe Ratio (Bailey & López de Prado) — research diagnostic.

DSR corrects observed Sharpe for selection bias under multiple testing and
non-normality. This is a research gate helper, not a deployment certificate.
Pass heuristic commonly cited: DSR ≥ 0.95.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

import numpy as np

EULER_MASCHERONI = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Approximate inverse CDF of standard normal via erfinv (math)."""
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    # erfinv(z) for z in (-1,1); Φ^{-1}(p) = √2 erfinv(2p-1)
    return math.sqrt(2.0) * _erfinv(2.0 * p - 1.0)


def _erfinv(z: float) -> float:
    """Numerical inverse erf (Winitzki approximation + Halley polish)."""
    z = min(max(float(z), -0.999999), 0.999999)
    a = 0.147
    ln = math.log(1.0 - z * z)
    first = 2.0 / (math.pi * a) + ln / 2.0
    second = ln / a
    sign = 1.0 if z >= 0 else -1.0
    x = sign * math.sqrt(math.sqrt(first * first - second) - first)
    # One Halley refinement
    for _ in range(3):
        err = math.erf(x) - z
        dens = (2.0 / math.sqrt(math.pi)) * math.exp(-x * x)
        x = x - err / (dens + x * err)
    return x


def sharpe_std_error(
    observed_sr: float,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Std error of the Sharpe estimator (non-normal correction).

    ``kurtosis`` is the non-excess (Pearson) kurtosis; Normal ⇒ 3.
    """
    t = max(int(n_obs), 2)
    sr = float(observed_sr)
    g3 = float(skew)
    g4 = float(kurtosis)
    var = (1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr * sr) / (t - 1)
    return math.sqrt(max(var, 1e-18))


def expected_max_sharpe(
    n_trials: int,
    sr_variance_across_trials: float,
) -> float:
    """E[max SR] under null of zero true edge given N independent trials."""
    n = max(int(n_trials), 1)
    v = max(float(sr_variance_across_trials), 1e-18)
    # SR0 = √V * [(1-γ) Z^{-1}(1-1/N) + γ Z^{-1}(1-1/(N e))]
    z1 = _norm_ppf(1.0 - 1.0 / n)
    z2 = _norm_ppf(1.0 - 1.0 / (n * math.e))
    return math.sqrt(v) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def deflated_sharpe_ratio(
    observed_sr: float,
    *,
    n_obs: int,
    n_trials: int,
    trial_sharpes: Sequence[float] | None = None,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    sr_variance: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute DSR for a selected strategy among ``n_trials`` attempts.

    Prefer passing ``trial_sharpes`` so V is measured across the search grid.
    """
    obs = float(observed_sr)
    if trial_sharpes is not None and len(trial_sharpes) >= 2:
        arr = np.asarray(list(trial_sharpes), dtype=float)
        arr = arr[np.isfinite(arr)]
        v = float(np.var(arr, ddof=1)) if len(arr) >= 2 else float(sr_variance or 1e-6)
        n_eff = max(int(n_trials), len(arr))
    else:
        v = float(sr_variance) if sr_variance is not None else 1e-6
        n_eff = max(int(n_trials), 1)

    sr0 = expected_max_sharpe(n_eff, v)
    se = sharpe_std_error(obs, n_obs, skew=skew, kurtosis=kurtosis)
    z = (obs - sr0) / se
    dsr = _norm_cdf(z)
    return {
        "dsr": float(dsr),
        "observed_sr": obs,
        "sr0_benchmark": float(sr0),
        "sr_std_error": float(se),
        "n_obs": int(n_obs),
        "n_trials": int(n_eff),
        "sr_variance_trials": float(v),
        "skew": float(skew),
        "kurtosis": float(kurtosis),
        "high_conviction": bool(dsr >= 0.95),
        "note": (
            "DSR≥0.95 is a common research heuristic that the selected Sharpe "
            "beats chance-adjusted selection bias; not a deploy certificate."
        ),
    }
