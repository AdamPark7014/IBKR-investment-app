from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd
import pytest
import requests

import ibtrader.data.service as svc_mod
from ibtrader.data.providers import SymbolMetadata, TiingoProvider
from ibtrader.data.vintage import load_manifest

# ----------------------------------------------------------------------------------------
# Fakes (no network: requests.get is monkeypatched in every test)
# ----------------------------------------------------------------------------------------


class _Resp:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        text: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("sin JSON")
        return self._payload


class _FakeGet:
    """Queue of responses (or callables / exceptions) returned in order; records every call."""

    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, url: str, params: Any = None, headers: Any = None, timeout: Any = None, **kw: Any) -> Any:
        self.calls.append({"url": url, "params": dict(params or {}), "headers": headers, "timeout": timeout})
        assert self.responses, "la prueba pidió más llamadas de las previstas"
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _tiingo_rows(n: int = 5, start: str = "2024-01-02", end: Optional[str] = None) -> List[Dict[str, Any]]:
    idx = pd.bdate_range(end=end, periods=n) if end else pd.bdate_range(start, periods=n)
    rows: List[Dict[str, Any]] = []
    for i, d in enumerate(idx):
        adj = 100.0 + i
        rows.append(
            {
                "date": d.strftime("%Y-%m-%dT00:00:00.000Z"),
                "open": adj * 2,
                "high": adj * 2 + 1,
                "low": adj * 2 - 1,
                "close": adj * 2,
                "volume": 1000 + i,
                "adjOpen": adj,
                "adjHigh": adj + 1,
                "adjLow": adj - 1,
                "adjClose": adj,
                "adjVolume": 2000 + i,
                "divCash": 0.0,
                "splitFactor": 1.0,
            }
        )
    return rows


def _provider(sleeps: Optional[List[float]] = None, **kw: Any) -> TiingoProvider:
    rec = sleeps if sleeps is not None else []
    return TiingoProvider("t0k-secret", sleep=lambda s: rec.append(s), **kw)


@contextmanager
def _ibtrader_logs(caplog: Any) -> Iterator[None]:
    """setup_logging() sets propagate=False on 'ibtrader'; attach caplog's handler there explicitly."""
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
# Provider
# ----------------------------------------------------------------------------------------


def test_fetch_maps_adjusted_columns_and_keeps_raw(monkeypatch: Any) -> None:
    fake = _FakeGet([_Resp(200, _tiingo_rows(5))])
    monkeypatch.setattr(requests, "get", fake)
    out = _provider().fetch_daily_ohlcv("spy", start="2024-01-01", end="2024-01-10")
    df = out.data
    assert {"open", "high", "low", "close", "volume", "adj_close", "close_raw", "div_cash", "split_factor"} <= set(
        df.columns
    )
    # adjusted series drive open/high/low/close/volume; raw close survives as close_raw
    assert df["close"].iloc[0] == 100.0
    assert df["close_raw"].iloc[0] == 200.0
    assert df["adj_close"].equals(df["close"])
    assert df["volume"].iloc[0] == 2000.0
    assert df.index.name == "date"
    assert df.index.tz is None
    assert df.index.is_monotonic_increasing and not df.index.has_duplicates
    assert str(df.index[0].date()) == "2024-01-02"
    # lineage: source tiingo, token never leaks
    assert out.lineage.source == "tiingo"
    assert "t0k-secret" not in json.dumps(out.lineage.to_dict())
    assert out.lineage.source_url == "https://api.tiingo.com/tiingo/daily/SPY/prices"
    call = fake.calls[0]
    assert call["url"] == "https://api.tiingo.com/tiingo/daily/SPY/prices"
    assert call["params"]["startDate"] == "2024-01-01"
    assert call["params"]["endDate"] == "2024-01-10"
    assert call["params"]["format"] == "json"
    assert call["params"]["token"] == "t0k-secret"


def test_fallback_to_raw_columns_when_adjusted_missing(monkeypatch: Any) -> None:
    rows = _tiingo_rows(3)
    for r in rows:
        for k in ("adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume"):
            r.pop(k)
    monkeypatch.setattr(requests, "get", _FakeGet([_Resp(200, rows)]))
    out = _provider().fetch_daily_ohlcv("SPY")
    assert out.data["close"].iloc[0] == 200.0
    assert out.data["close_raw"].iloc[0] == 200.0


def test_429_backoff_then_success(monkeypatch: Any) -> None:
    fake = _FakeGet([_Resp(429, text="rate"), _Resp(429, text="rate"), _Resp(200, _tiingo_rows(3))])
    monkeypatch.setattr(requests, "get", fake)
    sleeps: List[float] = []
    out = _provider(sleeps, backoff_s=2.0).fetch_daily_ohlcv("SPY")
    assert len(out.data) == 3
    assert sleeps == [2.0, 4.0]
    assert len(fake.calls) == 3


def test_429_respects_retry_after_header(monkeypatch: Any) -> None:
    fake = _FakeGet([_Resp(429, headers={"Retry-After": "7"}), _Resp(200, _tiingo_rows(2))])
    monkeypatch.setattr(requests, "get", fake)
    sleeps: List[float] = []
    _provider(sleeps).fetch_daily_ohlcv("SPY")
    assert sleeps == [7.0]


def test_429_gives_up_after_three_retries(monkeypatch: Any) -> None:
    fake = _FakeGet([_Resp(429)] * 4)
    monkeypatch.setattr(requests, "get", fake)
    sleeps: List[float] = []
    with pytest.raises(RuntimeError, match="429"):
        _provider(sleeps, max_retries=3).fetch_daily_ohlcv("SPY")
    assert len(sleeps) == 3
    assert len(fake.calls) == 4


