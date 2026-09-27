"""Cross-sectional SMA research across a multi-asset universe (not only SPY)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from ..config import AppSettings
from .runner import run_sma_research

# Default research names when caller does not pass an explicit list.
# Liquid ETFs spanning equity / rates — hypothesis stress, not a portfolio recipe.
DEFAULT_RESEARCH_SYMBOLS: List[str] = ["SPY", "QQQ", "IWM", "EFA", "TLT"]

# One canonical SMA pair per symbol keeps the cross-section readable and cheap.
DEFAULT_MULTI_ASSET_CANDIDATES: List[Tuple[int, int]] = [(10, 30)]


def resolve_research_symbols(
    data: Mapping[str, pd.DataFrame],
    symbols: Sequence[str] | None = None,
) -> List[str]:
    """Intersect requested symbols with available data keys (stable order)."""
    available = list(data.keys())
    if symbols is None:
        # Prefer default research set when present; else every loaded key.
        preferred = [s for s in DEFAULT_RESEARCH_SYMBOLS if s in data]
        return preferred if preferred else available
    return [s for s in symbols if s in data]


def run_multi_asset_sma_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbols: Sequence[str] | None = None,
    candidates: Sequence[Tuple[int, int]] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
) -> List[Dict[str, Any]]:
    """Run the same SMA candidate(s) independently on each symbol.

    Cross-section discipline: a rule that only PASSes on one lucky name is
    fragile. Each row is gated with the same OOS criteria as single-name research.
    """
    syms = resolve_research_symbols(data, symbols)
    grid = list(candidates) if candidates is not None else list(DEFAULT_MULTI_ASSET_CANDIDATES)
    rows: List[Dict[str, Any]] = []
    for sym in syms:
        partial = run_sma_research(
            settings=settings,
            data=data,
            symbol=sym,
            candidates=grid,
            direction=direction,
            n_folds=n_folds,
            candidate_prefix=f"sma_xasset_{sym}",
        )
        for r in partial:
            params = dict(r.get("params") or {})
            params["symbol"] = sym
            params["cross_section"] = True
            r["params"] = params
            r["symbol"] = sym
            rows.append(r)
    return rows


def summarize_cross_section(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate gate outcomes across symbols for one research rule family."""
    symbols = sorted({str(r.get("symbol") or (r.get("params") or {}).get("symbol") or "") for r in rows} - {""})
    n = len(rows)
    n_pass = sum(1 for r in rows if r.get("gate_passed"))
    sharpes: List[float] = []
    for r in rows:
        oos = r.get("oos") or {}
        sh = oos.get("sharpe")
        if sh is not None and sh == sh:  # not NaN
            sharpes.append(float(sh))
    median_sharpe: Optional[float]
    if sharpes:
        ordered = sorted(sharpes)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            median_sharpe = ordered[mid]
        else:
            median_sharpe = 0.5 * (ordered[mid - 1] + ordered[mid])
    else:
        median_sharpe = None
    pass_rate = float(n_pass / n) if n else 0.0
    # Heuristic: rule is cross-sectionally fragile if pass rate is low
    fragile = bool(n >= 2 and pass_rate < 0.5)
    return {
        "symbols": symbols,
        "n_rows": n,
        "n_pass": n_pass,
        "n_fail": n - n_pass,
        "pass_rate": pass_rate,
        "median_oos_sharpe": median_sharpe,
        "fragile_cross_section": fragile,
        "note": (
            "Low cross-sectional pass rate suggests SPY-specific (or name-specific) "
            "fit rather than a portable rule (research diagnostic only)."
        ),
    }
