from __future__ import annotations

from typer.testing import CliRunner
import pandas as pd
from datetime import datetime, timezone

import ibtrader.ops.cli as cli_mod


def _mk(len_days: int = 300) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    # Synthetic price with some variation
    base = 100.0
    vals = [base]
    for i in range(1, len(idx)):
        vals.append(vals[-1] * (1.0 + 0.0005))
    px = pd.Series(vals, index=idx).astype(float)
    df = pd.DataFrame({"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0}, index=idx)
    return df


def test_walk_forward_cli(monkeypatch):
    def fake_loader(settings):
        return {"SPY": _mk()}
    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["walk-forward", "--exp-id", "p9test"])
    assert res.exit_code == 0
    out = res.stdout
    assert "'in_sample':" in out and "'validation':" in out and "'oos':" in out
