"""Yahoo OHLC must be total-return adjusted (dividends/splits) before validation and caching."""

from __future__ import annotations

import pandas as pd

from ibtrader.data.providers import apply_total_return_adjustment


def _frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2021-12-01", "2021-12-02", "2021-12-03", "2021-12-06"])
    # PDBC-like: USD 5.39 distribution on 2021-12-03 drops the raw close 26.6 %; adj_close is flat.
    return pd.DataFrame(
        {
            "open": [20.0, 20.1, 14.9, 15.0],
            "high": [20.2, 20.3, 15.0, 15.2],
            "low": [19.9, 20.0, 14.8, 14.9],
            "close": [20.07, 20.29, 14.90, 15.16],
            "adj_close": [10.168, 10.280, 10.280, 10.459],
            "volume": [1000, 1000, 1000, 1000],
        },
        index=idx,
    )


def test_adjusted_close_has_no_spurious_drop() -> None:
    out = apply_total_return_adjustment(_frame())
    rets = out["close"].pct_change().dropna()
    assert rets.abs().max() < 0.05
    assert (out["close"] == out["adj_close"]).all()


def test_raw_close_kept_and_ohlc_scaled_by_same_factor() -> None:
    raw = _frame()
    out = apply_total_return_adjustment(raw)
    assert "close_raw" in out.columns
    assert out["close_raw"].tolist() == raw["close"].tolist()
    factor = raw["adj_close"] / raw["close"]
    for col in ("open", "high", "low"):
        pd.testing.assert_series_equal(out[col], raw[col] * factor, check_names=False)
    assert out["volume"].tolist() == raw["volume"].tolist()


def test_no_adj_close_is_a_noop() -> None:
    raw = _frame().drop(columns=["adj_close"])
    out = apply_total_return_adjustment(raw)
    pd.testing.assert_frame_equal(out, raw)
