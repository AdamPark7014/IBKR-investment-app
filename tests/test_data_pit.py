from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterator, List, Optional

import pandas as pd
import pytest

import ibtrader.data.service as svc_mod
from ibtrader.data import providers as prov_mod
from ibtrader.data.cache import cache_path, load_lineage
from ibtrader.data.validators import validate_pit
from ibtrader.data.vintage import (
    dataset_hash_from_files,
    list_vintages,
    load_manifest,
    load_vintage,
    sha256_file,
    vintage_file_path,
    write_vintage,
)


def _df(rows: int = 10, start: str = "2024-01-01", end: Optional[str] = None, base: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=rows) if end else pd.bdate_range(start, periods=rows)
    price = base + pd.Series(range(rows), index=idx).astype(float) * 0.5
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
# validate_pit
# ----------------------------------------------------------------------------------------

TODAY = date(2024, 2, 1)


def _pit(df: pd.DataFrame, **kw: Any) -> tuple[bool, List[str]]:
    opts = {"max_price_spike_pct": 25.0, "reject_future_bars": True, "today": TODAY}
    opts.update(kw)
    return validate_pit(df, "SPY", **opts)


def test_validate_pit_clean_frame() -> None:
    ok, reasons = _pit(_df(10))
    assert ok and reasons == []


def test_validate_pit_rejects_future_bars_only_when_asked() -> None:
    df = _df(5, start="2024-01-29")  # 2024-01-29 .. 2024-02-02 => 02-02 is after TODAY (02-01)
    ok, reasons = _pit(df)
    assert not ok and any("futura" in r for r in reasons)
    assert "2024-02-02" in " ".join(reasons)
    ok2, reasons2 = _pit(df, reject_future_bars=False)
    assert ok2 and reasons2 == []


def test_validate_pit_detects_close_spikes_and_can_be_disabled() -> None:
    df = _df(10)
    df.iloc[5, df.columns.get_loc("close")] = df["close"].iloc[4] * 1.4  # +40 %
    ok, reasons = _pit(df)
    assert not ok and any("saltos de cierre" in r for r in reasons)
    assert "40.0%" in " ".join(reasons)
    ok2, _ = _pit(df, max_price_spike_pct=0)
    assert ok2
    ok3, _ = _pit(df, max_price_spike_pct=50.0)
    assert ok3


def test_validate_pit_aggregates_every_reason() -> None:
    df = _df(6)
    df.iloc[2, df.columns.get_loc("open")] = float("nan")
    dup = pd.concat([df, df.iloc[[1]]])  # duplicate + non-monotonic
    ok, reasons = _pit(dup)
    assert not ok
    joined = " | ".join(reasons)
    assert "duplicadas" in joined
    assert "no monótono" in joined
    assert "NaN" in joined
    assert len(reasons) >= 3


def test_validate_pit_missing_columns_and_nonpositive_close() -> None:
    df = _df(4).drop(columns=["volume"])
    df.iloc[1, df.columns.get_loc("close")] = 0.0
    ok, reasons = _pit(df)
    assert not ok
    joined = " | ".join(reasons)
    assert "faltan columnas" in joined and "volume" in joined
    assert "cierres <= 0" in joined


def test_validate_pit_handles_tz_aware_index() -> None:
    df = _df(5)
    df.index = pd.DatetimeIndex(df.index).tz_localize("UTC")
    ok, reasons = _pit(df)
    assert ok, reasons


def test_validate_pit_empty_frame() -> None:
    ok, reasons = _pit(pd.DataFrame())
    assert not ok and "vacío" in reasons[0]


# ----------------------------------------------------------------------------------------
# vintages + manifest
# ----------------------------------------------------------------------------------------


