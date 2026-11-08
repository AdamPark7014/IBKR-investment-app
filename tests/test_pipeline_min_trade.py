"""Mínimo por operación: el sistema no cuenta operaciones que producción nunca enviaría."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.buffering import apply_buffer
from ibtrader.pipeline.system import SystemConfig, run_system


def test_small_edge_trades_wait_until_worth_a_commission() -> None:
    idx = pd.bdate_range("2026-01-01", periods=5)
    target = pd.Series([100.0, 103.0, 106.0, 112.0, 0.0], index=idx)
    buf = pd.Series(1.0, index=idx)
    plain = apply_buffer(target, buf)
    assert list(plain) == [99.0, 102.0, 105.0, 111.0, 1.0]
    banded = apply_buffer(target, buf, min_trade=pd.Series(5.0, index=idx))
    # entry is never blocked; +3 waits; at 106 the edge (101) is 1 away < 5 -> waits; at 112 edge 107 -> trades
    assert list(banded) == [99.0, 99.0, 99.0, 107.0, 1.0]  # exit to the edge is never blocked


def _prices(n: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2020-01-01", periods=n)
    vols = {"SPY": 0.16, "IEF": 0.07, "GLD": 0.15, "BIL": 0.003}
    return pd.DataFrame({s: 100 * np.exp(np.cumsum(rng.normal(0.0002, v / np.sqrt(252), n)))
                         for s, v in vols.items()}, index=idx)


def test_min_trade_cuts_orders_without_levering() -> None:
    px = _prices()
    kw = dict(boxes={"SPY": "eq", "IEF": "bd", "GLD": "au", "BIL": "cash"}, scalar_min_periods=60,
              fdm_min_periods=60, idm_min_periods=60, box_min_periods=40, vol_span=20, step=5)
    a = run_system(px, SystemConfig(**kw)).target_weights.fillna(0.0)
    b = run_system(px, SystemConfig(min_trade_frac=0.01, **kw)).target_weights.fillna(0.0)
    orders = lambda w: int((w.diff().abs() > 1e-9).sum().sum())  # noqa: E731
    assert orders(b) < orders(a)
    assert float(b.abs().sum(axis=1).max()) <= 1.0 + 1e-9


def test_min_trade_frac_validated() -> None:
    with pytest.raises(ValueError):
        SystemConfig(min_trade_frac=-0.1)
