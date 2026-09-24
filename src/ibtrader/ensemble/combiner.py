from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class EnsembleWeights:
    strategy_weights: Dict[str, float]
    feature_weights: Optional[Dict[str, float]] = None


def logistic(x: pd.Series, k: float = 5.0) -> pd.Series:
    return 1.0 / (1.0 + np.exp(-k * x))


def score_strategies(
    signals: Dict[str, Dict[str, pd.Series]], weights: EnsembleWeights
) -> Dict[str, pd.Series]:
    """
    signals: {symbol: {strategy_name: signal_series in [-1,0,1]}}
    Returns: {symbol: score in [-1,1]}
    """
    out: Dict[str, pd.Series] = {}
    for sym, strat_map in signals.items():
        idx = sorted(set().union(*[s.index for s in strat_map.values()]))
        total = pd.Series(0.0, index=idx)
        wsum = 0.0
        for name, sig in strat_map.items():
            w = weights.strategy_weights.get(name, 0.0)
            if w == 0:
                continue
            total = total.add(sig.reindex(idx).fillna(0.0) * w, fill_value=0.0)
            wsum += abs(w)
        if wsum == 0:
            out[sym] = pd.Series(0.0, index=idx)
        else:
            out[sym] = (total / wsum).clip(-1.0, 1.0)
    return out


def apply_regime_filter(
    scores: Dict[str, pd.Series], regime_df: pd.DataFrame
) -> Dict[str, pd.Series]:
    """
    Example: only allow long when risk_on=1, suppress signals when risk_off.
    """
    filtered: Dict[str, pd.Series] = {}
    regime = (
        regime_df["risk_on"]
        .reindex(next(iter(scores.values())).index)
        .fillna(method="ffill")
        .fillna(0)
    )
    for sym, sc in scores.items():
        s = sc.copy()
        s = s.where(~((regime == 0) & (s > 0)), 0.0)  # zero out long scores during risk-off
        filtered[sym] = s
    return filtered


def score_to_position(
    score: pd.Series, buy_threshold: float = 0.2, sell_threshold: float = -0.2
) -> pd.Series:
    pos = pd.Series(0, index=score.index, dtype=int)
    pos[score >= buy_threshold] = 1
    pos[score <= sell_threshold] = -1
    return pos


def trailing_stop_from_atr(
    close: pd.Series, atr_series: pd.Series, multiple: float = 3.0, side: str = "long"
) -> pd.Series:
    """
    Returns stop level series (price). For 'long', stop trails by ATR multiple below rolling max.
    """
    if side == "long":
        roll_max = close.cummax()
        stop = roll_max - multiple * atr_series
    else:
        roll_min = close.cummin()
        stop = roll_min + multiple * atr_series
    return stop


def enforce_stops(
    position: pd.Series,
    close: pd.Series,
    atr_series: pd.Series,
    atr_multiple: float = 3.0,
) -> pd.Series:
    """
    Converts desired position to effective position based on ATR trailing stops.
    """
    stop_long = trailing_stop_from_atr(close, atr_series, atr_multiple, side="long")
    stop_short = trailing_stop_from_atr(close, atr_series, atr_multiple, side="short")
    effective = position.copy().astype(int)
    in_pos = 0
    for i in range(len(position)):
        p = int(position.iloc[i])
        price = float(close.iloc[i])
        if p > 0:
            in_pos = 1 if in_pos >= 0 else 1  # long
            if price < float(stop_long.iloc[i]):
                in_pos = 0
        elif p < 0:
            in_pos = -1 if in_pos <= 0 else -1  # short
            if price > float(stop_short.iloc[i]):
                in_pos = 0
        else:
            in_pos = 0
        effective.iloc[i] = in_pos
    return effective

