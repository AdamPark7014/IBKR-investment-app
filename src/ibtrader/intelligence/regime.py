from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from ..config import DataConfig, EngineConfig, UniverseConfig


def compute_breadth(universe_data: Dict[str, pd.DataFrame], long_ma: int = 200) -> pd.Series:
    idx = sorted(set().union(*[df.index for df in universe_data.values()]))
    breadth = pd.Series(0.0, index=idx)
    for dt in idx:
        count = 0
        above = 0
        for df in universe_data.values():
            if dt not in df.index:
                continue
            close = df.loc[dt, "close"]
            ma = df["close"].rolling(long_ma).mean().reindex([dt]).iloc[0]
            if not np.isnan(close) and not np.isnan(ma):
                count += 1
                if close > ma:
                    above += 1
        breadth.loc[dt] = (above / count) if count else np.nan
    return breadth.fillna(method="ffill").fillna(0.0)


def vix_risk_on_off(vix_df: pd.DataFrame) -> pd.Series:
    vix_close = vix_df["close"].astype(float)
    vix_ma = vix_close.rolling(50).mean()
    # Risk-on when VIX below its 50d MA
    regime = (vix_close < vix_ma).astype(int)  # 1 risk-on, 0 risk-off
    return regime.reindex(vix_close.index).fillna(0)


def detect_regime(
    universe: UniverseConfig,
    engine: EngineConfig,
    data_cfg: DataConfig,
    universe_data: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Returns a DataFrame with columns:
    - breadth: fraction above MA
    - risk_on: 1/0 from VIX rule
    - trend: 1 trending, 0 ranging (simple ADX-like proxy using volatility contraction/expansion)
    """
    # Breadth
    breadth = compute_breadth(universe_data, long_ma=200)
    # VIX (si está disponible en universe_data). Si no, fallback sin red.
    if "^VIX" in universe_data:
        vix = universe_data["^VIX"]
        risk_on = vix_risk_on_off(vix).reindex(breadth.index).fillna(method="ffill").fillna(0)
    else:
        risk_on = pd.Series(1, index=breadth.index, dtype=int)  # fallback conservador
    # Trend proxy: when rolling std of returns is rising and price above 100d MA => trend
    bench = universe.benchmark or "SPY"
    bench_df = universe_data.get(bench)
    if bench_df is None:
        # Fallback: usa el primer símbolo disponible para derivar un proxy de tendencia
        any_sym = next(iter(universe_data.keys()))
        bench_df = universe_data[any_sym]
    close = bench_df["close"].astype(float).reindex(breadth.index).fillna(method="ffill")
    rets = close.pct_change()
    vol = rets.rolling(20).std(ddof=0)
    vol_slope = vol.diff(5)
    ma100 = close.rolling(100).mean()
    trend = ((vol_slope > 0) & (close > ma100)).astype(int)
    return pd.DataFrame(
        {
            "breadth": breadth,
            "risk_on": risk_on,
            "trend": trend,
        }
    ).fillna(0)

