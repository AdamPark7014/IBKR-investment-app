from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod


def _mk(len_days: int = 400) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    # Simple oscillation to induce trades
    vals = [100.0]
    for i in range(1, len(idx)):
        vals.append(vals[-1] * (1.0 + (0.002 if (i % 20) < 10 else -0.002)))
    px = pd.Series(vals, index=idx).astype(float)
    df = pd.DataFrame({"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0}, index=idx)
    return df


def test_walk_forward_fold_independence(monkeypatch):
    def fake_loader(settings):
        return {"SPY": _mk()}

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    res1 = runner.invoke(cli_mod.app, ["walk-forward", "--exp-id", "wf1"])
    assert res1.exit_code == 0
    res2 = runner.invoke(cli_mod.app, ["walk-forward", "--exp-id", "wf2"])
    assert res2.exit_code == 0
    # Simple equality on total OOS trades to ensure no cross-run leakage
    import re, json

    def _parse_oos(s: str) -> int:
        m = re.search(r"\{(.|\n)*\}$", s)
        assert m
        payload = json.loads(m.group(0))
        return int(payload["oos_total_trades"])

    assert _parse_oos(res1.stdout) == _parse_oos(res2.stdout)

