from __future__ import annotations

from typer.testing import CliRunner
import pandas as pd
from datetime import datetime, timezone

import ibtrader.ops.cli as cli_mod


def _series(len_days: int = 400) -> pd.Series:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    px = pd.Series(100.0 + (idx - idx[0]).days * 0.05, index=idx).astype(float)
    px.name = "close"
    return px


def test_regime_fit_cli(monkeypatch):
    def fake_loader(settings):
        df = pd.DataFrame(
            {"close": _series(400), "open": 0, "high": 0, "low": 0, "volume": 1000.0}
        )
        return {"SPY": df}
    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["regime-fit", "--n-components", "2", "--exp-id", "p6test"])
    assert res.exit_code == 0
    assert "'components': 2" in res.stdout
