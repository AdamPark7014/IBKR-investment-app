from __future__ import annotations

from typer.testing import CliRunner
import pandas as pd
from datetime import datetime, timezone

import ibtrader.ops.cli as cli_mod


def _mk(len_days: int = 300) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    px = pd.Series(100.0 + (idx - idx[0]).days * 0.1, index=idx).astype(float)
    df = pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0},
        index=idx,
    )
    return df


def test_signal_validate_cli(monkeypatch):
    def fake_loader(settings):
        return {"SPY": _mk()}
    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    res = runner.invoke(
        cli_mod.app,
        ["signal-validate", "--direction", "long_only", "--exp-id", "p7test"],
    )
    assert res.exit_code == 0
    assert "'cv_aggregate':" in res.stdout
