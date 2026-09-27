from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.research.multi_asset import (
    DEFAULT_RESEARCH_SYMBOLS,
    resolve_research_symbols,
    run_multi_asset_sma_research,
    summarize_cross_section,
)


def _mk(len_days: int = 400, seed: int = 0) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0 + seed, index=idx)
    wiggle = ((pd.Series(range(len(idx)), index=idx) % 30) - 15) * (0.4 + 0.05 * seed)
    px = (base + wiggle).astype(float)
    return pd.DataFrame({"close": px, "open": px, "high": px, "low": px, "volume": 1000.0}, index=idx)


def test_resolve_research_symbols_prefers_defaults() -> None:
    data = {s: _mk() for s in ("SPY", "QQQ", "EXTRA")}
    assert resolve_research_symbols(data) == ["SPY", "QQQ"]
    assert resolve_research_symbols(data, ["QQQ", "MISSING"]) == ["QQQ"]


def test_multi_asset_runs_per_symbol_and_summarizes() -> None:
    s = AppSettings()
    data = {
        "SPY": _mk(seed=0),
        "QQQ": _mk(seed=1),
        "IWM": _mk(seed=2),
    }
    rows = run_multi_asset_sma_research(s, data, symbols=["SPY", "QQQ", "IWM"], n_folds=3)
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"SPY", "QQQ", "IWM"}
    for r in rows:
        assert r["candidate_id"].startswith("sma_xasset_")
        assert r["params"].get("cross_section") is True
        assert "gate_passed" in r
    summary = summarize_cross_section(rows)
    assert summary["n_rows"] == 3
    assert summary["n_pass"] + summary["n_fail"] == 3
    assert 0.0 <= summary["pass_rate"] <= 1.0
    assert set(summary["symbols"]) == {"SPY", "QQQ", "IWM"}


def test_default_research_symbols_listed() -> None:
    assert "SPY" in DEFAULT_RESEARCH_SYMBOLS
    assert len(DEFAULT_RESEARCH_SYMBOLS) >= 3
