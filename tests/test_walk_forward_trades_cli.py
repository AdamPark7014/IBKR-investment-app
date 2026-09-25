from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod


def _mk(len_days: int = 600) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0, index=idx).astype(float)
    # Create gentle oscillation to ensure SMA crosses in OOS folds
    wiggle = (pd.Series(range(len(idx)), index=idx) % 40).astype(float)
    wiggle = (wiggle - 20.0) * 0.5  # range approx [-10, +10]
    px = base + wiggle
    df = pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0},
        index=idx,
    )
    return df


def test_walk_forward_produces_trades(monkeypatch):
    def fake_loader(settings):
        return {"SPY": _mk()}
    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    # Relax risk limits via env
    monkeypatch.setenv("RISK__MAX_POSITION_PCT", "100.0")
    monkeypatch.setenv("RISK__MAX_TOTAL_EXPOSURE_PCT", "100.0")
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["walk-forward", "--exp-id", "p9_wf_test"])
    assert res.exit_code == 0
    out = res.stdout
    assert "'oos_total_trades':" in out
    # Ensure non-zero trades
    assert "'oos_total_trades': 0" not in out
