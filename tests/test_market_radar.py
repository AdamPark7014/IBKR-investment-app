from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.intelligence.market_radar import DISCLAIMER, build_market_radar


def _ohlc(n: int = 120, start: float = 100.0, drift: float = 0.001) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = start * np.cumprod(1.0 + np.full(n, drift))
    return pd.DataFrame({"close": close}, index=idx)


def test_build_market_radar_basic() -> None:
    prices = {
        "SPY": _ohlc(120, drift=0.002),
        "TLT": _ohlc(120, start=90.0, drift=-0.0005),
        "IEF": _ohlc(120, start=95.0, drift=0.0),
        "GLD": _ohlc(120, start=180.0, drift=0.001),
        "^VIX": _ohlc(120, start=20.0, drift=-0.001),
    }
    out = build_market_radar(prices)
    assert out["disclaimer"] == DISCLAIMER
    assert out["as_of"] is not None
    assert out["equity_trend"] in (-1, 0, 1)
    assert out["equity_vol_20"] is not None
    assert out["risk_on_proxy"] in (0, 1)
    assert out["rates_slope"] is not None
    assert out["commodity_momentum"] is not None
    assert 0.0 <= float(out["breadth_proxy"]) <= 1.0


def test_radar_respects_as_of() -> None:
    prices = {"SPY": _ohlc(150, drift=0.001)}
    mid = prices["SPY"].index[80]
    out = build_market_radar(prices, as_of=mid)
    assert out["as_of"] == mid.date().isoformat()
