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

    sharpe_ok = sharpe is not None and sharpe >= 0.0
    checks["oos_sharpe"] = sharpe
    checks["oos_sharpe_ok"] = sharpe_ok
    if not sharpe_ok:
        reasons.append(f"oos_sharpe<0 or undefined ({stitched_oos_stats.get('sharpe')})")

    trades_ok = trade_count >= 5
    checks["trade_count"] = trade_count
    checks["trade_count_ok"] = trades_ok
    if not trades_ok:
        reasons.append(f"trade_count={trade_count} < 5")

    dd_ok = True
    if bh_stats is not None and cand_dd is not None:
        bh_dd = _as_float(bh_stats.get("max_dd", bh_stats.get("max_drawdown")))
        if bh_dd is not None:
            # Drawdowns are negative fractions; worse = more negative.
            # Reject if candidate is worse than B&H by more than 5 percentage points.
            dd_ok = not (cand_dd < bh_dd - 0.05)
            checks["candidate_max_dd"] = cand_dd
            checks["bh_max_dd"] = bh_dd
            if not dd_ok:
                reasons.append(
                    f"max_dd {cand_dd:.4f} worse than B&H {bh_dd:.4f} by >5pp"
                )
    checks["dd_ok"] = dd_ok

    frac = float(restricted_bar_frac or 0.0)
    lock_ok = frac <= 0.5
    checks["restricted_bar_frac"] = frac
    checks["lock_ok"] = lock_ok
    if not lock_ok:
        reasons.append(f"restricted_bar_frac={frac:.2%} > 50% (risk lockout dominated)")

    passed = sharpe_ok and trades_ok and dd_ok and lock_ok
    return OOSGateResult(passed=passed, reasons=reasons, checks=checks)
