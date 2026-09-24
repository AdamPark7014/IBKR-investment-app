from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from ..backtest.engine import backtest
from ..config import AppSettings
from ..strategy.sma_crossover import SMACrossover


@dataclass
class WFResult:
    params: Tuple[int, int]
    train_stats: dict
    val_stats: dict
    test_stats: dict


def _stats_to_dict(stats) -> dict:
    return {
        "cagr": stats.cagr,
        "sharpe": stats.sharpe,
        "sortino": stats.sortino,
        "calmar": stats.calmar,
        "max_dd": stats.max_drawdown,
        "win_rate": stats.win_rate,
        "trade_count": stats.trade_count,
        "commission": stats.total_commission,
        "turnover": stats.turnover,
    }


def walk_forward_sma(
    settings: AppSettings,
    data: Dict[str, pd.DataFrame],
    symbol: str,
    param_grid: List[Tuple[int, int]] | None = None,
) -> Tuple[WFResult, dict]:
    if param_grid is None:
        param_grid = [(5, 20), (10, 30)]
    df = data[symbol]
    n = len(df)
    i1 = int(n * 0.6)
    i2 = int(n * 0.8)
    idx = list(df.index)
    train_idx = idx[:i1]
    val_idx = idx[i1:i2]
    test_idx = idx[i2:]

    def slice_data(ix: List[pd.Timestamp]) -> Dict[str, pd.DataFrame]:
        return {k: v.reindex(ix).dropna() for k, v in data.items()}

    best = None
    best_sharpe = -1e9
    # Select on validation Sharpe
    for fast, slow in param_grid:
        strat = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
        res_val = backtest(
            data=slice_data(val_idx),
            strategy=strat,
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
        )
        if res_val.stats.sharpe > best_sharpe:
            best_sharpe = res_val.stats.sharpe
            best = (fast, slow)
    # Freeze and evaluate
    assert best is not None
    fast, slow = best
    strat = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
    res_train = backtest(
        data=slice_data(train_idx),
        strategy=strat,
        commission_cfg=settings.commission,
        slippage_cfg=settings.slippage,
    )
    res_val = backtest(
        data=slice_data(val_idx),
        strategy=strat,
        commission_cfg=settings.commission,
        slippage_cfg=settings.slippage,
    )
    res_test = backtest(
        data=slice_data(test_idx),
        strategy=strat,
        commission_cfg=settings.commission,
        slippage_cfg=settings.slippage,
    )
    wf = WFResult(
        params=best,
        train_stats=_stats_to_dict(res_train.stats),
        val_stats=_stats_to_dict(res_val.stats),
        test_stats=_stats_to_dict(res_test.stats),
    )
    # Buy&Hold on test
    bench = settings.universe.benchmark
    bh = None
    if bench in data:
        px = data[bench]["close"].astype(float).reindex(test_idx).dropna()
        eq = (100_000.0 / float(px.iloc[0])) * px
        ret = eq.pct_change().fillna(0.0)
        bh = {
            "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (252 / max(len(eq), 1)) - 1.0),
            "sharpe": float((ret.mean() / (ret.std(ddof=0) or 1e-9)) * (252 ** 0.5)),
            "max_dd": float((eq / eq.cummax() - 1.0).min()),
        }
    summary = {"buy_hold_oos": bh}
    return wf, summary
