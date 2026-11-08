"""End-to-end sanity of the model: it must earn on trends that exist and not on noise (2026-11-08).

Synthetic universes, fixed seeds. Trending: each asset's drift flips sign every 120–300 days
(±20 %/yr, 15 % vol). Noise: same vol, no drift. The trend system must beat static risk parity
clearly on the first and must not systematically beat it on the second. This proves the pipeline
extracts a real signal when there is one; it says nothing about real markets (that is the job of
``research-portfolio`` with the strict gates).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.pipeline.rules import DEFAULT_RULES
from ibtrader.pipeline.system import SystemConfig, run_system

SEEDS = (1, 2, 3)


def _universe(trend: bool, seed: int, n: int = 2600, k: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2014-01-01", periods=n)
    cols = {}
    for j in range(k):
        drift = np.zeros(n)
        if trend:
            sign, t = 1.0, 0
            while t < n:
                length = int(rng.integers(120, 300))
                drift[t:t + length] = sign * 0.20 / 252
                sign, t = -sign, t + length
        cols[f"S{j}"] = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.15 / np.sqrt(252), n)))
    return pd.DataFrame(cols, index=idx)


def _sharpe(px: pd.DataFrame, rules: tuple) -> float:
    out = run_system(px, SystemConfig(rules=rules, scalar_min_periods=250, fdm_min_periods=120,
                                      idm_min_periods=120))
    assert out.warmup_end is not None
    w = out.target_weights.loc[out.warmup_end:].fillna(0.0)
    r = (w.shift(1) * px.pct_change().loc[w.index]).sum(axis=1).iloc[1:]
    return float(r.mean() / r.std() * np.sqrt(252))


def _edge(trend: bool) -> float:
    diffs = []
    for s in SEEDS:
        px = _universe(trend, s)
        diffs.append(_sharpe(px, tuple(DEFAULT_RULES)) - _sharpe(px, ("long_const",)))
    return float(np.mean(diffs))


def test_trend_system_extracts_real_trends() -> None:
    assert _edge(trend=True) > 0.3


def test_trend_system_does_not_invent_an_edge_on_noise() -> None:
    assert abs(_edge(trend=False)) < 0.25
