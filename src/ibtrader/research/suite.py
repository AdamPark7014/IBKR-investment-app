"""Full V3 research suite orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from ..config import AppSettings
from .cost_stress import run_cost_ladder_research, summarize_cost_fragility
from .cpcv_sma import run_sma_cpcv
from .dsr_sma import run_sma_grid_dsr
from .embargo_sensitivity import run_embargo_sensitivity
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


def run_research_suite(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    direction: Optional[str] = None,
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
    direction = direction or settings.trading.direction
    sma = run_sma_research(
        settings,
        data,
        symbol,
        candidates=SMA_GRID_CANDIDATES,
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
        fragility = summarize_cost_fragility(ladder)
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
        lossmit_summary = summarize_loss_mitigation(lossmit)

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
        xasset_summary = summarize_cross_section(xasset)

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

    turnover_report: Dict[str, Any] | None = None
    if include_turnover:
        turnover_report = diagnose_turnover(all_rows)

    n_pass = sum(1 for r in all_rows if r.get("gate_passed"))
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
        "n_pass": n_pass,
        "n_fail": len(all_rows) - n_pass,
        "any_gate_passed": n_pass > 0,
    }
    out["honest_report"] = build_honest_report(out)
    return out
