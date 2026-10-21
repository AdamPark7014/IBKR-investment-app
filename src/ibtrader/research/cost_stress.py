"""Cost-ladder stress: re-run candidates at 1× / 2× / 3× execution costs (SPEC-v3 next slice).

The multiplier scales the whole cost model from COST_MODEL.md — spread, impact and
commission — not only the legacy flat ``slippage.bps``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..config import AppSettings
from .runner import SMA_GRID_CANDIDATES, run_sma_research

DEFAULT_SLIPPAGE_MULTS: Tuple[float, ...] = (1.0, 2.0, 3.0)

# Fields scaled by the ladder multiplier. Caps (max_percent_of_value), pass-through
# percentages and regulatory fees are statutory and stay fixed.
_SLIPPAGE_SCALED_FIELDS = ("bps", "spread_bps_default", "impact_y")
_COMMISSION_SCALED_FIELDS = (
    "per_share",
    "min_per_order",
    "tiered_per_share",
    "tiered_min_per_order",
    "tiered_exchange_per_share",
    "clearing_per_share",
)


def _with_slippage_mult(settings: AppSettings, mult: float) -> AppSettings:
    """Return a copied settings with every execution-cost parameter scaled by ``mult``.

    Scales ``slippage.bps`` (legacy), ``spread_bps_default``, every entry of
    ``spread_bps_by_symbol``, ``impact_y`` and the commission per-share / minimum
    terms. The caller's settings object is never mutated.
    """
    # pydantic-settings: prefer model_copy when available
    try:
        s = settings.model_copy(deep=True)
    except Exception:
        s = deepcopy(settings)
    m = float(mult)
    sl = s.slippage
    for name in _SLIPPAGE_SCALED_FIELDS:
        setattr(sl, name, float(getattr(sl, name)) * m)
    sl.spread_bps_by_symbol = {
        str(k): float(v) * m for k, v in dict(sl.spread_bps_by_symbol or {}).items()
    }
    cm = s.commission
    for name in _COMMISSION_SCALED_FIELDS:
        setattr(cm, name, float(getattr(cm, name)) * m)
    return s


_with_cost_mult = _with_slippage_mult  # explicit alias: the ladder scales the whole model


def run_cost_ladder_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    candidates: Sequence[Tuple[int, int]] | None = None,
    multipliers: Sequence[float] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
) -> List[Dict[str, Any]]:
    """Evaluate SMA candidates under an execution-cost ladder.

    Each multiplier scales spread, impact and commission together (see
    ``_with_slippage_mult``). Survivors that PASS at 1× but FAIL at 2×/3× are fragile
    to costs — institutional desks reject those early. Does not mutate the caller's
    settings object.
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
            params["cost_mult"] = float(m)
            params["slippage_bps"] = float(base_bps * m)
            params["slippage_model"] = str(stressed.slippage.model)
            params["spread_bps_default"] = float(stressed.slippage.spread_bps_default)
            params["impact_y"] = float(stressed.slippage.impact_y)
            params["commission_per_share"] = float(stressed.commission.per_share)
            params["commission_min_per_order"] = float(stressed.commission.min_per_order)
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
