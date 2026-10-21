"""Full V3 research suite orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from ..config import AppSettings
from .cost_stress import run_cost_ladder_research, summarize_cost_fragility
from .cpcv_sma import run_sma_cpcv
from .dsr_sma import run_sma_grid_dsr
from .embargo_sensitivity import run_embargo_sensitivity
from .gates import evaluate_strict_gates
from .loss_mitigation import run_loss_mitigation_research, summarize_loss_mitigation
from .market_analyzer import analyze_market
from .mean_reversion_runner import DEFAULT_MR_CANDIDATES, run_mean_reversion_research
from .multi_asset import run_multi_asset_sma_research, summarize_cross_section
from .pbo_sma import run_sma_grid_pbo
from .report import build_honest_report
from .runner import SMA_GRID_CANDIDATES, TREND_REGIME_CANDIDATES, run_sma_research, run_trend_regime_research
from .tsmom_runner import DEFAULT_TSMOM_LOOKBACKS, run_tsmom_research
from .turnover_diag import diagnose_turnover
from .xsection_runner import DEFAULT_XSECTION_CANDIDATES, run_xsection_research

# Diagnostic blocks (keys of the suite output) that ``evaluate_strict_gates`` understands.
_STRICT_DIAGNOSTIC_KEYS = ("dsr", "pbo", "cpcv")


def _is_sma_family(row: Mapping[str, Any]) -> bool:
    """True for rows produced by ``run_sma_research`` (grid / regime / cost ladder / multi-asset).

    Other tracks tag ``params.family`` (tsmom, mean_reversion, xsection_momentum,
    loss_mitigation); SMA rows carry no family tag and a ``sma`` candidate prefix.
    """
    params = row.get("params") or {}
    family = params.get("family") if isinstance(params, Mapping) else None
    if family not in (None, "sma"):
        return False
    return str(row.get("candidate_id") or "").startswith("sma")


def _apply_strict_gates(
    rows: List[Dict[str, Any]],
    diagnostics: Optional[Mapping[str, Any]],
    symbol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Re-gate every candidate row with ``evaluate_strict_gates`` (in place).

    Runners emit the loose SPEC §3 gate (``gate_passed`` / ``gate_reasons`` /
    ``gate_checks``). This keeps that verdict under ``gate_passed_loose`` /
    ``gate_reasons_loose`` and overwrites ``gate_passed`` / ``gate_reasons`` with
    the strict verdict (Sharpe ≥ 0.25, beat B&H risk-adjusted, DSR/PBO/CPCV).

    ``diagnostics`` (DSR / PBO / CPCV) were computed over the SMA grid of
    ``symbol``, so they are only applied to SMA-family rows of that symbol
    (``symbol=None`` → any SMA row); other families get ``diagnostics=None``.
    A row whose loose checks carry ``restricted_bar_frac_assumed=True`` (the
    engine did not report lockout bars) fails strict with reason
    ``restricted_bar_frac_assumed``: an assumed 0.0 is not evidence.
    """
    diag: Optional[Dict[str, Any]] = None
    if diagnostics:
        diag = {k: diagnostics[k] for k in _STRICT_DIAGNOSTIC_KEYS if diagnostics.get(k) is not None} or None

    for row in rows:
        loose_checks = dict(row.get("gate_checks") or {})
        row["gate_passed_loose"] = bool(row.get("gate_passed"))
        row["gate_reasons_loose"] = list(row.get("gate_reasons") or [])

        oos = row.get("oos") or {}
        bh = row.get("buy_hold_oos")
        try:
            frac = float(loose_checks.get("restricted_bar_frac") or 0.0)
        except (TypeError, ValueError):
            frac = 0.0

        row_symbol = row.get("symbol") or (row.get("params") or {}).get("symbol")
        use_diag = (
            diag is not None
            and _is_sma_family(row)
            and (symbol is None or row_symbol is None or str(row_symbol) == str(symbol))
        )
        strict = evaluate_strict_gates(
            stitched_oos_stats=oos,
            bh_stats=bh if isinstance(bh, Mapping) else None,
            restricted_bar_frac=frac,
            diagnostics=diag if use_diag else None,
        )
        passed = strict.passed
        reasons = list(strict.reasons)
        checks: Dict[str, Any] = {**loose_checks, **strict.checks}
        if loose_checks.get("restricted_bar_frac_assumed"):
            passed = False
            reasons.append("restricted_bar_frac_assumed")
        checks["gate_mode"] = "strict"
        checks["strict_diagnostics_applied"] = bool(use_diag)

        row["gate_passed"] = passed
        row["gate_reasons"] = reasons
        row["gate_checks"] = checks
    return rows


