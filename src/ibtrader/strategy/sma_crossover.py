from __future__ import annotations

from typing import Dict

import pandas as pd

from .base import Strategy


class SMACrossover(Strategy):
    def __init__(self, fast_window: int = 10, slow_window: int = 30) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be < slow_window")
        self.fast = fast_window
        self.slow = slow_window

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        for sym, df in data.items():
            prices = df["close"].astype(float)
            ma_fast = prices.rolling(self.fast).mean()
            ma_slow = prices.rolling(self.slow).mean()
            signal = (ma_fast > ma_slow).astype(int) - (ma_fast < ma_slow).astype(int)
            signal = signal.fillna(0).astype(int)
            out[sym] = signal
        return out

