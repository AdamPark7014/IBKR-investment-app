from __future__ import annotations

from typer.testing import CliRunner
import pandas as pd
from datetime import datetime, timezone

import ibtrader.ops.cli as cli_mod


def _mk(len_days: int = 260) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    px = pd.Series(100.0 + (idx - idx[0]).days * 0.05, index=idx).astype(float)
    df = pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0},
        index=idx,
    )
    return df


def test_run_with_risk_cli_abstain_when_threshold_high(monkeypatch):
    def fake_loader(settings):
        return {"SPY": _mk()}
    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    res = runner.invoke(
        cli_mod.app,
        ["run-with-risk", "--exp-id", "p8test", "--risk-on-threshold", "0.99"],
    )
    assert res.exit_code == 0
    assert "'metrics':" in res.stdout
    assert "'artifact':" in res.stdout
