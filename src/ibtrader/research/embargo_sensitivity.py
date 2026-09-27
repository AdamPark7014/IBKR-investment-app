"""Embargo-width sensitivity for purged CV signal validation (research only)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

import pandas as pd

from ..config import AppSettings
from ..validation.signal import validate_sma_signal

DEFAULT_EMBARGO_WIDTHS: List[int] = [0, 5, 10, 21]


def run_embargo_sensitivity(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    fast: int = 10,
    slow: int = 30,
    direction: str | None = None,
    n_splits: int = 5,
    embargo_widths: Sequence[int] | None = None,
) -> Dict[str, Any]:
    """Re-run purged SMA signal CV across embargo widths; report fold Sharpe stats.

    Geometry is fixed (n_splits); only embargo changes. Large swings in aggregate
    Sharpe across embargo imply fragile / leakage-sensitive results.
    """
    widths = list(embargo_widths) if embargo_widths is not None else list(DEFAULT_EMBARGO_WIDTHS)
    direction = direction or settings.trading.direction
    rows: List[Dict[str, Any]] = []
    for emb in widths:
        folds, agg = validate_sma_signal(
            data=dict(data),
            symbol=symbol,
            fast=int(fast),
            slow=int(slow),
            direction=direction,
            n_splits=n_splits,
            embargo=int(emb),
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
        )
        fold_sharpes = [float(f.sharpe) for f in folds]
        mean_fs = float(sum(fold_sharpes) / len(fold_sharpes)) if fold_sharpes else float("nan")
        rows.append(
            {
                "embargo": int(emb),
                "fast": int(fast),
                "slow": int(slow),
                "n_folds": len(folds),
                "fold_sharpes": fold_sharpes,
                "mean_fold_sharpe": mean_fs,
                "agg_sharpe": float(agg.sharpe),
                "agg_mean_ret": float(agg.mean_ret),
                "n_obs": int(agg.n_obs),
            }
        )
    # Stability: range of mean fold Sharpe across embargo widths
    means = [r["mean_fold_sharpe"] for r in rows if r["mean_fold_sharpe"] == r["mean_fold_sharpe"]]
    sharpe_range = (max(means) - min(means)) if len(means) >= 2 else 0.0
    unstable = sharpe_range > 0.5  # heuristic: >0.5 Sharpe swing → flag
    return {
        "symbol": symbol,
        "params": {"fast": int(fast), "slow": int(slow), "direction": direction},
        "rows": rows,
        "mean_fold_sharpe_range": float(sharpe_range),
        "unstable_across_embargo": bool(unstable),
    }
