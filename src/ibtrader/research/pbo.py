"""Combinatorially Symmetric Cross-Validation (CSCV) PBO — lightweight research estimate.

Based on Bailey, Borwein, López de Prado, Zhu — Probability of Backtest Overfitting.
This is a research diagnostic, not a deployment certificate.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Sequence

import numpy as np


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Average ranks (1..n), higher value → higher rank; NaNs get NaN rank."""
    n = len(values)
    ranks = np.full(n, np.nan, dtype=float)
    valid = np.isfinite(values)
    if not valid.any():
        return ranks
    idx = np.where(valid)[0]
    v = values[idx]
    order = np.argsort(v)
    sorted_v = v[order]
    raw = np.empty(len(v), dtype=float)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and sorted_v[j + 1] == sorted_v[i]:
            j += 1
        avg = 0.5 * ((i + 1) + (j + 1))
        for k in range(i, j + 1):
            raw[order[k]] = avg
        i = j + 1
    ranks[idx] = raw
    return ranks


def probability_of_backtest_overfitting(
    perf_matrix: np.ndarray,
    *,
    n_partitions: int | None = None,
) -> Dict[str, Any]:
    """Estimate PBO from a (n_trials × n_periods) performance matrix."""
    m = np.asarray(perf_matrix, dtype=float)
    if m.ndim != 2:
        raise ValueError("perf_matrix must be 2-D (trials × periods)")
    n_trials, n_periods = m.shape
    if n_trials < 2 or n_periods < 2:
        return {
            "pbo": float("nan"),
            "n_combos": 0,
            "n_trials": int(n_trials),
            "n_periods": int(n_periods),
            "logits": [],
            "note": "insufficient trials/periods for CSCV",
        }
    if n_periods % 2 == 1:
        m = m[:, : n_periods - 1]
        n_periods = m.shape[1]
    half = n_periods // 2
    period_idx = list(range(n_periods))
    combos = list(combinations(period_idx, half))
    max_combos = int(n_partitions) if n_partitions is not None else 2000
    if len(combos) > max_combos:
        rng = np.random.default_rng(42)
        pick = rng.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in sorted(int(x) for x in pick)]

    logits: List[float] = []
    underperform = 0
    for is_cols_t in combos:
        is_cols = list(is_cols_t)
        oos_cols = [c for c in period_idx if c not in is_cols]
        is_mean = np.nanmean(m[:, is_cols], axis=1)
        oos_mean = np.nanmean(m[:, oos_cols], axis=1)
        if not np.isfinite(is_mean).any():
            continue
        best = int(np.nanargmax(is_mean))
        ranks = _average_ranks(oos_mean)
        if not np.isfinite(ranks[best]):
            continue
        omega = float(ranks[best] / (n_trials + 1.0))
        omega = min(max(omega, 1e-6), 1.0 - 1e-6)
        logit = float(np.log(omega / (1.0 - omega)))
        logits.append(logit)
        if logit < 0:
            underperform += 1

    n_combos = len(logits)
    pbo = float(underperform / n_combos) if n_combos else float("nan")
    return {
        "pbo": pbo,
        "n_combos": n_combos,
        "n_trials": int(n_trials),
        "n_periods_used": int(n_periods),
        "mean_logit": float(np.mean(logits)) if logits else float("nan"),
        "high_overfit_risk": bool(pbo == pbo and pbo >= 0.5),
        "note": (
            "PBO≥0.5 suggests the selected configuration often underperforms OOS "
            "relative to peers (research diagnostic only)."
        ),
    }


def pbo_from_fold_sharpe_rows(
    trial_fold_sharpes: Sequence[Sequence[float]],
) -> Dict[str, Any]:
    """Convenience: list of per-trial fold-Sharpe vectors → PBO dict."""
    if not trial_fold_sharpes:
        return probability_of_backtest_overfitting(np.zeros((0, 0)))
    width = max(len(row) for row in trial_fold_sharpes)
    mat = np.full((len(trial_fold_sharpes), width), np.nan, dtype=float)
    for i, row in enumerate(trial_fold_sharpes):
        mat[i, : len(row)] = np.asarray(row, dtype=float)
    keep = ~np.all(np.isnan(mat), axis=0)
    mat = mat[:, keep]
    return probability_of_backtest_overfitting(mat)
