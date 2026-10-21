from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.data import providers as prov_mod
from ibtrader.data.service import load_universe_v2 as real_load_universe_v2


def _make_df(rows: int = 260) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()
    idx = pd.bdate_range(end=today, periods=rows)
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


def test_cli_download_backtest_compare(monkeypatch: Any, tmp_path) -> None:
    # Use FixtureProvider end-to-end (no mocks)
    monkeypatch.setenv("DATA__PROVIDERS", '["fixture"]')
    monkeypatch.setenv("DATA__FIXTURE_DIR", "./tests/fixtures")
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
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


def test_service_calls_yahoo_with_window(monkeypatch: Any, tmp_path) -> None:
    fake = _FakeYFProv()
    # Patch both module and service symbols to ensure our fake is used
    monkeypatch.setattr(prov_mod, "YahooProvider", lambda: fake)
    import ibtrader.data.service as svc_mod
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: fake)
    # Build default settings
    from ibtrader.config import AppSettings
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    s = AppSettings()
    s.resolve_paths()
    # Ensure no cache to force fetch
    # (no-op: tmp cache is empty)
    out = real_load_universe_v2(s)
    assert "SPY" in out
    # Verify window length
    start = pd.Timestamp(fake.captured["start"])
    assert (pd.Timestamp(datetime.now(timezone.utc).date()) - start).days >= 252


def test_cache_poisoning_blocked(monkeypatch: Any, tmp_path) -> None:
    # Write a poisoned cache (future-dated, mock source)
    from ibtrader.data.cache import save_lineage, save_to_cache
    from ibtrader.data.lineage import DataLineage
    # Future dates
    idx = pd.date_range("2099-01-01", periods=260, freq="B")
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        index=idx,
    )
    save_to_cache(str(tmp_path), "SPY", "1d", df)
    save_lineage(str(tmp_path), "SPY", "1d", DataLineage(source="yahoo-mock"))
    # Patch YahooProvider to a valid provider that returns sane data
    class _ValidProv(prov_mod.MarketDataProvider):
        def fetch_daily_ohlcv(self, symbol: str, start: str | None = None, end: str | None = None):
            lin = prov_mod.DataLineage(source="yahoo", methodology="test")
            return prov_mod.DataFrameWithMeta(_make_df(), lin)
    monkeypatch.setattr(prov_mod, "YahooProvider", lambda: _ValidProv())
    import ibtrader.data.service as svc_mod
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: _ValidProv())
    # Load with tmp cache dir
    from ibtrader.config import AppSettings
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    s = AppSettings()
    s.resolve_paths()
    out = real_load_universe_v2(s)
    assert "SPY" in out
    # Ensure last bar is not in the future
    assert out["SPY"].index.max() <= pd.Timestamp(datetime.now(timezone.utc).date())
