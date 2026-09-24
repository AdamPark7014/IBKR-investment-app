from __future__ import annotations

from typing import Dict

import pandas as pd

from .base import Strategy


class MeanReversion(Strategy):
    """
    Simple Bollinger-band mean reversion:
    - Long when price < lower band
    - Short when price > upper band
    """

    def __init__(self, window: int = 20, num_std: float = 2.0) -> None:
        self.window = window
        self.num_std = num_std

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        for sym, df in data.items():
            close = df["close"].astype(float)
            ma = close.rolling(self.window).mean()
            std = close.rolling(self.window).std(ddof=0)
            upper = ma + self.num_std * std
            lower = ma - self.num_std * std
            sig = (close < lower).astype(int) - (close > upper).astype(int)
            sig = sig.fillna(0).astype(int)
            out[sym] = sig
        return out

