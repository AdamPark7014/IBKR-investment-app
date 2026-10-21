from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, List, Optional

import pandas as pd
import pytest

import ibtrader.data.service as svc_mod
from ibtrader.data import providers as prov_mod
from ibtrader.data.cache import load_from_cache
from ibtrader.data.universe import (
    UniverseEntry,
    UniverseSpec,
    active_symbols,
    clip_to_lifecycle,
    load_universe_spec,
)
from ibtrader.data.vintage import load_vintage

REPO = Path(__file__).resolve().parent.parent
TEN_ETF = REPO / "config" / "universe-10etf.json"


def _df(rows: int, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=rows) if end else pd.bdate_range(start, periods=rows)
    price = 100.0 + pd.Series(range(rows), index=idx).astype(float) * 0.5
    df = pd.DataFrame({"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 1000.0}, index=idx)
    df.index.name = "date"
    return df


@contextmanager
def _ibtrader_logs(caplog: Any) -> Iterator[None]:
    lg = logging.getLogger("ibtrader")
    lg.addHandler(caplog.handler)
    prev = lg.level
    lg.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        lg.removeHandler(caplog.handler)
        lg.setLevel(prev)


# ----------------------------------------------------------------------------------------
# config/universe-10etf.json
# ----------------------------------------------------------------------------------------


def test_ten_etf_spec_loads_with_boxes_and_inception_dates() -> None:
    spec = load_universe_spec(TEN_ETF)
    assert spec.name == "10etf-risk-parity"
    assert spec.symbols == ["SPY", "VEA", "VWO", "IEF", "TLT", "TIP", "GLD", "PDBC", "VNQ", "BIL"]
    boxes = spec.boxes()
    assert set(boxes) == {
        "us_equity",
        "developed_ex_us_equity",
        "emerging_equity",
        "treasuries_intermediate",
        "treasuries_long",
        "tips",
        "gold",
        "commodities",
        "reit",
        "cash",
    }
    assert all(len(v) == 1 for v in boxes.values())
    for e in spec.entries:
        assert e.listed_from is not None, e.symbol
        assert e.delisted_on is None, e.symbol
        assert e.spread_bps is not None and e.spread_bps <= 5.0
    spy = spec.get("spy")
    assert spy is not None and spy.listed_from == date(1993, 1, 22)
    # the playbook ceiling: PDBC and TIP up to 5 bp, the rest 2 bp
    assert {e.symbol for e in spec.entries if e.spread_bps == 5.0} == {"PDBC", "TIP"}
    assert spec.notes is not None and "Tiingo" in spec.notes


def test_ten_etf_active_symbols_follow_inception() -> None:
    spec = load_universe_spec(TEN_ETF)
    assert active_symbols(spec, "2000-01-01") == ["SPY"]
    assert set(active_symbols(spec, date(2005, 1, 1))) == {"SPY", "IEF", "TLT", "TIP", "GLD", "VNQ"}
    assert len(spec.active_symbols("2026-01-01")) == 10


# ----------------------------------------------------------------------------------------
# UniverseSpec / clip_to_lifecycle
# ----------------------------------------------------------------------------------------


def _entry(**kw: Any) -> UniverseEntry:
    base = {"symbol": "ABC", "asset_class": "equity", "box": "us_equity"}
    base.update(kw)
    return UniverseEntry(**base)


def test_clip_removes_bars_before_listing_and_reports_count() -> None:
    df = _df(23, start="2024-01-01")  # 2024-01-01 .. 2024-01-31
    entry = _entry(listed_from=date(2024, 1, 10))
    out, rep = clip_to_lifecycle(entry, df)
    assert out.index.min() == pd.Timestamp("2024-01-10")
    assert rep.removed_before == 7 and rep.removed_after == 0 and rep.removed == 7
    assert len(out) == len(df) - 7


def test_clip_removes_bars_after_delisting() -> None:
    df = _df(23, start="2024-01-01")
    entry = _entry(delisted_on=date(2024, 1, 19))
    out, rep = clip_to_lifecycle(entry, df)
    assert out.index.max() == pd.Timestamp("2024-01-19")
    assert rep.removed_after == 8 and rep.removed_before == 0


def test_clip_is_noop_without_lifecycle_dates_and_for_empty_frames() -> None:
    df = _df(5, start="2024-01-01")
    out, rep = clip_to_lifecycle(_entry(), df)
    assert out is df and rep.removed == 0
    empty, rep2 = clip_to_lifecycle(_entry(listed_from=date(2024, 1, 1)), pd.DataFrame())
    assert empty.empty and rep2.removed == 0


def test_clip_handles_tz_aware_index() -> None:
    df = _df(10, start="2024-01-01")
    df.index = pd.DatetimeIndex(df.index).tz_localize("UTC")
    out, rep = clip_to_lifecycle(_entry(listed_from=date(2024, 1, 5)), df)
    assert rep.removed_before == 4 and len(out) == 6


def test_spec_clip_unknown_symbol_untouched_with_warning(caplog: Any) -> None:
    spec = UniverseSpec(name="t", entries=[_entry(symbol="SPY", listed_from=date(2024, 1, 5))])
    df = _df(5, start="2024-01-01")  # 2024-01-01 .. 2024-01-05 (business days)
    with _ibtrader_logs(caplog):
        out, rep = spec.clip_to_lifecycle("QQQ", df)
    assert out is df and rep.removed == 0
    assert any("universe_symbol_sin_ciclo_de_vida" in r.getMessage() for r in caplog.records)
    clipped, rep2 = spec.clip_to_lifecycle("spy", df)
    assert rep2.removed_before == 4 and len(clipped) == 1


def test_delisted_symbol_is_inactive_after_delisting() -> None:
    spec = UniverseSpec(
        name="t",
        entries=[
            _entry(symbol="SPY", listed_from=date(1993, 1, 22)),
            _entry(symbol="DEAD", listed_from=date(2010, 1, 1), delisted_on=date(2020, 1, 1)),
        ],
    )
    assert spec.active_symbols(date(2019, 6, 1)) == ["SPY", "DEAD"]
    assert spec.active_symbols(date(2021, 1, 1)) == ["SPY"]
    assert spec.active_symbols(date(2020, 1, 1)) == ["SPY", "DEAD"]  # inclusive on the delisting day
    assert spec.active_symbols(date(2009, 12, 31)) == ["SPY"]


def test_spec_rejects_duplicates_and_bad_dates(tmp_path: Any) -> None:
    with pytest.raises(ValueError, match="duplicado"):
        UniverseSpec(name="t", entries=[_entry(symbol="SPY"), _entry(symbol="spy")])
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"symbols": [{"symbol": "SPY", "asset_class": "equity", "box": "x", "listed_from": "22/01/1993"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fecha ISO"):
        load_universe_spec(bad)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"symbols": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="vacío"):
        load_universe_spec(empty)
    with pytest.raises(FileNotFoundError):
        load_universe_spec(tmp_path / "missing.json")


def test_yaml_spec_loads(tmp_path: Any) -> None:
    p = tmp_path / "u.yaml"
    p.write_text(
        "name: mini\n"
        "symbols:\n"
        "  - symbol: spy\n"
        "    asset_class: equity\n"
        "    box: us_equity\n"
        "    listed_from: 1993-01-22\n",
        encoding="utf-8",
    )
    spec = load_universe_spec(p)
    assert spec.name == "mini" and spec.symbols == ["SPY"]
    assert spec.entries[0].listed_from == date(1993, 1, 22)


# ----------------------------------------------------------------------------------------
# service.py applies the clip when data.universe_file is set
# ----------------------------------------------------------------------------------------


class _Prov(prov_mod.MarketDataProvider):
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.calls: List[str] = []

    def fetch_daily_ohlcv(self, symbol: str, start: Optional[str] = None, end: Optional[str] = None):
        self.calls.append(symbol)
        return prov_mod.DataFrameWithMeta(self.df, prov_mod.DataLineage(source="yahoo", methodology="test"))


def test_service_clips_to_universe_lifecycle(tmp_path: Any, monkeypatch: Any) -> None:
    from ibtrader.config import AppSettings

    today = datetime.now(timezone.utc).date()
    full = _df(400, end=str(today))
    listed_from = full.index[100].date()  # 300 bars survive (>= 252 required by the gate)
    ufile = tmp_path / "universe.json"
    ufile.write_text(
        json.dumps(
            {
                "name": "test",
                "symbols": [
                    {"symbol": "SPY", "asset_class": "equity", "box": "us_equity", "listed_from": str(listed_from)}
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    monkeypatch.setenv("DATA__UNIVERSE_FILE", str(ufile))
    prov = _Prov(full)
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: prov)
    s = AppSettings()
    s.resolve_paths()
    s.data.providers = ["yahoo"]
    s.universe.symbols = ["SPY"]
    out = svc_mod.load_universe_v2(s)
    assert len(out["SPY"]) == 300
    assert out["SPY"].index.min().date() == listed_from
    # the clipped frame is what gets cached and snapshotted, never the raw one
    cached = load_from_cache(s.data.cache_dir, "SPY", "1d")
    assert cached is not None and len(cached) == 300
    snap = load_vintage(s.data.vintage_dir, str(today))
    assert len(snap["SPY"]) == 300
    # a cache hit goes through the same clip and stays at 300 rows without refetching
    out2 = svc_mod.load_universe_v2(s)
    assert len(out2["SPY"]) == 300 and prov.calls == ["SPY"]


def test_service_lifecycle_can_starve_a_symbol_into_exclusion(tmp_path: Any, monkeypatch: Any) -> None:
    """A symbol listed too recently to satisfy min_rows is excluded loudly, not padded."""
    from ibtrader.config import AppSettings

    today = datetime.now(timezone.utc).date()
    full = _df(400, end=str(today))
    ufile = tmp_path / "universe.json"
    ufile.write_text(
        json.dumps(
            {
                "symbols": [
                    {"symbol": "SPY", "asset_class": "equity", "box": "us_equity", "listed_from": "1993-01-22"},
                    {"symbol": "NEW", "asset_class": "equity", "box": "x", "listed_from": str(full.index[-50].date())},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    monkeypatch.setenv("DATA__UNIVERSE_FILE", str(ufile))
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: _Prov(full))
    s = AppSettings()
    s.resolve_paths()
    s.data.providers = ["yahoo"]
    s.universe.symbols = ["SPY", "NEW"]
    out = svc_mod.load_universe_v2(s)
    assert set(out) == {"SPY"}