def test_write_vintage_is_idempotent_for_same_content(tmp_path: Any) -> None:
    vdir = str(tmp_path / "vint")
    df = _df(30)
    rec = write_vintage(vdir, "SPY", "1d", df, provider="test", vintage_date="2026-10-21")
    path = vintage_file_path(vdir, "2026-10-21", "SPY", "1d")
    assert path.exists() and rec.written is True
    assert rec.path == "vintage_date=2026-10-21/SPY_1d.parquet"
    assert rec.sha256 == sha256_file(path)
    assert rec.rows == 30 and rec.first_bar == "2024-01-01"
    mtime = path.stat().st_mtime_ns
    rec2 = write_vintage(vdir, "SPY", "1d", df.copy(), provider="test", vintage_date="2026-10-21")
    assert rec2.written is False and rec2.sha256 == rec.sha256
    assert path.stat().st_mtime_ns == mtime
    manifest = load_manifest(vdir)
    files = manifest["vintages"]["2026-10-21"]["files"]
    assert len(files) == 1
    assert files[0]["sha256"] == rec.sha256 and files[0]["provider"] == "test"
    assert manifest["vintages"]["2026-10-21"]["dataset_hash"] == dataset_hash_from_files([rec.sha256])
    assert "created_at_utc" in manifest["vintages"]["2026-10-21"]


def test_write_vintage_overwrite_same_day_records_superseded(tmp_path: Any, caplog: Any) -> None:
    vdir = str(tmp_path / "vint")
    a = write_vintage(vdir, "SPY", "1d", _df(30), provider="test", vintage_date="2026-10-21")
    with _ibtrader_logs(caplog):
        b = write_vintage(vdir, "SPY", "1d", _df(31), provider="test", vintage_date="2026-10-21")
    assert b.written and b.sha256 != a.sha256
    entry = load_manifest(vdir)["vintages"]["2026-10-21"]["files"][0]
    assert entry["sha256"] == b.sha256
    assert entry["superseded"] == [a.sha256]
    assert any("vintage_overwrite" in r.getMessage() for r in caplog.records)


def test_load_vintage_roundtrip_and_dataset_hash(tmp_path: Any) -> None:
    vdir = str(tmp_path / "vint")
    spy, qqq = _df(40), _df(40, base=300.0)
    r1 = write_vintage(vdir, "SPY", "1d", spy, provider="test", vintage_date="2026-10-20")
    r2 = write_vintage(vdir, "QQQ", "1d", qqq, provider="test", vintage_date="2026-10-20")
    write_vintage(vdir, "SPY", "1d", _df(41), provider="test", vintage_date="2026-10-21")
    assert list_vintages(vdir) == ["2026-10-20", "2026-10-21"]
    out = load_vintage(vdir, "2026-10-20")
    assert set(out) == {"SPY", "QQQ"}
    pd.testing.assert_frame_equal(out["SPY"], spy, check_freq=False)
    pd.testing.assert_frame_equal(out["QQQ"], qqq, check_freq=False)
    vint = load_manifest(vdir)["vintages"]["2026-10-20"]
    assert vint["dataset_hash"] == dataset_hash_from_files([r1.sha256, r2.sha256])
    only = load_vintage(vdir, "2026-10-20", symbols=["spy"])
    assert set(only) == {"SPY"}


def test_load_vintage_fails_loud_on_tamper_or_missing(tmp_path: Any) -> None:
    vdir = str(tmp_path / "vint")
    write_vintage(vdir, "SPY", "1d", _df(20), provider="test", vintage_date="2026-10-21")
    write_vintage(vdir, "QQQ", "1d", _df(20, base=50.0), provider="test", vintage_date="2026-10-21")
    path = vintage_file_path(vdir, "2026-10-21", "SPY", "1d")
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(RuntimeError, match="sha256 no coincide"):
        load_vintage(vdir, "2026-10-21")
    with pytest.raises(RuntimeError, match="no existe"):
        load_vintage(vdir, "1999-01-01")
    with pytest.raises(RuntimeError, match="sin entrada"):
        load_vintage(vdir, "2026-10-21", symbols=["QQQ", "IWM"])


def test_write_vintage_rejects_empty_or_bad_date(tmp_path: Any) -> None:
    with pytest.raises(ValueError):
        write_vintage(str(tmp_path), "SPY", "1d", pd.DataFrame(), provider="t")
    with pytest.raises(ValueError):
        write_vintage(str(tmp_path), "SPY", "1d", _df(3), provider="t", vintage_date="21-10-2026")


