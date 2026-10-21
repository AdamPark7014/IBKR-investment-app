"""Honest research report aggregator — PASS/FAIL summary across V3 tracks."""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..config import AppSettings, CommissionConfig, RegFeesConfig, SlippageConfig
from ..execution.costs import model_all_in_bps

# Reference order used to price the configured cost model when the suite rows carry no
# observed per-order cost (engine default: 100 % of USD 100k equity in one order).
DEFAULT_TYPICAL_ORDER_USD = 100_000.0
DEFAULT_REFERENCE_PRICE = 100.0


def _finite_float(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _resolve_cost_configs(
    suite: Mapping[str, Any],
    commission_cfg: Optional[CommissionConfig],
    slippage_cfg: Optional[SlippageConfig],
    reg_fees_cfg: Optional[RegFeesConfig],
) -> Tuple[CommissionConfig, SlippageConfig, RegFeesConfig, str]:
    """Explicit kwargs > ``suite["settings"]`` (AppSettings or mapping) > environment defaults."""
    source = "explicit"
    settings_obj = suite.get("settings")
    if commission_cfg is None or slippage_cfg is None or reg_fees_cfg is None:
        if settings_obj is not None:
            source = "suite.settings"
            if isinstance(settings_obj, Mapping):
                try:
                    commission_cfg = commission_cfg or CommissionConfig(**dict(settings_obj.get("commission") or {}))
                    slippage_cfg = slippage_cfg or SlippageConfig(**dict(settings_obj.get("slippage") or {}))
                    reg_fees_cfg = reg_fees_cfg or RegFeesConfig(**dict(settings_obj.get("reg_fees") or {}))
                except Exception:
                    pass
            else:
                commission_cfg = commission_cfg or getattr(settings_obj, "commission", None)
                slippage_cfg = slippage_cfg or getattr(settings_obj, "slippage", None)
                reg_fees_cfg = reg_fees_cfg or getattr(settings_obj, "reg_fees", None)
    if commission_cfg is None or slippage_cfg is None or reg_fees_cfg is None:
        source = "environment"
        try:
            env = AppSettings()
            commission_cfg = commission_cfg or env.commission
            slippage_cfg = slippage_cfg or env.slippage
            reg_fees_cfg = reg_fees_cfg or env.reg_fees
        except Exception:
            source = "defaults"
            commission_cfg = commission_cfg or CommissionConfig()
            slippage_cfg = slippage_cfg or SlippageConfig()
            reg_fees_cfg = reg_fees_cfg or RegFeesConfig()
    return commission_cfg, slippage_cfg, reg_fees_cfg, source


def cost_model_diagnostics(
    suite: Mapping[str, Any],
    *,
    commission_cfg: Optional[CommissionConfig] = None,
    slippage_cfg: Optional[SlippageConfig] = None,
    reg_fees_cfg: Optional[RegFeesConfig] = None,
) -> Dict[str, Any]:
    """Diagnostic only (never touches ``gate_passed``): is the cost model too cheap to believe?

    Suspicious when the slippage model is the legacy flat ``bps`` one, or when the
    all-in cost per order (observed in the rows, else the configured model priced at a
    reference order) is below ``commission.sanity_min_all_in_bps`` — IBKR Pro clients
    actually paid 2.5-4 bp all-in in jul-2026 (annex 4).
    """
    commission, slippage, reg, cfg_source = _resolve_cost_configs(
        suite, commission_cfg, slippage_cfg, reg_fees_cfg
    )
    candidates: Sequence[Mapping[str, Any]] = list(suite.get("candidates") or [])
    observed_bps: List[float] = []
    turnovers: List[float] = []
    drags: List[float] = []
    for c in candidates:
        oos = c.get("oos") or {}
        bps = _finite_float(oos.get("avg_cost_bps_per_order"))
        if bps is None:
            tc = _finite_float(oos.get("total_costs"))
            nt = _finite_float(oos.get("notional_traded"))
            if tc is not None and nt is not None and nt > 0.0:
                bps = tc / nt * 1e4
        if bps is not None:
            observed_bps.append(bps)
        t = _finite_float(oos.get("turnover"))
        if t is not None:
            turnovers.append(t)
        d = _finite_float(oos.get("cost_drag_annual_pct"))
        if d is not None:
            drags.append(d)

    sanity = float(commission.sanity_min_all_in_bps)
    legacy = slippage.model == "bps"
    symbol = str(suite.get("symbol") or "SPY")
    typical_order_usd = _finite_float(suite.get("typical_order_usd")) or DEFAULT_TYPICAL_ORDER_USD
    reference_price = _finite_float(suite.get("reference_price")) or DEFAULT_REFERENCE_PRICE
    model_estimate_bps = model_all_in_bps(
        symbol,
        typical_order_usd,
        reference_price,
        commission_cfg=commission,
        slippage_cfg=slippage,
        reg_fees_cfg=reg,
    )
    if observed_bps:
        avg_bps: Optional[float] = min(observed_bps)
        bps_source = "observed"
    else:
        avg_bps = model_estimate_bps
        bps_source = "model_estimate"

    reasons: List[str] = []
    if legacy:
        reasons.append(
            f"slippage.model='bps' (flat {float(slippage.bps):g} bp legacy; no spread, no impact, no reg fees split)"
        )
    if avg_bps is not None and avg_bps < sanity:
        reasons.append(
            f"all-in cost per order {avg_bps:.2f} bp ({bps_source}) < sanity floor {sanity:.2f} bp "
            "(IBKR Pro clients paid 2.5-4 bp all-in, jul-2026)"
        )
    suspicious = bool(reasons)
    if suspicious:
        note = (
            "Cost model looks too cheap: " + "; ".join(reasons) + ". Backtest returns are "
            "optimistic until costs are at least as high as what IBKR actually charges. "
            "See COST_MODEL.md."
        )
    else:
        note = (
            f"Cost model all-in {avg_bps:.2f} bp per order ({bps_source}) >= sanity floor "
            f"{sanity:.2f} bp; slippage.model='{slippage.model}', commission.model='{commission.model}'."
        )
    return {
        "suspicious": suspicious,
        "note": note,
        "reasons": reasons,
        "summary": {
            "slippage_model": slippage.model,
            "commission_model": commission.model,
            "config_source": cfg_source,
            "sanity_min_all_in_bps": sanity,
            "avg_cost_bps_per_order": avg_bps,
            "avg_cost_bps_source": bps_source,
            "observed_bps_min": min(observed_bps) if observed_bps else None,
            "observed_bps_median": float(median(observed_bps)) if observed_bps else None,
            "model_estimate_bps": model_estimate_bps,
            "typical_order_usd": float(typical_order_usd),
            "reference_price": float(reference_price),
            "turnover": max(turnovers) if turnovers else None,
            "turnover_median": float(median(turnovers)) if turnovers else None,
            "cost_drag_annual_pct": max(drags) if drags else None,
            "n_candidates_with_cost_data": len(observed_bps),
        },
    }


def build_honest_report(
    suite: Mapping[str, Any],
    *,
    commission_cfg: Optional[CommissionConfig] = None,
    slippage_cfg: Optional[SlippageConfig] = None,
    reg_fees_cfg: Optional[RegFeesConfig] = None,
) -> Dict[str, Any]:
    """Collapse suite output into an owner-readable reject/pass digest.

    Emphasizes failures and diagnostics. Never frames gate PASS as deploy. The cost
    model check (``cost_model_suspicious``) is diagnostic only and does not alter
    ``gate_passed`` or the verdict.
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

    cost_diag = cost_model_diagnostics(
        suite,
        commission_cfg=commission_cfg,
        slippage_cfg=slippage_cfg,
        reg_fees_cfg=reg_fees_cfg,
    )

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
        # Cost-model sanity (diagnostic only; does not change gate_passed / verdict)
        "cost_model_suspicious": cost_diag["suspicious"],
        "cost_model_note": cost_diag["note"],
        "cost_summary": cost_diag["summary"],
        "turnover": cost_diag["summary"]["turnover"],
        "cost_drag_annual_pct": cost_diag["summary"]["cost_drag_annual_pct"],
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
