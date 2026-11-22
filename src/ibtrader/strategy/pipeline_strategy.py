"""Weight-mode strategy that wraps the phase-2 stage graph (``pipeline/system.py``)."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from ..pipeline.rules import carry_forecast
from ..pipeline.system import SystemConfig, SystemOutput, run_system
from ..pipeline.vol import pct_vol_daily
from .base import Strategy


class PipelineStrategy(Strategy):
    """Run ``run_system`` over the closes and hand the engine signed target weights.

    ``signal_kind = "weight"``: the engine reads each series as a target weight
    (fraction of NAV) already sized by the volatility target and buffered, and only
    trades when the weight changes. Weights are 0.0 before ``warmup_end`` (no stage
    is trusted until every stage has a value for at least two symbols) and NaN
    stages map to 0.0 (flat), never to an implicit position.

    ``last_output`` keeps the full ``SystemOutput`` of the last call so research
    can read ``warmup_end`` and every intermediate stage.
    """

    signal_kind = "weight"

    def __init__(self, cfg: Optional[SystemConfig] = None) -> None:
        self.cfg = cfg if cfg is not None else SystemConfig()
        self.last_output: Optional[SystemOutput] = None

    @staticmethod
    def close_frame(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Closes as a (dates × symbols) frame on the union of the symbol indexes."""
        closes = {sym: df["close"].astype(float) for sym, df in data.items()}
        frame = pd.DataFrame(closes)
        frame.index = pd.DatetimeIndex(frame.index)
        return frame.sort_index()

    def extra_raw(self, data: Dict[str, pd.DataFrame]) -> Optional[Dict[str, pd.DataFrame]]:
        """Pronósticos brutos de las reglas externas (carry), calculados con los repartos de ``data``."""
        if "carry_12m" not in self.cfg.rules:
            return None
        missing = [s for s, df in data.items() if "div_cash" not in df.columns or "close_raw" not in df.columns]
        if missing:
            raise ValueError(f"carry_12m necesita div_cash y close_raw; faltan en: {sorted(missing)}")
        cash = self.cfg.cash_symbols(sorted(data))
        idx = {s: pd.DatetimeIndex(df.index) for s, df in data.items()}
        return {"carry_12m": carry_forecast(
            {s: pd.Series(df["div_cash"].to_numpy(dtype=float), index=idx[s]) for s, df in data.items()},
            {s: pd.Series(df["close_raw"].to_numpy(dtype=float), index=idx[s]) for s, df in data.items()},
            {s: pct_vol_daily(pd.Series(df["close"].to_numpy(dtype=float), index=idx[s]), span=self.cfg.vol_span)
             for s, df in data.items()},
            cash_symbol=cash[0] if cash else None,
        )}

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if not data:
            return {}
        prices = self.close_frame(data)
        out = run_system(prices, self.cfg, self.extra_raw(data))
        self.last_output = out
        signals: Dict[str, pd.Series] = {}
        for sym, df in data.items():
            idx = pd.DatetimeIndex(df.index)
            if sym in out.target_weights.columns:
                w = out.target_weights[sym].reindex(idx)
            else:
                w = pd.Series(0.0, index=idx)
            if out.warmup_end is not None:
                w = w.where(idx >= out.warmup_end, 0.0)
            else:
                w = pd.Series(0.0, index=idx)
            signals[sym] = w.fillna(0.0).astype(float)
        return signals


__all__ = ["PipelineStrategy"]
