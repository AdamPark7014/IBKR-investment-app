from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.research.loss_mitigation import (
    run_loss_mitigation_research,
    summarize_loss_mitigation,
)
from ibtrader.research.market_analyzer import analyze_market
from ibtrader.research.xsection_runner import run_xsection_research


def _mk(len_days: int = 450, seed: float = 0.0) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    # Mild uptrend + wiggle so SMA/trend filters have structure
    t = pd.Series(range(len(idx)), index=idx).astype(float)
    wiggle = ((t % 30) - 15) * 0.35
    px = (100.0 + seed + 0.05 * t + wiggle).astype(float)
    return pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1000.0}, index=idx
    )


def test_market_analyzer_ranks_and_actions() -> None:
    data = {
        "SPY": _mk(seed=0),
        "QQQ": _mk(seed=5),
        "IWM": _mk(seed=-3),
    }
    # Make IWM weaker: flat/down
    weak = data["IWM"].copy()
    weak["close"] = weak["close"] * 0.85
    weak["open"] = weak["close"]
    weak["high"] = weak["close"]
    weak["low"] = weak["close"]
    data["IWM"] = weak

    rep = analyze_market(data, symbols=["SPY", "QQQ", "IWM"], benchmark="SPY")
    assert rep["n_symbols"] == 3
    assert "regime" in rep
    assert "ranked" in rep
    assert "model" in rep
    assert rep["model"]["name"].startswith("WARDEN")
    assert set(rep["action_counts"]) >= {"AVOID", "WATCH", "RESEARCH_CANDIDATE"}
    assert "disclaimer" in rep
    assert "NOT" in rep["disclaimer"]
    actions = {r["symbol"]: r["action"] for r in rep["ranked"]}
    assert all(a in {"AVOID", "WATCH", "RESEARCH_CANDIDATE"} for a in actions.values())
    assert "engines" in rep["ranked"][0]
    assert "confidence" in rep["ranked"][0]["scores"]


def test_loss_mitigation_runs_overlays() -> None:
    s = AppSettings()
    rows = run_loss_mitigation_research(s, {"SPY": _mk()}, "SPY", n_folds=3)
    assert len(rows) == 3
    assert rows[0]["params"]["overlay"] == "none"
    assert any(r["params"]["overlay"] == "trend_ma" for r in rows)
    assert any(r["params"]["overlay"] == "risk_tight" for r in rows)
    for r in rows:
        assert "gate_passed" in r
        assert "max_dd" in (r.get("oos") or {})
    summary = summarize_loss_mitigation(rows)
    assert "any_dd_improvement" in summary


def test_xsection_research_needs_multi_name() -> None:
    s = AppSettings()
    assert run_xsection_research(s, {"SPY": _mk()}, n_folds=2) == []
    data = {"SPY": _mk(seed=0), "QQQ": _mk(seed=2), "IWM": _mk(seed=1)}
    rows = run_xsection_research(s, data, candidates=[(60, 2)], n_folds=3)
    assert len(rows) == 1
    assert rows[0]["candidate_id"].startswith("xsection_")
    assert "gate_passed" in rows[0]
