"""Full V3 research suite orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from ..config import AppSettings
from .cost_stress import run_cost_ladder_research, summarize_cost_fragility
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
) -> Dict[str, Any]:
    """Run SMA grid + optional regime / cost-ladder / TSMOM research tracks."""
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
        # Cost ladder on the baseline (10,30) only to keep suite fast in CI/fixtures
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

    all_rows = list(sma) + list(regime) + list(ladder) + list(tsmom)
    n_pass = sum(1 for r in all_rows if r.get("gate_passed"))
    return {
        "symbol": symbol,
        "direction": direction,
        "tracks": {
            "sma_grid": sma,
            "sma_regime": regime,
            "cost_ladder": ladder,
            "tsmom": tsmom,
        },
        "cost_fragility": fragility,
        "candidates": all_rows,
        "n_candidates": len(all_rows),
        "n_pass": n_pass,
        "n_fail": len(all_rows) - n_pass,
        "any_gate_passed": n_pass > 0,
    }
