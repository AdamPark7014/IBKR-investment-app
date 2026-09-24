from __future__ import annotations

from typing import Dict

import pandas as pd

from .base import Strategy


class CrossSectionalMomentum(Strategy):
    """
    Rank symbols by trailing return, hold top N equally.
    """

    def __init__(self, lookback_days: int = 60, top_n: int = 3) -> None:
        self.lookback = lookback_days
        self.top_n = top_n

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        # Align indexes
        all_idx = sorted(set().union(*[df.index for df in data.values()]))
        returns: Dict[str, pd.Series] = {}
        for sym, df in data.items():
            close = df["close"].astype(float)
            rets = close.pct_change(self.lookback)
            returns[sym] = rets.reindex(all_idx).fillna(method="ffill")
        out: Dict[str, pd.Series] = {}
        for dt in all_idx:
            ranks = sorted(
                ((sym, float(returns[sym].get(dt, 0.0))) for sym in data.keys()),
                key=lambda x: x[1],
                reverse=True,
            )
            top_syms = {sym for sym, _ in ranks[: self.top_n]}
            for sym in data.keys():
                sig_series = out.setdefault(sym, pd.Series(index=all_idx, dtype=int))
                sig_series.loc[dt] = 1 if sym in top_syms else 0
        # Ensure int dtype and fill nans
        for sym in out.keys():
            out[sym] = out[sym].fillna(0).astype(int)
        return out

