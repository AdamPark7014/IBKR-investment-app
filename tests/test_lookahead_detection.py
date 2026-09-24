from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.strategy.sma_crossover import SMACrossover


def test_naive_same_bar_vs_next_open_diff() -> None:
    # Build simple price series
    idx = pd.bdate_range("2024-01-01", periods=120)
    close = pd.Series(100.0 + (np.sin(np.linspace(0, 10, len(idx))) * 2.0) + 0.1 * np.arange(len(idx)), index=idx).astype(float)
    open_px = close.copy()
    df = pd.DataFrame({"open": open_px, "high": close, "low": close, "close": close, "volume": 1000.0}, index=idx)
    base = SMACrossover(5, 20, allow_short=True)
    sig = base.generate_signals({"SPY": df})["SPY"].reindex(idx).fillna(0)
    # Proper next-open returns
    next_open_rets = df["open"].pct_change().fillna(0.0)
    ret_proper = (sig.shift(1).fillna(0) * next_open_rets).mean()
    # Naive same-bar (look-ahead) using close-to-close at time t
    same_bar_rets = df["close"].pct_change().fillna(0.0)
    ret_lookahead = (sig * same_bar_rets).mean()
    # Look-ahead typically overstates performance
    assert ret_lookahead >= ret_proper - 1e-12

