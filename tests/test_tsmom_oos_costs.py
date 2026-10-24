"""TSMOM OOS rows expose execution cost headline metrics."""

from __future__ import annotations

import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.research.tsmom_runner import run_tsmom_research


def _wf_data() -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=320)
    close = pd.Series(100.0, index=idx).add(pd.Series(range(len(idx)), index=idx) * 0.05)
    return pd.DataFrame(
        {"close": close, "open": close, "high": close, "low": close, "volume": 1_000_000}
    )


def test_run_tsmom_research_oos_has_avg_cost_bps_per_order() -> None:
    settings = AppSettings()
    rows = run_tsmom_research(
        settings,
        {"SPY": _wf_data()},
        "SPY",
        lookbacks=[21],
        n_folds=2,
    )
    oos = rows[0]["oos"]
    assert "avg_cost_bps_per_order" in oos
