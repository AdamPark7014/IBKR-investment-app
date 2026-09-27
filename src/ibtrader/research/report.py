"""Honest research report aggregator — PASS/FAIL summary across V3 tracks."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


def build_honest_report(suite: Mapping[str, Any]) -> Dict[str, Any]:
    """Collapse suite output into an owner-readable reject/pass digest.

    Emphasizes failures and diagnostics. Never frames gate PASS as deploy.
    """
    candidates: Sequence[Mapping[str, Any]] = list(suite.get("candidates") or [])
    by_track: Dict[str, Dict[str, Any]] = {}
    tracks = suite.get("tracks") or {}
    for name, rows in tracks.items():
        rows = list(rows or [])
        n_pass = sum(1 for r in rows if r.get("gate_passed"))
        by_track[str(name)] = {
            "n": len(rows),
            "n_pass": n_pass,
            "n_fail": len(rows) - n_pass,
            "pass_ids": [r.get("candidate_id") for r in rows if r.get("gate_passed")],
            "fail_ids": [r.get("candidate_id") for r in rows if not r.get("gate_passed")],
        }

    passed = [c for c in candidates if c.get("gate_passed")]
    failed = [c for c in candidates if not c.get("gate_passed")]

    diagnostics: Dict[str, Any] = {
        "cost_fragility": suite.get("cost_fragility"),
        "loss_mitigation_summary": suite.get("loss_mitigation_summary"),
        "embargo_sensitivity": _slim_embargo(suite.get("embargo_sensitivity")),
        "pbo": _slim_pbo(suite.get("pbo")),
        "cross_section": suite.get("cross_section"),
        "cpcv": _slim_cpcv(suite.get("cpcv")),
        "dsr": _slim_dsr(suite.get("dsr")),
        "turnover": suite.get("turnover"),
        "market_analyzer": _slim_analyzer(suite.get("market_analyzer")),
    }

    reject_reasons: List[str] = []
    pbo = suite.get("pbo") or {}
    if pbo.get("high_overfit_risk"):
        reject_reasons.append(f"PBO high ({pbo.get('pbo')})")
    dsr = suite.get("dsr") or {}
    if dsr and not dsr.get("high_conviction") and dsr.get("dsr") == dsr.get("dsr"):
        reject_reasons.append(f"DSR below 0.95 ({dsr.get('dsr')})")
    cpcv = suite.get("cpcv") or {}
    if cpcv.get("fragile_cpcv"):
        reject_reasons.append(f"CPCV frac_positive low ({cpcv.get('frac_positive')})")
    xs = suite.get("cross_section") or {}
    if xs.get("fragile_cross_section"):
        reject_reasons.append(f"cross-section pass_rate low ({xs.get('pass_rate')})")
    emb = suite.get("embargo_sensitivity") or {}
    if emb.get("unstable_across_embargo"):
        reject_reasons.append("embargo-unstable fold Sharpe")

    verdict = "REJECT_LAB_DEFAULT"
    if passed and not reject_reasons:
        verdict = "INTERESTING_OWNER_PC_RERUN"
    elif passed and reject_reasons:
        verdict = "PASS_GATES_BUT_DIAGNOSTICS_SKEPTICAL"
    elif not candidates:
        verdict = "EMPTY_SUITE"

    return {
        "verdict": verdict,
        "symbol": suite.get("symbol"),
        "n_candidates": len(candidates),
        "n_pass": len(passed),
        "n_fail": len(failed),
        "pass_ids": [c.get("candidate_id") for c in passed],
        "by_track": by_track,
        "diagnostics": diagnostics,
        "skeptical_flags": reject_reasons,
        "disclaimer": (
            "Passing OOS gates ≠ deploy. Failing / skeptical diagnostics is the "
            "normal institutional outcome. See SPEC-v3-research-alpha.md."
        ),
    }


def _slim_embargo(rep: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rep:
        return None
    return {
        "mean_fold_sharpe_range": rep.get("mean_fold_sharpe_range"),
        "unstable_across_embargo": rep.get("unstable_across_embargo"),
    }


def _slim_pbo(rep: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rep:
        return None
    return {
        "pbo": rep.get("pbo"),
        "high_overfit_risk": rep.get("high_overfit_risk"),
        "n_trials": rep.get("n_trials"),
        "n_combos": rep.get("n_combos"),
    }


def _slim_cpcv(rep: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rep:
        return None
    return {
        "median_sharpe": rep.get("median_sharpe"),
        "frac_positive": rep.get("frac_positive"),
        "fragile_cpcv": rep.get("fragile_cpcv"),
        "n_combos": rep.get("n_combos"),
        "p05": rep.get("p05"),
        "p95": rep.get("p95"),
    }


def _slim_dsr(rep: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rep:
        return None
    return {
        "dsr": rep.get("dsr"),
        "observed_sr": rep.get("observed_sr"),
        "sr0_benchmark": rep.get("sr0_benchmark"),
        "high_conviction": rep.get("high_conviction"),
        "n_trials": rep.get("n_trials"),
    }


def _slim_analyzer(rep: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rep:
        return None
    return {
        "regime": rep.get("regime"),
        "action_counts": rep.get("action_counts"),
        "top_research": rep.get("top_research"),
        "avoid": rep.get("avoid"),
    }
