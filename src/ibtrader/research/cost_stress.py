"""Cost-ladder stress: re-run candidates at 1× / 2× / 3× slippage (SPEC-v3 next slice)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..config import AppSettings
from .runner import SMA_GRID_CANDIDATES, run_sma_research

DEFAULT_SLIPPAGE_MULTS: Tuple[float, ...] = (1.0, 2.0, 3.0)


def _with_slippage_mult(settings: AppSettings, mult: float) -> AppSettings:
    """Return a copied settings with slippage.bps scaled by ``mult``."""
    # pydantic-settings: prefer model_copy when available
    try:
        s = settings.model_copy(deep=True)
    except Exception:
        s = deepcopy(settings)
    base = float(s.slippage.bps)
    s.slippage.bps = float(base * mult)
    return s


def run_cost_ladder_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    candidates: Sequence[Tuple[int, int]] | None = None,
    multipliers: Sequence[float] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
) -> List[Dict[str, Any]]:
    """Evaluate SMA candidates under a slippage cost ladder.

    Survivors that PASS at 1× but FAIL at 2×/3× are fragile to costs — institutional
    desks reject those early. Does not mutate the caller's settings object.
    """
    mults = list(multipliers) if multipliers is not None else list(DEFAULT_SLIPPAGE_MULTS)
    grid = list(candidates) if candidates is not None else list(SMA_GRID_CANDIDATES)
    rows: List[Dict[str, Any]] = []
    base_bps = float(settings.slippage.bps)
    for m in mults:
        stressed = _with_slippage_mult(settings, float(m))
        partial = run_sma_research(
            settings=stressed,
            data=data,
            symbol=symbol,
            candidates=grid,
            direction=direction,
            n_folds=n_folds,
            candidate_prefix=f"sma_cost{m:g}x",
        )
        for r in partial:
            params = dict(r.get("params") or {})
            params["slippage_mult"] = float(m)
            params["slippage_bps"] = float(base_bps * m)
            r["params"] = params
            r["cost_ladder_mult"] = float(m)
            rows.append(r)
    return rows


def summarize_cost_fragility(ladder_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per base SMA pair: which multipliers still PASS gates."""
    by_pair: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for r in ladder_rows:
        p = r.get("params") or {}
        key = (int(p.get("fast", 0)), int(p.get("slow", 0)))
        entry = by_pair.setdefault(
            key,
            {"fast": key[0], "slow": key[1], "pass_at_mults": [], "fail_at_mults": []},
        )
        m = float(r.get("cost_ladder_mult") or p.get("slippage_mult") or 1.0)
        if r.get("gate_passed"):
            entry["pass_at_mults"].append(m)
        else:
            entry["fail_at_mults"].append(m)
    out = []
    for entry in by_pair.values():
        entry["fragile"] = bool(entry["pass_at_mults"]) and any(m > 1.0 for m in entry["fail_at_mults"])
        entry["robust_to_3x"] = 3.0 in entry["pass_at_mults"] or 3 in entry["pass_at_mults"]
        out.append(entry)
    return out