def run_research_suite(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    direction: Optional[str] = None,
    profile: str = "full",
    n_folds: int = 3,
    include_cost_ladder: bool = True,
    include_tsmom: bool = True,
    include_regime: bool = True,
    include_embargo: bool = True,
    include_pbo: bool = True,
    include_multi_asset: bool = True,
    include_mean_reversion: bool = True,
    include_cpcv: bool = True,
    include_dsr: bool = True,
    include_turnover: bool = True,
    include_loss_mitigation: bool = True,
    include_xsection: bool = True,
    include_market_analyzer: bool = True,
) -> Dict[str, Any]:
    """Run full V3 research tracks + institutional diagnostics + analyzer."""
    if profile == "smoke":
        n_folds = 2
        include_cost_ladder = False
        include_tsmom = False
        include_regime = False
        include_embargo = False
        include_pbo = False
        include_multi_asset = False
        include_mean_reversion = False
        include_cpcv = False
        include_dsr = True
        include_turnover = False
        include_loss_mitigation = False
        include_xsection = False
        include_market_analyzer = False

    direction = direction or settings.trading.direction
    sma_candidates = [(10, 30)] if profile == "smoke" else SMA_GRID_CANDIDATES
    sma = run_sma_research(
        settings,
        data,
        symbol,
        candidates=sma_candidates,
        direction=direction,
        n_folds=n_folds,
    )
    regime: List[Dict[str, Any]] = []
    if include_regime:
        regime = run_trend_regime_research(
            settings,
            data,
            symbol,
            candidates=TREND_REGIME_CANDIDATES,
            direction=direction,
            n_folds=n_folds,
        )
    ladder: List[Dict[str, Any]] = []
    fragility: List[Dict[str, Any]] = []
    if include_cost_ladder:
        ladder = run_cost_ladder_research(
            settings,
            data,
            symbol,
            candidates=[(10, 30)],
            direction=direction,
            n_folds=n_folds,
        )
    tsmom: List[Dict[str, Any]] = []
    if include_tsmom:
        tsmom = run_tsmom_research(
            settings,
            data,
            symbol,
            lookbacks=DEFAULT_TSMOM_LOOKBACKS,
            direction=direction,
            n_folds=n_folds,
        )

    mean_rev: List[Dict[str, Any]] = []
    if include_mean_reversion:
        mean_rev = run_mean_reversion_research(
            settings,
            data,
            symbol,
            candidates=DEFAULT_MR_CANDIDATES,
            direction=direction,
            n_folds=n_folds,
        )

    lossmit: List[Dict[str, Any]] = []
    lossmit_summary: Dict[str, Any] | None = None
    if include_loss_mitigation:
        lossmit = run_loss_mitigation_research(
            settings,
            data,
            symbol,
            direction=direction,
            n_folds=n_folds,
        )

    xsection: List[Dict[str, Any]] = []
    if include_xsection and len(data) >= 2:
        xsection = run_xsection_research(
            settings,
            data,
            candidates=DEFAULT_XSECTION_CANDIDATES,
            direction=direction,
            n_folds=n_folds,
        )

    embargo_report: Dict[str, Any] | None = None
    if include_embargo:
        embargo_report = run_embargo_sensitivity(
            settings,
            data,
            symbol,
            fast=10,
            slow=30,
            direction=direction,
        )

    pbo_report: Dict[str, Any] | None = None
    if include_pbo:
        pbo_report = run_sma_grid_pbo(
            settings,
            data,
            symbol,
            candidates=SMA_GRID_CANDIDATES,
            direction=direction,
        )

    xasset: List[Dict[str, Any]] = []
    xasset_summary: Dict[str, Any] | None = None
    if include_multi_asset:
        xasset = run_multi_asset_sma_research(
            settings,
            data,
            symbols=list(data.keys()),
            direction=direction,
            n_folds=n_folds,
        )

    cpcv_report: Dict[str, Any] | None = None
    if include_cpcv:
        cpcv_report = run_sma_cpcv(
            settings,
            data,
            symbol,
            fast=10,
            slow=30,
            direction=direction,
            n_folds=max(6, n_folds * 2),
        )

    analyzer: Dict[str, Any] | None = None
    if include_market_analyzer:
        analyzer = analyze_market(
            data,
            symbols=list(data.keys()),
            benchmark=settings.universe.benchmark
            if settings.universe.benchmark in data
            else symbol,
        )

    all_rows = (
        list(sma)
        + list(regime)
        + list(ladder)
        + list(tsmom)
        + list(mean_rev)
        + list(lossmit)
        + list(xsection)
        + list(xasset)
    )

    dsr_report: Dict[str, Any] | None = None
    if include_dsr:
        dsr_report = run_sma_grid_dsr(
            settings,
            data,
            symbol,
            precomputed=sma,
            direction=direction,
            n_folds=n_folds,
        )

    # Strict gating is the verdict the suite reports; loose stays as *_loose.
    _apply_strict_gates(
        all_rows,
        {"dsr": dsr_report, "pbo": pbo_report, "cpcv": cpcv_report},
        symbol=symbol,
    )
    # Per-track summaries must describe the same (strict) gate as the rows.
    if include_cost_ladder:
        fragility = summarize_cost_fragility(ladder)
    if include_loss_mitigation:
        lossmit_summary = summarize_loss_mitigation(lossmit)
    if include_multi_asset:
        xasset_summary = summarize_cross_section(xasset)

    turnover_report: Dict[str, Any] | None = None
    if include_turnover:
        turnover_report = diagnose_turnover(all_rows)

    n_pass = sum(1 for r in all_rows if r.get("gate_passed"))
    n_pass_loose = sum(1 for r in all_rows if r.get("gate_passed_loose"))
    out: Dict[str, Any] = {
        "symbol": symbol,
        "direction": direction,
        "tracks": {
            "sma_grid": sma,
            "sma_regime": regime,
            "cost_ladder": ladder,
            "tsmom": tsmom,
            "mean_reversion": mean_rev,
            "loss_mitigation": lossmit,
            "xsection": xsection,
            "multi_asset": xasset,
        },
        "cost_fragility": fragility,
        "loss_mitigation_summary": lossmit_summary,
        "embargo_sensitivity": embargo_report,
        "pbo": pbo_report,
        "cross_section": xasset_summary,
        "cpcv": cpcv_report,
        "dsr": dsr_report,
        "turnover": turnover_report,
        "market_analyzer": analyzer,
        "candidates": all_rows,
        "n_candidates": len(all_rows),
        "gate_mode": "strict",
        "n_pass": n_pass,
        "n_fail": len(all_rows) - n_pass,
        "n_pass_loose": n_pass_loose,
        "any_gate_passed": n_pass > 0,
    }
    out["honest_report"] = build_honest_report(out)
    return out