# ----------------------------------------------------------------------------------------
# service.py: fail-loud orchestration
# ----------------------------------------------------------------------------------------


class _Prov(prov_mod.MarketDataProvider):
    """Returns a frame per symbol; a symbol mapped to an Exception raises it."""

    def __init__(self, frames: dict, source: str = "yahoo") -> None:
        self.frames = frames
        self.source = source
        self.calls: List[str] = []

    def fetch_daily_ohlcv(self, symbol: str, start: Optional[str] = None, end: Optional[str] = None):
        self.calls.append(symbol)
        item = self.frames[symbol]
        if isinstance(item, Exception):
            raise item
        return prov_mod.DataFrameWithMeta(item, prov_mod.DataLineage(source=self.source, methodology="test"))


def _settings(tmp_path: Any, monkeypatch: Any, symbols: List[str]) -> Any:
    from ibtrader.config import AppSettings

    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    s = AppSettings()
    s.resolve_paths()
    s.data.providers = ["yahoo"]
    s.universe.symbols = list(symbols)
    return s


def _good(rows: int = 260) -> pd.DataFrame:
    return _df(rows, end=str(datetime.now(timezone.utc).date()))


def test_service_writes_vintage_and_lineage(tmp_path: Any, monkeypatch: Any) -> None:
    good = _good()
    prov = _Prov({"SPY": good})
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: prov)
    s = _settings(tmp_path, monkeypatch, ["SPY"])
    out = svc_mod.load_universe_v2(s)
    assert set(out) == {"SPY"}
    today = str(datetime.now(timezone.utc).date())
    meta = load_lineage(s.data.cache_dir, "SPY", "1d")
    assert meta is not None
    assert meta.vintage_date == today
    assert meta.vintage_path == f"vintage_date={today}/SPY_1d.parquet"
    manifest = load_manifest(s.data.vintage_dir)
    entry = manifest["vintages"][today]["files"][0]
    assert entry["sha256"] == meta.sha256 and entry["provider"] == "yahoo" and entry["rows"] == 260
    snap = load_vintage(s.data.vintage_dir, today)
    pd.testing.assert_frame_equal(snap["SPY"], good, check_freq=False)
    # second load is served from cache, nothing refetched, vintage untouched
    out2 = svc_mod.load_universe_v2(s)
    assert len(out2["SPY"]) == 260 and prov.calls == ["SPY"]


def test_service_write_manifest_false_skips_vintage(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: _Prov({"SPY": _good()}))
    s = _settings(tmp_path, monkeypatch, ["SPY"])
    s.data.write_manifest = False
    svc_mod.load_universe_v2(s)
    assert not (tmp_path / "vintages").exists()
    meta = load_lineage(s.data.cache_dir, "SPY", "1d")
    assert meta is not None and meta.vintage_date is None and meta.sha256 is None


def test_service_fixture_provider_never_enters_vintage_store(tmp_path: Any, monkeypatch: Any, caplog: Any) -> None:
    """Synthetic CI data must not overwrite the real snapshot of the same day (write_manifest stays True)."""
    monkeypatch.setenv("DATA__FIXTURE_DIR", "./tests/fixtures")
    s = _settings(tmp_path, monkeypatch, ["SPY"])
    s.data.providers = ["fixture"]
    with _ibtrader_logs(caplog):
        out = svc_mod.load_universe_v2(s)
    assert "SPY" in out
    assert not (tmp_path / "vintages").exists()
    assert any("vintage_skipped symbol=SPY source=fixture" in r.getMessage() for r in caplog.records)
    meta = load_lineage(s.data.cache_dir, "SPY", "1d")
    assert meta is not None and meta.source == "fixture" and meta.vintage_date is None