@pytest.mark.parametrize("status", [401, 403])
def test_bad_token_fails_with_clear_message(monkeypatch: Any, status: int) -> None:
    monkeypatch.setattr(requests, "get", _FakeGet([_Resp(status, text="Unauthorized")]))
    with pytest.raises(RuntimeError, match="token Tiingo inválido o ausente"):
        _provider().fetch_daily_ohlcv("SPY")


def test_404_unknown_symbol(monkeypatch: Any) -> None:
    monkeypatch.setattr(requests, "get", _FakeGet([_Resp(404, text="Not found")]))
    with pytest.raises(RuntimeError, match="404"):
        _provider().fetch_daily_ohlcv("ZZZZ")


def test_empty_payload_is_an_error(monkeypatch: Any) -> None:
    monkeypatch.setattr(requests, "get", _FakeGet([_Resp(200, [])]))
    with pytest.raises(RuntimeError, match="vacío"):
        _provider().fetch_daily_ohlcv("SPY")


def test_network_error_is_not_swallowed(monkeypatch: Any) -> None:
    monkeypatch.setattr(requests, "get", _FakeGet([requests.ConnectionError("dns down")]))
    with pytest.raises(RuntimeError, match="error de red"):
        _provider().fetch_daily_ohlcv("SPY")


def test_duplicate_dates_rejected(monkeypatch: Any) -> None:
    rows = _tiingo_rows(3)
    rows.append(dict(rows[-1]))
    monkeypatch.setattr(requests, "get", _FakeGet([_Resp(200, rows)]))
    with pytest.raises(RuntimeError, match="inválida"):
        _provider().fetch_daily_ohlcv("SPY")


def test_empty_token_rejected() -> None:
    with pytest.raises(ValueError, match="token Tiingo inválido o ausente"):
        TiingoProvider("")
    with pytest.raises(ValueError):
        TiingoProvider("   ")


def test_fetch_metadata_exposes_listing_dates(monkeypatch: Any) -> None:
    payload = {
        "ticker": "spy",
        "name": "SPDR S&P 500 ETF Trust",
        "exchangeCode": "NYSE ARCA",
        "startDate": "1993-01-29T00:00:00.000Z",
        "endDate": "2026-10-20T00:00:00.000Z",
        "description": "...",
    }
    fake = _FakeGet([_Resp(200, payload)])
    monkeypatch.setattr(requests, "get", fake)
    meta = _provider().fetch_metadata("spy")
    assert isinstance(meta, SymbolMetadata)
    assert meta.symbol == "SPY"
    assert meta.start_date == "1993-01-29"
    assert meta.end_date == "2026-10-20"
    assert meta.exchange == "NYSE ARCA"
    assert fake.calls[0]["url"] == "https://api.tiingo.com/tiingo/daily/SPY"


# ----------------------------------------------------------------------------------------
# Registration in service.py
# ----------------------------------------------------------------------------------------


def _settings(tmp_path: Any, monkeypatch: Any) -> Any:
    from ibtrader.config import AppSettings

    monkeypatch.setenv("DATA__CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DATA__VINTAGE_DIR", str(tmp_path / "vintages"))
    s = AppSettings()
    s.resolve_paths()
    return s


def test_service_skips_tiingo_without_token(tmp_path: Any, monkeypatch: Any, caplog: Any) -> None:
    s = _settings(tmp_path, monkeypatch)
    s.data.providers = ["tiingo", "fixture"]
    s.data.tiingo_token = ""
    with _ibtrader_logs(caplog):
        chain = svc_mod.build_provider_chain(s)
    assert [name for name, _ in chain] == ["fixture"]
    assert any("tiingo_disabled" in r.getMessage() for r in caplog.records)


def test_service_registers_tiingo_with_token(tmp_path: Any, monkeypatch: Any) -> None:
    s = _settings(tmp_path, monkeypatch)
    s.data.providers = ["tiingo", "yahoo"]
    s.data.tiingo_token = "abc"
    chain = svc_mod.build_provider_chain(s)
    assert [name for name, _ in chain] == ["tiingo", "yahoo"]
    assert isinstance(chain[0][1], TiingoProvider)


def test_service_loads_universe_through_tiingo(tmp_path: Any, monkeypatch: Any) -> None:
    today = datetime.now(timezone.utc).date()
    rows = _tiingo_rows(260, end=str(today))
    monkeypatch.setattr(requests, "get", _FakeGet([_Resp(200, rows)]))
    s = _settings(tmp_path, monkeypatch)
    s.data.providers = ["tiingo"]
    s.data.tiingo_token = "abc"
    s.universe.symbols = ["SPY"]
    out = svc_mod.load_universe_v2(s)
    assert "SPY" in out and len(out["SPY"]) == 260
    # lineage sidecar + vintage manifest both say tiingo
    from ibtrader.data.cache import load_lineage

    meta = load_lineage(s.data.cache_dir, "SPY", s.engine.bar_size)
    assert meta is not None and meta.source == "tiingo"
    assert meta.vintage_date == str(today) and meta.sha256
    manifest = load_manifest(s.data.vintage_dir)
    files = manifest["vintages"][str(today)]["files"]
    assert files[0]["symbol"] == "SPY" and files[0]["provider"] == "tiingo"
    assert files[0]["sha256"] == meta.sha256
