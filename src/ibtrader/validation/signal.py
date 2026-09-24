from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ..ml.cv import PurgedTimeSeriesSplit
from ..strategy.sma_crossover import SMACrossover
from ..config import CommissionConfig, SlippageConfig


def _next_open_returns(open_px: pd.Series) -> pd.Series:
    # r_t = open_t / open_{t-1} - 1
    return open_px.pct_change().fillna(0.0)


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
    open_px = df["open"].astype(float)
    rets = _next_open_returns(open_px)
    base = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
    sig = base.generate_signals({symbol: df})[symbol].reindex(open_px.index).fillna(0)
    if direction == "long_only":
        sig = sig.clip(lower=0)
    elif direction == "short_only":
        sig = (sig.mask(sig > 0, 0)).clip(upper=0)
    # Strategy daily returns with one-bar lag (sig at t-1 acts on open_t)
    sig_lag = sig.shift(1).fillna(0)
    strat_ret_gross = sig_lag * rets
    # Costs: slippage + commission on signal changes at open
    changes = sig_lag.diff().abs().fillna(0)
    slip = SlippageConfig()  # default bps
    commission = CommissionConfig()  # default per-share/min
    nav = 100_000.0
    # Shares traded per change_t = |Δsig| * nav / open_t
    shares_traded = (changes * nav / open_px).fillna(0.0)
    per_share_comm = commission.per_share * shares_traded
    min_comm = shares_traded.apply(lambda sh: commission.min_per_order if sh > 0 else 0.0)
    comm_cost = (per_share_comm.where(per_share_comm > min_comm, min_comm)) / nav
    slip_cost = (changes * (slip.bps / 10000.0)).fillna(0.0)
    strat_ret_cost = strat_ret_gross - (comm_cost + slip_cost)
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
