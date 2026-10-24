"""Research experiment runner — SMA grid + trend/regime candidates via walk-forward."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..config import AppSettings
from ..validation.walkforward import walk_forward_sma
from .gates import OOSGateResult, evaluate_candidate_gates
from .registry import ExperimentRecord

_RESTRICTED_FRAC_KEYS = ("restricted_bar_frac", "risk_restricted_frac")


def _float_from_mapping(container: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        raw = container.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def resolve_restricted_bar_frac(
    oos_stats: Mapping[str, Any],
    *,
    wf_summary: Mapping[str, Any] | None = None,
    override: float | None = None,
) -> tuple[float, bool]:
    """Return ``(frac, sourced)`` for the risk-lockout gate.

    ``sourced`` is True when the fraction came from backtest/WF stats (or a
    non-zero caller override). When False, ``frac`` is 0.0 and gates should treat
    the sample as ``restricted_bar_frac_assumed`` (legacy rows without engine wiring).
    """
    if override is not None and float(override) != 0.0:
        return float(override), True

    for container in (
        oos_stats,
        oos_stats.get("extra") if isinstance(oos_stats.get("extra"), Mapping) else None,
        wf_summary,
        wf_summary.get("extra") if wf_summary and isinstance(wf_summary.get("extra"), Mapping) else None,
    ):
        if not isinstance(container, Mapping):
            continue
        found = _float_from_mapping(container, _RESTRICTED_FRAC_KEYS)
        if found is not None:
            return found, True

    return 0.0, False


def evaluate_gates_with_restricted_frac(
    oos_stats: Mapping[str, Any],
    bh_stats: Mapping[str, Any] | None,
    *,
    wf_summary: Mapping[str, Any] | None = None,
    override: float | None = None,
) -> OOSGateResult:
    """``evaluate_candidate_gates`` with honest ``restricted_bar_frac`` resolution."""
    frac, sourced = resolve_restricted_bar_frac(
        oos_stats, wf_summary=wf_summary, override=override
    )
    gate = evaluate_candidate_gates(
        stitched_oos_stats=oos_stats,
        bh_stats=bh_stats,
        restricted_bar_frac=frac,
    )
    if sourced:
        return gate
    checks = dict(gate.checks)
    checks["restricted_bar_frac_assumed"] = True
    checks["restricted_bar_frac_note"] = (
        "restricted_bar_frac missing from OOS/WF stats — using 0.0 (assumed)"
    )
    return OOSGateResult(passed=gate.passed, reasons=list(gate.reasons), checks=checks)


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

    ``restricted_bar_frac`` for gates is taken from stitched OOS / WF summary
    stats when present; otherwise 0.0 until the backtest engine reports lockout
    bar counts (see ``resolve_restricted_bar_frac``).
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
        gate = evaluate_gates_with_restricted_frac(
            oos,
            bh,
            wf_summary=summary,
            override=restricted_bar_frac if restricted_bar_frac != 0.0 else None,
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


def _opt_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def build_experiment_records(
    results: List[Dict[str, Any]],
    exp_id: str,
    git_commit: str = "unknown",
    dataset_hash: str = "",
    config_hash: str = "",
    notes: str = "",
    suite_summary: Mapping[str, Any] | None = None,
) -> List[ExperimentRecord]:
    """Convert runner result dicts into ``ExperimentRecord`` rows.

    ``dataset_hash`` and ``config_hash`` are mandatory provenance: a registry
    row that cannot be tied to the exact data + settings it was produced with
    is not reproducible, so empty hashes raise ``ValueError``.

    ``suite_summary`` (the dict returned by ``run_research_suite``) supplies the
    research-discipline fields shared by every row of the run: ``n_trials``,
    ``years_available``, ``years_needed``, ``budget_ok``, ``holdout_start``,
    ``holdout_applied``, ``holdout_opened``. Without it they keep their
    defaults (0 / None / False), which is how legacy rows read back. A row
    flagged ``holdout_overused`` keeps that flag under ``extra``.
    """
    if not dataset_hash or not config_hash:
        raise ValueError(
            "build_experiment_records: dataset_hash and config_hash are required "
            f"(got dataset_hash={dataset_hash!r}, config_hash={config_hash!r})"
        )
    summary: Mapping[str, Any] = suite_summary or {}
    n_trials = int(summary.get("n_trials") or 0)
    years_available = float(summary.get("years_available") or 0.0)
    years_needed = float(summary.get("years_needed") or 0.0)
    budget_ok = _opt_bool(summary.get("budget_ok"))
    holdout_start_raw = summary.get("holdout_start")
    holdout_start = str(holdout_start_raw) if holdout_start_raw is not None else None
    holdout_applied = bool(summary.get("holdout_applied"))
    holdout_opened = bool(summary.get("holdout_opened"))

    now = datetime.now(timezone.utc).isoformat()
    out: List[ExperimentRecord] = []
    for r in results:
        extra: Dict[str, Any] = {}
        if r.get("holdout_overused"):
            extra["holdout_overused"] = True
            opening_no = summary.get("holdout_opening_no")
            if opening_no is not None:
                extra["holdout_opening_no"] = int(opening_no)
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
                n_trials=n_trials,
                years_available=years_available,
                years_needed=years_needed,
                budget_ok=budget_ok,
                holdout_start=holdout_start,
                holdout_applied=holdout_applied,
                holdout_opened=holdout_opened,
                extra=extra,
            )
        )
    return out
