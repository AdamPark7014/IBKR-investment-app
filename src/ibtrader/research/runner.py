"""Research experiment runner — SMA grid + trend/regime candidates via walk-forward."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..config import AppSettings
from ..validation.walkforward import walk_forward_sma
from .gates import evaluate_candidate_gates
from .registry import ExperimentRecord

# Explicit research grids only — never mutate AppSettings.strategy defaults.
SMA_GRID_CANDIDATES: List[Tuple[int, int]] = [
    (5, 20),
    (10, 30),
    (20, 50),
]

# Trend + regime: same SMA pairs evaluated under the walk-forward path, which
# already fits GMM on train and passes risk_on into the cost-aware backtest
# (no look-ahead; embargo via expanding train / rolling OOS folds).
TREND_REGIME_CANDIDATES: List[Tuple[int, int]] = [
    (10, 30),
    (20, 50),
]


def run_sma_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    candidates: Sequence[Tuple[int, int]] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    restricted_bar_frac: float = 0.0,
    candidate_prefix: str = "sma",
) -> List[Dict[str, Any]]:
    """Evaluate each (fast, slow) candidate via ``walk_forward_sma``.

    Costs come from ``settings.commission`` / ``settings.slippage``.
    Each candidate is run with a single-combo param grid so WF selection is
    identity for that candidate (no in-sample cherry-pick across the research
    list). Returns a list of dicts with OOS metrics and gate results.
    """
    if candidates is None:
        candidates = list(SMA_GRID_CANDIDATES)

    results: List[Dict[str, Any]] = []
    for fast, slow in candidates:
        wf, summary = walk_forward_sma(
            settings=settings,
            data=dict(data),
            symbol=symbol,
            param_grid=[(int(fast), int(slow))],
            direction=direction or settings.trading.direction,
            n_folds=n_folds,
        )
        oos = dict(wf.stitched_oos or {})
        bh = summary.get("buy_hold_oos")
        gate = evaluate_candidate_gates(
            stitched_oos_stats=oos,
            bh_stats=bh,
            restricted_bar_frac=restricted_bar_frac,
        )
        results.append(
            {
                "candidate_id": f"{candidate_prefix}_{fast}_{slow}",
                "params": {"fast": int(fast), "slow": int(slow), "regime_gated": True},
                "oos": oos,
                "buy_hold_oos": bh,
                "oos_total_trades": summary.get("oos_total_trades"),
                "oos_commission_approx": summary.get("oos_commission_approx"),
                "per_fold_params": summary.get("per_fold_params"),
                "gate_passed": gate.passed,
                "gate_reasons": list(gate.reasons),
                "gate_checks": dict(gate.checks),
            }
        )
    return results


def run_trend_regime_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    candidates: Sequence[Tuple[int, int]] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    restricted_bar_frac: float = 0.0,
) -> List[Dict[str, Any]]:
    """SMA trend candidates under the existing train-fit regime (risk_on) gate."""
    return run_sma_research(
        settings=settings,
        data=data,
        symbol=symbol,
        candidates=list(candidates) if candidates is not None else list(TREND_REGIME_CANDIDATES),
        direction=direction,
        n_folds=n_folds,
        restricted_bar_frac=restricted_bar_frac,
        candidate_prefix="sma_regime",
    )


def build_experiment_records(
    results: List[Dict[str, Any]],
    exp_id: str,
    git_commit: str = "unknown",
    dataset_hash: str = "",
    config_hash: str = "",
    notes: str = "",
) -> List[ExperimentRecord]:
    """Convert runner result dicts into ``ExperimentRecord`` rows."""
    now = datetime.now(timezone.utc).isoformat()
    out: List[ExperimentRecord] = []
    for r in results:
        out.append(
            ExperimentRecord(
                exp_id=exp_id,
                created_at_utc=now,
                git_commit=git_commit,
                candidate_id=str(r["candidate_id"]),
                params=dict(r.get("params") or {}),
                oos=dict(r.get("oos") or {}),
                buy_hold_oos=r.get("buy_hold_oos"),
                gate_passed=bool(r.get("gate_passed")),
                gate_reasons=list(r.get("gate_reasons") or []),
                notes=notes,
                dataset_hash=dataset_hash,
                config_hash=config_hash,
            )
        )
    return out
