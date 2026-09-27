"""Combinatorial Purged Cross-Validation (CPCV) — lightweight research estimate.

Builds a *distribution* of OOS Sharpes by choosing combinatorial subsets of
fold-level return paths as the reported OOS set. Research diagnostic only;
full López de Prado CPCV with purge on labels can extend this later.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Dict, List, Sequence

import numpy as np


def _sharpe_from_returns(rets: np.ndarray) -> float:
    r = np.asarray(rets, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return float("nan")
    vol = float(np.std(r, ddof=0))
    if vol <= 0:
        return float("nan")
    return float(np.mean(r) / vol * math.sqrt(252.0))


def cpcv_sharpe_distribution(
    fold_returns: Sequence[Sequence[float]],
    *,
    n_test_folds: int | None = None,
    max_combos: int = 500,
) -> Dict[str, Any]:
    """CPCV-lite over a list of per-fold daily return vectors.

    For each combination of ``n_test_folds`` folds, stitch those returns and
    compute an annualized Sharpe. Reports the distribution across paths.
    """
    folds = [np.asarray(f, dtype=float) for f in fold_returns]
    folds = [f[np.isfinite(f)] for f in folds]
    folds = [f for f in folds if len(f) >= 2]
    n = len(folds)
    if n < 2:
        return {
            "n_folds": n,
            "n_combos": 0,
            "sharpes": [],
            "median_sharpe": float("nan"),
            "p05": float("nan"),
            "p95": float("nan"),
            "frac_positive": float("nan"),
            "note": "insufficient folds for CPCV",
        }
    k = int(n_test_folds) if n_test_folds is not None else max(1, n // 2)
    k = min(max(k, 1), n - 1)
    combos = list(combinations(range(n), k))
    if len(combos) > max_combos:
        rng = np.random.default_rng(42)
        pick = rng.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in sorted(int(x) for x in pick)]

    sharpes: List[float] = []
    for cols in combos:
        stitched = np.concatenate([folds[i] for i in cols])
        sh = _sharpe_from_returns(stitched)
        if sh == sh:
            sharpes.append(float(sh))

    arr = np.asarray(sharpes, dtype=float) if sharpes else np.array([], dtype=float)
    frac_pos = float(np.mean(arr > 0)) if len(arr) else float("nan")
    return {
        "n_folds": n,
        "n_test_folds": k,
        "n_combos": len(sharpes),
        "sharpes": sharpes,
        "median_sharpe": float(np.median(arr)) if len(arr) else float("nan"),
        "mean_sharpe": float(np.mean(arr)) if len(arr) else float("nan"),
        "p05": float(np.percentile(arr, 5)) if len(arr) else float("nan"),
        "p95": float(np.percentile(arr, 95)) if len(arr) else float("nan"),
        "frac_positive": frac_pos,
        "fragile_cpcv": bool(frac_pos == frac_pos and frac_pos < 0.5),
        "note": (
            "CPCV-lite: fraction of combinatorial OOS paths with Sharpe>0. "
            "Low frac_positive ⇒ path-dependent / fragile edge (research only)."
        ),
    }
