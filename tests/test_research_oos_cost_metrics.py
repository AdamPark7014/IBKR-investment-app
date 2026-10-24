"""OOS research rows expose avg_cost_bps_per_order and cost_drag_annual_pct."""

from __future__ import annotations

from ibtrader.backtest.metrics import PerformanceStats, copy_oos_cost_metrics
from ibtrader.config import AppSettings
from ibtrader.research.runner import run_sma_research
from ibtrader.validation.walkforward import _enrich_window_stats, walk_forward_sma

import pandas as pd


def _wf_data() -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=320)
    close = pd.Series(100.0, index=idx).add(pd.Series(range(len(idx)), index=idx) * 0.05)
    return pd.DataFrame({"close": close, "open": close, "high": close, "low": close, "volume": 1_000_000})


def test_enrich_window_stats_copies_cost_fields_from_base() -> None:
    base = {
        "sharpe": 0.5,
        "avg_cost_bps_per_order": 3.25,
        "cost_drag_annual_pct": 1.1,
    }
    out = _enrich_window_stats(base, [], 0.0, 100_000.0)
    assert out["avg_cost_bps_per_order"] == 3.25
    assert out["cost_drag_annual_pct"] == 1.1


def test_copy_oos_cost_metrics_from_performance_stats() -> None:
    st = PerformanceStats(
        cagr=0.0,
        sharpe=0.0,
        sortino=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        exposure=0.0,
        total_return=0.0,
        volatility=0.0,
        avg_cost_bps_per_order=2.75,
        cost_drag_annual_pct=0.85,
    )
    oos: dict = {"sharpe": 0.2}
    copy_oos_cost_metrics(oos, st)
    assert oos["avg_cost_bps_per_order"] == 2.75
    assert oos["cost_drag_annual_pct"] == 0.85


def test_walk_forward_stitched_oos_includes_cost_headlines() -> None:
    settings = AppSettings()
    wf, _summary = walk_forward_sma(
        settings,
        {"SPY": _wf_data()},
        "SPY",
        param_grid=[(5, 20)],
        n_folds=2,
        warmup_bars=40,
    )
    stitched = wf.stitched_oos
    assert "avg_cost_bps_per_order" in stitched
    assert "cost_drag_annual_pct" in stitched
    assert float(stitched["avg_cost_bps_per_order"]) >= 0.0
    assert float(stitched["cost_drag_annual_pct"]) >= 0.0


def test_run_sma_research_oos_includes_cost_headlines() -> None:
    settings = AppSettings()
    rows = run_sma_research(
        settings,
        {"SPY": _wf_data()},
        "SPY",
        candidates=[(5, 20)],
        n_folds=2,
    )
    oos = rows[0]["oos"]
    assert "avg_cost_bps_per_order" in oos
    assert "cost_drag_annual_pct" in oos
