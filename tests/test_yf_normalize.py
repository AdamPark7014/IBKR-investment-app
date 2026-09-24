from __future__ import annotations

import pandas as pd

from ibtrader.data.downloader import normalize_yf


def test_normalize_yf_flattens_multiindex() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    cols = pd.MultiIndex.from_tuples(
        [
            ("Open", "SPY"),
            ("High", "SPY"),
            ("Low", "SPY"),
            ("Close", "SPY"),
            ("Adj Close", "SPY"),
            ("Volume", "SPY"),
        ]
    )
    df = pd.DataFrame([[1, 2, 0.5, 1.5, 1.4, 1000]] * 3, index=idx, columns=cols)
    out = normalize_yf(df)
    assert {"open", "high", "low", "close", "adj_close", "volume"}.issubset(set(out.columns))
