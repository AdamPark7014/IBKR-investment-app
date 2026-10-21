"""V3 OOS gate helpers (SPEC-v3-research-alpha §3)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class OOSGateResult:
    """Outcome of SPEC §3 gates. Passing ≠ deploy permission."""

    passed: bool
    reasons: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def evaluate_candidate_gates(
    stitched_oos_stats: Mapping[str, Any],
    bh_stats: Optional[Mapping[str, Any]] = None,
    restricted_bar_frac: float = 0.0,
    min_oos_sharpe: float = 0.0,
) -> OOSGateResult:
    """Evaluate whether a candidate is "interesting" under SPEC §3.

    All must hold:
    * OOS Sharpe ≥ 0 after costs (stitched walk-forward)
    * OOS max DD not worse than B&H max DD by > 5 absolute pp
    * trade_count ≥ 5 on stitched OOS
    * restricted_bar_frac ≤ 0.5 (reject if lockout dominates the sample)
    """
    reasons: List[str] = []
    checks: Dict[str, Any] = {}

    sharpe = _as_float(stitched_oos_stats.get("sharpe"))
    trade_count = int(stitched_oos_stats.get("trade_count") or 0)
    max_dd = stitched_oos_stats.get("max_dd", stitched_oos_stats.get("max_drawdown"))
    cand_dd = _as_float(max_dd)

    sharpe_ok = sharpe is not None and sharpe >= min_oos_sharpe
    checks["oos_sharpe"] = sharpe
    checks["min_oos_sharpe"] = min_oos_sharpe
    checks["oos_sharpe_ok"] = sharpe_ok
    if not sharpe_ok:
        if min_oos_sharpe > 0.0:
            reasons.append(
                f"oos_sharpe<{min_oos_sharpe} or undefined ({stitched_oos_stats.get('sharpe')})"
            )
        else:
            reasons.append(f"oos_sharpe<0 or undefined ({stitched_oos_stats.get('sharpe')})")

    trades_ok = trade_count >= 5
    checks["trade_count"] = trade_count
    checks["trade_count_ok"] = trades_ok
    if not trades_ok:
        reasons.append(f"trade_count={trade_count} < 5")

    dd_ok = True
    if bh_stats is None:
        dd_ok = False
        reasons.append("bh_missing: cannot compare max_dd vs Buy&Hold")
    elif cand_dd is not None:
        bh_dd = _as_float(bh_stats.get("max_dd", bh_stats.get("max_drawdown")))
        if bh_dd is None:
            dd_ok = False
            reasons.append("bh_max_dd missing or non-numeric")
        else:
            # Drawdowns are negative fractions; worse = more negative.
            # Reject if candidate is worse than B&H by more than 5 percentage points.
            dd_ok = not (cand_dd < bh_dd - 0.05)
            checks["candidate_max_dd"] = cand_dd
            checks["bh_max_dd"] = bh_dd
            if not dd_ok:
                reasons.append(f"max_dd {cand_dd:.4f} worse than B&H {bh_dd:.4f} by >5pp")
    checks["dd_ok"] = dd_ok

    frac = float(restricted_bar_frac or 0.0)
    lock_ok = frac <= 0.5
    checks["restricted_bar_frac"] = frac
    checks["lock_ok"] = lock_ok
    if not lock_ok:
        reasons.append(f"restricted_bar_frac={frac:.2%} > 50% (risk lockout dominated)")

    passed = sharpe_ok and trades_ok and dd_ok and lock_ok
    return OOSGateResult(passed=passed, reasons=reasons, checks=checks)


# Risk-adjusted "beat Buy & Hold" tolerances (strict gates only).
BH_SHARPE_TOLERANCE = 0.10  # candidate may trail B&H Sharpe by at most this much...
BH_DD_MARGIN = 0.05  # ...if its max DD is at least this many pp shallower than B&H.


def compute_trial_budget(
    n_trials: int,
    years_available: float,
    target_sharpe: float = 1.0,
) -> Dict[str, Any]:
    """Trial budget of Bailey, Borwein, López de Prado & Zhu (2014).

    With ``N`` independent trials and a target annual Sharpe ``SR``, the sample
    must span at least ``years_needed = 2·ln(N) / SR²`` years for the best
    backtest not to be a selection artefact (E[max Z_N]² ≤ 2 ln N). One trial
    needs nothing (``years_needed = 0``). ``budget_ok`` is
    ``years_available >= years_needed``; a non-positive ``target_sharpe`` makes
    the budget undefined (``years_needed = inf``, ``budget_ok = False``).
    """
    n = max(int(n_trials), 0)
    years = float(years_available)
    sr = float(target_sharpe)
    if n < 2:
        needed = 0.0
    elif sr <= 0.0 or math.isnan(sr):
        needed = float("inf")
    else:
        needed = 2.0 * math.log(n) / (sr * sr)
    ok = bool(math.isfinite(needed) and years >= needed - 1e-12)
    return {
        "n_trials": n,
        "years_available": years,
        "years_needed": needed,
        "target_sharpe": sr,
        "budget_ok": ok,
    }


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def evaluate_strict_gates(
    stitched_oos_stats: Mapping[str, Any],
    bh_stats: Optional[Mapping[str, Any]] = None,
    restricted_bar_frac: float = 0.0,
    diagnostics: Optional[Mapping[str, Any]] = None,
    min_oos_sharpe: float = 0.25,
    budget: Optional[Mapping[str, Any]] = None,
    holdout: Optional[Mapping[str, Any]] = None,
) -> OOSGateResult:
    """Candidate gates + risk-adjusted beat-B&H + institutional diagnostics.

    On top of ``evaluate_candidate_gates`` (with ``min_oos_sharpe`` = 0.25):

    * The candidate must beat Buy & Hold on a risk-adjusted basis: either
      ``sharpe_cand > sharpe_bh``, or ``sharpe_cand >= sharpe_bh - 0.10`` *and*
      the candidate's max DD is at least 5 pp shallower than B&H's (drawdowns
      are negative fractions). No numeric B&H Sharpe → FAIL (``bh_sharpe_missing``).
      This applies even when ``diagnostics`` is None.
    * When ``diagnostics`` carries ``pbo`` / ``dsr`` / ``cpcv`` blocks, high
      overfit risk, DSR < 0.95 or a fragile CPCV distribution also FAIL.
    * ``budget`` (see ``compute_trial_budget``: ``budget_ok``, ``n_trials``,
      ``years_needed``, ``years_available``; optional
      ``fail_on_budget_exceeded``, default True) → FAIL with reason
      ``trial_budget_exceeded`` when the sample is shorter than the trial
      budget demands and enforcement is on. When enforcement is off the
      verdict is unchanged but ``checks['budget_ok']`` still says False.
    * ``holdout`` (``holdout_applied`` / ``holdout_opened`` /
      ``holdout_overused``) → FAIL with reason ``holdout_overused`` when the
      frozen hold-out was opened more times than ``max_holdout_openings``.
      All flags are copied into ``checks``.
    """
    base = evaluate_candidate_gates(
        stitched_oos_stats,
        bh_stats=bh_stats,
        restricted_bar_frac=restricted_bar_frac,
        min_oos_sharpe=min_oos_sharpe,
    )
    reasons = list(base.reasons)
    checks: Dict[str, Any] = dict(base.checks)
    passed = base.passed

    # --- Beat Buy & Hold, risk adjusted (always enforced) ---------------------
    sharpe_cand = _as_float(stitched_oos_stats.get("sharpe"))
    bh_sharpe = _as_float(bh_stats.get("sharpe")) if bh_stats is not None else None
    cand_dd = _as_float(stitched_oos_stats.get("max_dd", stitched_oos_stats.get("max_drawdown")))
    bh_dd = (
        _as_float(bh_stats.get("max_dd", bh_stats.get("max_drawdown"))) if bh_stats is not None else None
    )
    checks["bh_sharpe"] = bh_sharpe
    checks["bh_sharpe_tolerance"] = BH_SHARPE_TOLERANCE
    checks["bh_dd_margin"] = BH_DD_MARGIN
    beats_bh = False  # strict Sharpe win
    beats_bh_via_dd = False  # near-miss on Sharpe compensated by a shallower DD
    if bh_sharpe is None:
        passed = False
        reasons.append("bh_sharpe_missing")
    elif sharpe_cand is None:
        passed = False
        reasons.append("does_not_beat_bh: oos_sharpe undefined")
    else:
        beats_bh = sharpe_cand > bh_sharpe
        if not beats_bh and sharpe_cand >= bh_sharpe - BH_SHARPE_TOLERANCE:
            if cand_dd is not None and bh_dd is not None:
                beats_bh_via_dd = (cand_dd - bh_dd) >= BH_DD_MARGIN - 1e-12
        if not (beats_bh or beats_bh_via_dd):
            passed = False
            dd_txt = (
                f"dd {cand_dd:.4f} vs B&H {bh_dd:.4f}" if cand_dd is not None and bh_dd is not None else "dd n/a"
            )
            reasons.append(
                f"does_not_beat_bh: sharpe {sharpe_cand:.4f} vs B&H {bh_sharpe:.4f} "
                f"(tol {BH_SHARPE_TOLERANCE}), {dd_txt} (need {BH_DD_MARGIN:.0%} shallower)"
            )
    checks["beats_bh"] = beats_bh
    checks["beats_bh_via_dd"] = beats_bh_via_dd
    checks["beats_bh_ok"] = beats_bh or beats_bh_via_dd

    # --- Trial budget (Bailey et al. 2014): years ≥ 2·ln(N)/SR² ----------------
    if budget is not None:
        n_trials = int(budget.get("n_trials") or 0)
        years_needed = _as_float(budget.get("years_needed"))
        years_available = _as_float(budget.get("years_available"))
        budget_ok = _as_bool(budget.get("budget_ok"), default=False)
        enforce = _as_bool(budget.get("fail_on_budget_exceeded"), default=True)
        checks["n_trials"] = n_trials
        checks["years_needed"] = years_needed
        checks["years_available"] = years_available
        checks["budget_ok"] = budget_ok
        checks["budget_enforced"] = enforce
        if not budget_ok:
            txt = (
                f"trial_budget_exceeded: n_trials={n_trials} needs "
                f"{years_needed if years_needed is not None else float('nan'):.2f}y, "
                f"have {years_available if years_available is not None else float('nan'):.2f}y"
            )
            if enforce:
                passed = False
                reasons.append(txt)
            else:
                checks["budget_warning"] = txt + " (not enforced)"

    # --- Frozen hold-out discipline --------------------------------------------
    if holdout is not None:
        applied = _as_bool(holdout.get("holdout_applied"))
        opened = _as_bool(holdout.get("holdout_opened"))
        overused = _as_bool(holdout.get("holdout_overused"))
        checks["holdout_applied"] = applied
        checks["holdout_opened"] = opened
        checks["holdout_overused"] = overused
        if holdout.get("holdout_start") is not None:
            checks["holdout_start"] = str(holdout.get("holdout_start"))
        if holdout.get("holdout_opening_no") is not None:
            checks["holdout_opening_no"] = int(holdout["holdout_opening_no"])
        if overused:
            passed = False
            reasons.append("holdout_overused")

    if not diagnostics:
        return OOSGateResult(passed=passed, reasons=reasons, checks=checks)

    pbo = diagnostics.get("pbo")
    if isinstance(pbo, Mapping) and pbo.get("high_overfit_risk"):
        passed = False
        checks["pbo_high_overfit_risk"] = True
        reasons.append("pbo.high_overfit_risk")

    dsr_block = diagnostics.get("dsr")
    if isinstance(dsr_block, Mapping) and "dsr" in dsr_block:
        dsr_val = _as_float(dsr_block.get("dsr"))
        checks["dsr"] = dsr_val
        if dsr_val is not None and dsr_val < 0.95:
            passed = False
            checks["dsr_ok"] = False
            reasons.append(f"dsr={dsr_val:.4f} < 0.95")
        elif dsr_val is not None:
            checks["dsr_ok"] = True

    cpcv = diagnostics.get("cpcv")
    if isinstance(cpcv, Mapping) and cpcv.get("fragile_cpcv"):
        passed = False
        checks["fragile_cpcv"] = True
        reasons.append("cpcv.fragile_cpcv")

    return OOSGateResult(passed=passed, reasons=reasons, checks=checks)
