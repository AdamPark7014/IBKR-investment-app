"""Full V3 research suite orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from ..config import AppSettings
from .cost_stress import run_cost_ladder_research, summarize_cost_fragility
from .embargo_sensitivity import run_embargo_sensitivity
from .multi_asset import run_multi_asset_sma_research, summarize_cross_section
from .pbo_sma import run_sma_grid_pbo
from .runner import SMA_GRID_CANDIDATES, TREND_REGIME_CANDIDATES, run_sma_research, run_trend_regime_research
from .tsmom_runner import DEFAULT_TSMOM_LOOKBACKS, run_tsmom_research


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
) -> Dict[str, Any]:
    """Run SMA grid + optional regime / cost / TSMOM / embargo / PBO / multi-asset tracks."""
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
        # Cross-section over every symbol present in ``data`` (caller controls load).
        xasset = run_multi_asset_sma_research(
            settings,
            data,
            symbols=list(data.keys()),
            direction=direction,
            n_folds=n_folds,
        )
        xasset_summary = summarize_cross_section(xasset)

    all_rows = list(sma) + list(regime) + list(ladder) + list(tsmom) + list(xasset)
    n_pass = sum(1 for r in all_rows if r.get("gate_passed"))
    return {
        "symbol": symbol,
        "direction": direction,
        "tracks": {
            "sma_grid": sma,
            "sma_regime": regime,
            "cost_ladder": ladder,
            "tsmom": tsmom,
            "multi_asset": xasset,
        },
        "cost_fragility": fragility,
        "embargo_sensitivity": embargo_report,
        "pbo": pbo_report,
        "cross_section": xasset_summary,
        "candidates": all_rows,
        "n_candidates": len(all_rows),
        "n_pass": n_pass,
        "n_fail": len(all_rows) - n_pass,
        "any_gate_passed": n_pass > 0,
    }
