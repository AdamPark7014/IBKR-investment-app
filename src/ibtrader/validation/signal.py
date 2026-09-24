from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ..ml.cv import PurgedTimeSeriesSplit
from ..strategy.sma_crossover import SMACrossover


def _forward_returns(close: pd.Series, horizon: int = 1) -> pd.Series:
    return close.pct_change(periods=horizon).shift(-horizon).fillna(0.0)


@dataclass
class CVFoldResult:
    mean_ret: float
    sharpe: float
    n_obs: int


def validate_sma_signal(
    data: Dict[str, pd.DataFrame],
    symbol: str,
    fast: int = 10,
    slow: int = 30,
    direction: str = "long_only",
    n_splits: int = 5,
    embargo: int = 5,
) -> Tuple[List[CVFoldResult], CVFoldResult]:
    df = data[symbol]
    close = df["close"].astype(float)
    rets = close.pct_change().fillna(0.0)
    base = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
    sig = base.generate_signals({symbol: df})[symbol].reindex(close.index).fillna(0)
    if direction == "long_only":
        sig = sig.clip(lower=0)
    elif direction == "short_only":
        sig = (sig.mask(sig > 0, 0)).clip(upper=0)
    # Strategy daily returns with one-bar lag to avoid lookahead
    sig_lag = sig.shift(1).fillna(0)
    strat_ret = sig_lag * rets
    # Approximate costs: slippage drag on signal changes
    changes = sig.diff().abs().fillna(0)
    cost_drag = changes * (1.0 / 10000.0)  # 1bp per change
    strat_ret_cost = strat_ret - cost_drag
    X = pd.DataFrame({"sig": sig})
    splitter = PurgedTimeSeriesSplit(n_splits=n_splits, embargo=embargo)
    folds: List[CVFoldResult] = []
    ann = np.sqrt(252.0)
    for train_idx, test_idx in splitter.split(X):
        if len(test_idx) == 0:
            continue
        r = strat_ret_cost.iloc[test_idx]
        mean = float(r.mean())
        std = float(r.std(ddof=0)) or 1e-9
        sharpe = (mean / std) * ann
        folds.append(CVFoldResult(mean_ret=mean, sharpe=sharpe, n_obs=int(len(test_idx))))
    # Aggregate
    r_all = strat_ret_cost
    agg = CVFoldResult(
        mean_ret=float(r_all.mean()) if len(r_all) else 0.0,
        sharpe=float((r_all.mean() / (r_all.std(ddof=0) or 1e-9)) * ann) if len(r_all) else 0.0,
        n_obs=int(len(r_all)),
    )
    return folds, agg
