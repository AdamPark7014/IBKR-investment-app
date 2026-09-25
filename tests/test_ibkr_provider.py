from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List

import pandas as pd

from ibtrader.data.providers import IBKRProvider


class _Bar:
    def __init__(self, dt: datetime, o: float, h: float, lo: float, c: float, v: float) -> None:
        self.date = dt
        self.open = o
        self.high = h
        self.low = lo
        self.close = c
        self.volume = v


class _FakeIB:
    def __init__(self) -> None:
        self.connected = False
        self.args: list[Any] = []

    def connect(self, host: str, port: int, clientId: int, readonly: bool, timeout: int) -> None:
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert isinstance(clientId, int)
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def reqHistoricalData(
        self,
        contract: Any,
        endDateTime: str,
        durationStr: str,
        barSizeSetting: str,
        whatToShow: str,
        useRTH: bool,
    ) -> List[_Bar]:
        # Return a small deterministic series
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=4)
        days = pd.date_range(start=start.date(), end=end.date(), freq="D")
        out: List[_Bar] = []
        price = 100.0
        for i, d in enumerate(days):
            price += 1.0
            out.append(_Bar(pd.Timestamp(d).to_pydatetime(), price, price + 1, price - 1, price, 1000))
        return out


class _FakeStock:
    def __init__(self, symbol: str, exchange: str, currency: str) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency


def test_ibkr_provider_fetch_historical(monkeypatch: Any) -> None:
    # Monkeypatch providers.IB and providers.Stock to fakes
    import ibtrader.data.providers as providers

    monkeypatch.setattr(providers, "IB", _FakeIB)
    monkeypatch.setattr(providers, "Stock", _FakeStock)

    prov = IBKRProvider(host="127.0.0.1", port=4002, client_id=999)
    out = prov.fetch_daily_ohlcv("SPY")
    assert set(out.data.columns) == {"open", "high", "low", "close", "volume"}
    assert len(out.data) >= 3
    # Strictly increasing index, no duplicates
    assert out.data.index.is_monotonic_increasing
    assert not out.data.index.has_duplicates
