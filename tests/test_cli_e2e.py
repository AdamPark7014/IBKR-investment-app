from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pandas as pd
import typer
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.data import providers as prov_mod
from ibtrader.data.service import load_universe_v2 as real_load_universe_v2


def _make_df(rows: int = 260) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=rows + 10)
    idx = pd.bdate_range(start=start.date(), periods=rows)
    price = 100.0 + pd.Series(range(rows), index=idx).astype(float)
    df = pd.DataFrame(
        {"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 1000.0},
        index=idx,
    )
    df.index.name = "date"
    return df


class _FakeYFProv(prov_mod.MarketDataProvider):
    def __init__(self) -> None:
        self.captured: Dict[str, str] = {}

    def fetch_daily_ohlcv(self, symbol: str, start: str | None = None, end: str | None = None):
        assert start is not None and end is not None
        self.captured["start"] = start
        self.captured["end"] = end
        lin = prov_mod.DataLineage(source="yahoo-mock", methodology="test")
        return prov_mod.DataFrameWithMeta(_make_df(), lin)


def test_cli_download_backtest_compare(monkeypatch: Any) -> None:
    # Mock the universe loader to return deterministic data without network
    def fake_loader(settings):
        return {"SPY": _make_df()}
    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    # download-data
    res = runner.invoke(cli_mod.app, ["download-data"])
    assert res.exit_code == 0
    assert "SPY" in res.stdout
    # backtest-sample with exp-id
    res_bt = runner.invoke(cli_mod.app, ["backtest-sample", "--exp-id", "e2e"])
    assert res_bt.exit_code == 0
    assert "'report':" in res_bt.stdout
    # compare-directions
    res_cmp = runner.invoke(cli_mod.app, ["compare-directions", "--exp-id", "e2e2"])
    assert res_cmp.exit_code == 0
    assert "'directions':" in res_cmp.stdout


def test_service_calls_yahoo_with_window(monkeypatch: Any) -> None:
    fake = _FakeYFProv()
    # Patch both module and service symbols to ensure our fake is used
    monkeypatch.setattr(prov_mod, "YahooProvider", lambda: fake)
    import ibtrader.data.service as svc_mod
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: fake)
    # Build default settings
    from ibtrader.config import AppSettings
    s = AppSettings()
    s.resolve_paths()
    # Ensure no cache to force fetch
    from ibtrader.data.cache import cache_path
    import os
    try:
        os.remove(cache_path(s.data.cache_dir, "SPY", s.engine.bar_size))
    except Exception:
        pass
    out = real_load_universe_v2(s)
    assert "SPY" in out
    # Verify window length
    start = pd.Timestamp(fake.captured["start"])
    assert (pd.Timestamp(datetime.now(timezone.utc).date()) - start).days >= 252
