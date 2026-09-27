from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.research.mean_reversion_runner import run_mean_reversion_research
from ibtrader.research.report import build_honest_report
from ibtrader.research.turnover_diag import diagnose_turnover


def _mk(len_days: int = 400, seed: int = 0) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0 + seed, index=idx)
    wiggle = ((pd.Series(range(len(idx)), index=idx) % 25) - 12) * 0.5
    px = (base + wiggle).astype(float)
    return pd.DataFrame({"close": px, "open": px, "high": px, "low": px, "volume": 1000.0}, index=idx)


def test_mean_reversion_research_runs() -> None:
    s = AppSettings()
    rows = run_mean_reversion_research(s, {"SPY": _mk()}, "SPY", candidates=[(20, 2.0)], n_folds=3)
    assert len(rows) == 1
    assert rows[0]["candidate_id"].startswith("mr_")
    assert "gate_passed" in rows[0]
    assert "oos" in rows[0]


def test_turnover_diag_flags_fragile() -> None:
    cands = [
        {
            "candidate_id": "a",
            "gate_passed": False,
            "oos": {"turnover": 20.0, "sharpe": -0.1},
        },
        {
            "candidate_id": "b",
            "gate_passed": True,
            "oos": {"turnover": 1.0, "sharpe": 0.5},
        },
    ]
    rep = diagnose_turnover(cands, high_turnover_threshold=8.0)
    assert rep["n_turnover_fragile"] == 1
    assert rep["rows"][0]["turnover_fragile"] is True


def test_honest_report_verdict() -> None:
    suite = {
        "symbol": "SPY",
        "candidates": [
            {"candidate_id": "sma_10_30", "gate_passed": False},
            {"candidate_id": "tsmom_21", "gate_passed": True},
        ],
        "tracks": {
            "sma_grid": [{"candidate_id": "sma_10_30", "gate_passed": False}],
            "tsmom": [{"candidate_id": "tsmom_21", "gate_passed": True}],
        },
        "pbo": {"pbo": 0.7, "high_overfit_risk": True},
        "dsr": {"dsr": 0.4, "high_conviction": False},
        "cpcv": {"frac_positive": 0.2, "fragile_cpcv": True},
        "cross_section": {"pass_rate": 0.2, "fragile_cross_section": True},
        "embargo_sensitivity": {"unstable_across_embargo": False},
    }
    rep = build_honest_report(suite)
    assert rep["n_pass"] == 1
    assert rep["verdict"] == "PASS_GATES_BUT_DIAGNOSTICS_SKEPTICAL"
    assert any("PBO" in f for f in rep["skeptical_flags"])
