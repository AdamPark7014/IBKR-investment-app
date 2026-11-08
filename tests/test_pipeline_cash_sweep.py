"""Cash box out of the risk chain + sweep of idle capital; static risk parity baseline (2026-11-08)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.pipeline.system import SystemConfig, run_system
from ibtrader.research.portfolio_runner import portfolio_candidates

SPEC = {"SPY": (0.08, 0.17), "IEF": (0.02, 0.07), "GLD": (0.04, 0.15), "BIL": (0.02, 0.004)}
BOXES = {"SPY": "us_equity", "IEF": "treasuries", "GLD": "gold", "BIL": "cash"}


def _px() -> pd.DataFrame:
    idx = pd.bdate_range("2015-01-01", periods=1400)
    rng = np.random.default_rng(3)
    return pd.DataFrame({s: 100 * np.exp(np.cumsum(rng.normal(m / 252, v / np.sqrt(252), len(idx))))
                         for s, (m, v) in SPEC.items()}, index=idx)


def test_cash_symbol_never_swallows_the_leverage_cap() -> None:
    px = _px()
    out = run_system(px, SystemConfig(boxes=BOXES))
    tail = out.target_weights.iloc[-250:]
    risky = tail[["SPY", "IEF", "GLD"]].sum(axis=1)
    # Before the fix BIL (σ≈0.4 %) took ~45 % of the book through vol scaling; now it only holds idle cash.
    assert np.allclose(tail["BIL"], (1.0 - risky).clip(lower=0.0))
    assert (tail.sum(axis=1) <= 1.0 + 1e-9).all()
    assert "BIL" not in out.combined_forecast.columns  # never forecast or risk-weighted


def test_sweep_off_or_long_short_leaves_cash() -> None:
    px = _px()
    off = run_system(px, SystemConfig(boxes=BOXES, cash_sweep=False))
    assert "BIL" not in off.target_weights.columns
    ls = run_system(px, SystemConfig(boxes=BOXES, long_only=False))
    assert "BIL" not in ls.target_weights.columns


def test_static_risk_parity_candidate_is_always_long() -> None:
    out = run_system(_px(), SystemConfig(boxes=BOXES, rules=("long_const",)))
    assert out.warmup_end is not None
    w = out.target_weights.loc[out.warmup_end:, ["SPY", "IEF", "GLD"]].iloc[5:]
    assert (w > 0).all().all()
    ids = [c[0] for c in portfolio_candidates("full")]
    assert "pipeline_static_box_risk_parity" in ids and len(ids) == len(set(ids))


def test_known_tbill_etf_is_cash_without_universe_file() -> None:
    boxes = {k: v for k, v in BOXES.items() if k != "BIL"}
    out = run_system(_px(), SystemConfig(boxes=boxes))
    assert "BIL" not in out.combined_forecast.columns and "BIL" in out.target_weights.columns
