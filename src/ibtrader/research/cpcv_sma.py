"""Build CPCV-lite diagnostic from SMA walk-forward fold return paths."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

import pandas as pd

from ..config import AppSettings
from ..validation.walkforward import walk_forward_sma
from .cpcv import cpcv_sharpe_distribution


def _fold_oos_returns(fold: Mapping[str, Any]) -> List[float]:
    """Extract daily OOS returns from a walk-forward fold detail dict."""
    eq_pairs = fold.get("oos_equity")
    if not eq_pairs:
        return []
    try:
        s = pd.Series({pd.Timestamp(t): float(v) for t, v in eq_pairs}).sort_index()
    except Exception:
        return []
    if len(s) < 2:
        return []
    return [float(x) for x in s.pct_change().dropna().tolist()]


def run_sma_cpcv(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    fast: int = 10,
    slow: int = 30,
    direction: str | None = None,
    n_folds: int = 6,
) -> Dict[str, Any]:
    """Run WF SMA once, extract per-fold OOS daily returns, then CPCV-lite.

    Uses more folds than the gate suite (default 6) so combinatorial paths
    have room to vary. Single (fast, slow) — no in-sample cherry-pick.
    """
    direction = direction or settings.trading.direction
    if n_folds < 4:
        n_folds = 4
    wf, _summary = walk_forward_sma(
        settings=settings,
        data=dict(data),
        symbol=symbol,
        param_grid=[(int(fast), int(slow))],
        direction=direction,
        n_folds=n_folds,
    )
    fold_rets = [_fold_oos_returns(fold) for fold in (wf.per_fold or [])]
    fold_rets = [r for r in fold_rets if len(r) >= 2]
    report = cpcv_sharpe_distribution(fold_rets)
    report["symbol"] = symbol
    report["params"] = {"fast": int(fast), "slow": int(slow), "direction": direction}
    report["n_folds_requested"] = int(n_folds)
    report["n_folds_with_returns"] = len(fold_rets)
    return report
