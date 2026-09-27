from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.research.embargo_sensitivity import run_embargo_sensitivity


def _mk(len_days: int = 300) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0, index=idx)
    wiggle = ((pd.Series(range(len(idx)), index=idx) % 30) - 15) * 0.4
    px = (base + wiggle).astype(float)
    return pd.DataFrame({"close": px, "open": px, "high": px, "low": px, "volume": 1000.0}, index=idx)


def test_embargo_sensitivity_runs_multiple_widths() -> None:
    s = AppSettings()
    report = run_embargo_sensitivity(
        s,
        {"SPY": _mk()},
        "SPY",
        fast=10,
        slow=30,
        embargo_widths=[0, 5, 10],
        n_splits=4,
    )
    assert len(report["rows"]) == 3
    assert {r["embargo"] for r in report["rows"]} == {0, 5, 10}
    assert "mean_fold_sharpe_range" in report
    assert "unstable_across_embargo" in report
    for r in report["rows"]:
        assert r["n_folds"] > 0
        assert len(r["fold_sharpes"]) == r["n_folds"]
