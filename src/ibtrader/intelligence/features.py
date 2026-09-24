from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    up = (delta.where(delta > 0, 0)).rolling(window).mean()
    down = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = up / (down.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    h_l = (high - low).abs()
    h_pc = (high - close.shift()).abs()
    l_pc = (low - close.shift()).abs()
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    return tr.rolling(window, min_periods=window).mean()


def volume_zscore(volume: pd.Series, window: int = 20) -> pd.Series:
    mean = volume.rolling(window).mean()
    std = volume.rolling(window).std(ddof=0).replace(0, np.nan)
    z = (volume - mean) / std
    return z.fillna(0.0)


def support_resistance(close: pd.Series, window: int = 20) -> pd.DataFrame:
    sup = close.rolling(window).min()
    res = close.rolling(window).max()
    return pd.DataFrame({"support": sup, "resistance": res})


@dataclass
class FeatureSpec:
    include_rsi: bool = True
    include_sma: Optional[List[int]] = None  # e.g., [10, 30, 100, 200]
    include_ema: Optional[List[int]] = None
    atr_window: int = 14
    bb_window: int = 20
    volume_window: int = 20

    def __post_init__(self) -> None:
        if self.include_sma is None:
            self.include_sma = [10, 30, 100, 200]
        if self.include_ema is None:
            self.include_ema = [12, 26]


def build_features(
    data: Dict[str, pd.DataFrame], spec: FeatureSpec | None = None
) -> Dict[str, pd.DataFrame]:
    if spec is None:
        spec = FeatureSpec()
    features: Dict[str, pd.DataFrame] = {}
    for sym, df in data.items():
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        vol = df["volume"].astype(float)
        feat = pd.DataFrame(index=df.index)
        # Trend / momentum
        for w in (spec.include_sma or []):
            feat[f"sma_{w}"] = sma(close, w)
        for w in (spec.include_ema or []):
            feat[f"ema_{w}"] = ema(close, w)
        feat["mom_20"] = close.pct_change(20)
        feat["mom_60"] = close.pct_change(60)
        if spec.include_rsi:
            feat["rsi_14"] = rsi(close, 14)
        # Volatility
        feat["atr_14"] = atr(high, low, close, spec.atr_window)
        feat["vol_20"] = close.pct_change().rolling(20).std(ddof=0)
        # Volume
        feat["vol_z_20"] = volume_zscore(vol, spec.volume_window)
        # Support / resistance proximity
        sr = support_resistance(close, 20)
        feat["dist_to_support"] = (close - sr["support"]) / close
        feat["dist_to_resistance"] = (sr["resistance"] - close) / close
        # Normalize some ratios
        for w in [10, 30, 100, 200]:
            if f"sma_{w}" in feat:
                feat[f"price_over_sma_{w}"] = close / feat[f"sma_{w}"] - 1.0
        features[sym] = feat
    return features