def test_service_excludes_bad_symbol_and_never_caches_it(tmp_path: Any, monkeypatch: Any, caplog: Any) -> None:
    future = _df(260, start="2099-01-01")
    spiky = _good()
    spiky.iloc[100, spiky.columns.get_loc("close")] = spiky["close"].iloc[99] * 3
    prov = _Prov({"SPY": _good(), "FUT": future, "SPK": spiky})
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: prov)
    s = _settings(tmp_path, monkeypatch, ["SPY", "FUT", "SPK"])
    with _ibtrader_logs(caplog):
        out = svc_mod.load_universe_v2(s)
    assert set(out) == {"SPY"}
    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("symbol_excluido symbol=FUT" in m and "futura" in m for m in msgs)
    assert any("symbol_excluido symbol=SPK" in m and "saltos de cierre" in m for m in msgs)
    assert any("universe_parcial" in m for m in msgs)
    # nothing invalid reached the cache or the vintage
    assert cache_path(s.data.cache_dir, "SPY", "1d").exists()
    assert not cache_path(s.data.cache_dir, "FUT", "1d").exists()
    assert not cache_path(s.data.cache_dir, "SPK", "1d").exists()
    today = str(datetime.now(timezone.utc).date())
    assert [f["symbol"] for f in load_manifest(s.data.vintage_dir)["vintages"][today]["files"]] == ["SPY"]


def test_service_raises_when_no_symbol_loads(tmp_path: Any, monkeypatch: Any) -> None:
    prov = _Prov({"SPY": RuntimeError("yfinance vacío"), "QQQ": _df(260, start="2099-01-01")})
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: prov)
    s = _settings(tmp_path, monkeypatch, ["SPY", "QQQ"])
    with pytest.raises(RuntimeError) as ei:
        svc_mod.load_universe_v2(s)
    msg = str(ei.value)
    assert "Ningún símbolo cargó (2 fallaron)" in msg
    assert "SPY: yahoo: RuntimeError: yfinance vacío" in msg
    assert "QQQ:" in msg and "futura" in msg
    assert not (tmp_path / "vintages" / "manifest.json").exists()


def test_service_provider_chain_aggregates_reasons(tmp_path: Any, monkeypatch: Any) -> None:
    first = _Prov({"SPY": RuntimeError("timeout")}, source="yahoo")
    second = _Prov({"SPY": _df(10, end=str(datetime.now(timezone.utc).date()))}, source="stooq")  # too short
    third = _Prov({"SPY": _good()}, source="ibkr")
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: first)
    monkeypatch.setattr(svc_mod, "StooqProvider", lambda: second)
    monkeypatch.setattr(svc_mod, "IBKRProvider", lambda **kw: third)
    s = _settings(tmp_path, monkeypatch, ["SPY"])
    s.data.providers = ["yahoo", "stooq", "ibkr"]
    out = svc_mod.load_universe_v2(s)
    assert len(out["SPY"]) == 260
    meta = load_lineage(s.data.cache_dir, "SPY", "1d")
    assert meta is not None and meta.source == "ibkr"
    # same chain without the working provider => exception carries both reasons
    s.data.providers = ["yahoo", "stooq"]
    s.engine.use_cache = False
    with pytest.raises(RuntimeError) as ei:
        svc_mod.load_universe_v2(s)
    msg = str(ei.value)
    assert "yahoo: RuntimeError: timeout" in msg
    assert "stooq:" in msg and "insuficiente" in msg


def test_service_rejects_unusable_provider_list(tmp_path: Any, monkeypatch: Any) -> None:
    s = _settings(tmp_path, monkeypatch, ["SPY"])
    s.data.providers = ["nope", "tiingo"]
    s.data.tiingo_token = ""
    with pytest.raises(RuntimeError, match="Ningún proveedor"):
        svc_mod.load_universe_v2(s)


def test_service_cache_rejected_when_lineage_missing(tmp_path: Any, monkeypatch: Any, caplog: Any) -> None:
    from ibtrader.data.cache import save_to_cache

    good = _good()
    s = _settings(tmp_path, monkeypatch, ["SPY"])
    save_to_cache(s.data.cache_dir, "SPY", "1d", good)  # parquet without .meta.json sidecar
    prov = _Prov({"SPY": good})
    monkeypatch.setattr(svc_mod, "YahooProvider", lambda: prov)
    with _ibtrader_logs(caplog):
        out = svc_mod.load_universe_v2(s)
    assert "SPY" in out and prov.calls == ["SPY"]
    assert any("cache_rechazada" in r.getMessage() and "sin linaje" in r.getMessage() for r in caplog.records)
