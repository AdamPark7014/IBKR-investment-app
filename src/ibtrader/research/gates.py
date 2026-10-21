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


def evaluate_strict_gates(
    stitched_oos_stats: Mapping[str, Any],
    bh_stats: Optional[Mapping[str, Any]] = None,
    restricted_bar_frac: float = 0.0,
    diagnostics: Optional[Mapping[str, Any]] = None,
    min_oos_sharpe: float = 0.25,
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
