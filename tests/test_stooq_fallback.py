from __future__ import annotations

from typing import Any

from ibtrader.data.providers import StooqProvider


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_stooq_fallback_parses_csv(monkeypatch: Any) -> None:
    csv = (
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,1,2,0.5,1.5,1000\n"
        "2024-01-03,1.1,2.1,0.6,1.6,1100\n"
    )

    def fake_get(url: str, timeout: int, headers: dict, allow_redirects: bool) -> _Resp:
        return _Resp(200, csv)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    prov = StooqProvider()
    out = prov.fetch_daily_ohlcv("SPY")
    assert set(out.data.columns) == {"open", "high", "low", "close", "volume"}
    assert len(out.data) == 2
