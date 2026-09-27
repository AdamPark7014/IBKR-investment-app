from __future__ import annotations

from typing import Dict

import pandas as pd

from .base import Strategy


class TimeSeriesMomentum(Strategy):
    """Simple time-series momentum (research candidate).

    Signal at t uses only close[t - lookback] .. close[t] (no future).
    Long if lookback return > 0, short if < 0 (when allow_short), else flat.
    """

    def __init__(self, lookback: int = 21, allow_short: bool = True) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        self.lookback = int(lookback)
        self.allow_short = bool(allow_short)

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        for sym, df in data.items():
            prices = df["close"].astype(float)
            # Return over lookback bars ending at t (point-in-time)
            ret = prices / prices.shift(self.lookback) - 1.0
            if self.allow_short:
                signal = (ret > 0).astype(int) - (ret < 0).astype(int)
            else:
                signal = (ret > 0).astype(int)
            # Warm-up: insufficient history → flat (0), not implicit risk-on
            signal = signal.where(ret.notna(), 0).fillna(0).astype(int)
            out[sym] = signal
        return out
