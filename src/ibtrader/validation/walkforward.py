from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from ..backtest.engine import backtest
from ..config import AppSettings
from ..strategy.sma_crossover import SMACrossover
from ..regime.gmm import fit_gmm_regime, build_regime_features
from ..risk.manager import RiskManager, RiskState
from ..backtest.metrics import compute_stats as _cs


@dataclass
class WFResult:
    params: Tuple[int, int]
    train_stats: dict
    val_stats: dict
    test_stats: dict
    stitched_oos: dict
    per_fold: List[dict]


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
    direction: str | None = None,
    n_folds: int = 3,
    warmup_bars: int = 100,
) -> Tuple[WFResult, dict]:
    if param_grid is None:
        param_grid = [(5, 20), (10, 30), (20, 50), (50, 200)]
    df = data[symbol]
    n = len(df)
    idx = list(df.index)
    # Define anchored multi-fold splits over last 40% of data
    oos_start = int(n * 0.6)
    oos_indices = idx[oos_start:]
    fold_size = max(1, len(oos_indices) // n_folds)

    def slice_data(ix: List[pd.Timestamp]) -> Dict[str, pd.DataFrame]:
        # Do not dropna silently; assume upstream gate ensures integrity
        return {k: v.reindex(ix) for k, v in data.items()}

    # Track best over validation in last 20% of train per fold
    tried: List[Tuple[int, int]] = []
    chosen = None
    # Use expanding train and rolling OOS folds
    folds_detail = []
    tried_all: List[Tuple[Tuple[int, int], float]] = []
    total_oos_trades = 0
    stitched_eq = pd.Series(dtype=float)
    stitched_bh = pd.Series(dtype=float)
    for f in range(n_folds):
        test_start = oos_start + f * fold_size
        test_end = oos_start + (f + 1) * fold_size if f < n_folds - 1 else n
        train_idx = idx[: test_start]
        # Validation: last 20% of train
        v_start = int(len(train_idx) * 0.8)
        val_idx = train_idx[v_start:]
        # Warmup indices before val/test start
        warm_start = max(0, min(v_start, test_start) - warmup_bars)
        span_idx = idx[warm_start:test_end]
        # Fit regime model on train and build risk_on series over span
        bench = settings.universe.benchmark if settings.universe.benchmark in data else symbol
        model, _ = fit_gmm_regime(data[bench]["close"].reindex(train_idx), n_components=2, train_slice=slice(None))
        feats_span = build_regime_features(data[bench]["close"].reindex(span_idx))
        proba_span = model.predict_proba(feats_span)
        import numpy as _np
        risk_on_series = pd.Series(
            _np.where(proba_span.argmax(axis=1) == model.risk_on_label, proba_span[:, model.risk_on_label], 0.0),
            index=feats_span.index,
        ).reindex(span_idx).fillna(0.0)
        # Grid search on validation Sharpe
        best = None
        best_sharpe = -1e9
        for fast, slow in param_grid:
            tried.append((fast, slow))
            # Backtest on span (warmup+val), compute stats on val only
            strat = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
            res_span = backtest(
                data=slice_data(span_idx),
                strategy=strat,
                commission_cfg=settings.commission,
                slippage_cfg=settings.slippage,
                direction=direction or settings.trading.direction,
                risk_on=risk_on_series,
                risk_on_threshold=float(settings.risk.risk_on_threshold),
                target_vol_annual=float(settings.risk.target_vol_annual),
                risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=100_000.0)),
            )
            # Recompute stats on val window only
            eq = res_span.equity_curve.reindex(val_idx).dropna()
            rets = res_span.returns.reindex(val_idx).dropna()
            res_val_stats = _cs(eq, rets)
            if res_val_stats.sharpe > best_sharpe:
                best_sharpe = res_val_stats.sharpe
                best = (fast, slow)
            tried_all.append(((fast, slow), float(res_val_stats.sharpe)))
        if chosen is None:
            chosen = best
        # Evaluate with frozen params on train/val/test using warmup spans
        fast, slow = best
        strat = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
        # Train span and compute on train window
        train_span_idx = idx[max(0, len(train_idx) - warmup_bars) : test_start]
        res_train_span = backtest(
            data=slice_data(train_span_idx),
            strategy=strat,
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
            direction=direction or settings.trading.direction,
            risk_on=risk_on_series,
            risk_on_threshold=float(settings.risk.risk_on_threshold),
            target_vol_annual=float(settings.risk.target_vol_annual),
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=100_000.0)),
            )
        train_eq = res_train_span.equity_curve.reindex(train_idx).dropna()
        train_rets = res_train_span.returns.reindex(train_idx).dropna()
        res_train_stats = _cs(train_eq, train_rets)
        # Val span (warmup+val), compute on val
        val_span_idx = idx[warm_start:test_start]
        res_val_span = backtest(
            data=slice_data(val_span_idx),
            strategy=strat,
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
            direction=direction or settings.trading.direction,
            risk_on=risk_on_series,
            risk_on_threshold=float(settings.risk.risk_on_threshold),
            target_vol_annual=float(settings.risk.target_vol_annual),
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=100_000.0)),
        )
        val_eq = res_val_span.equity_curve.reindex(val_idx).dropna()
        val_rets = res_val_span.returns.reindex(val_idx).dropna()
        res_val_stats = _cs(val_eq, val_rets)
        # Test span (warmup+test), compute on test
        test_span_idx = idx[warm_start:test_end]
        res_test_span = backtest(
            data=slice_data(test_span_idx),
            strategy=strat,
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
            direction=direction or settings.trading.direction,
            risk_on=risk_on_series,
            risk_on_threshold=float(settings.risk.risk_on_threshold),
            target_vol_annual=float(settings.risk.target_vol_annual),
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=100_000.0)),
        )
        test_idx = idx[test_start:test_end]
        test_eq = res_test_span.equity_curve.reindex(test_idx).dropna()
        test_rets = res_test_span.returns.reindex(test_idx).dropna()
        res_test_stats = _cs(test_eq, test_rets)
        total_oos_trades += int(res_test_span.stats.trade_count)
        # Stitch OOS equity and B&H for this fold
        stitched_eq = pd.concat([stitched_eq, test_eq]) if not stitched_eq.empty else test_eq.copy()
        # B&H for same test window
        bench = settings.universe.benchmark
        if bench in data:
            px = data[bench]["close"].astype(float).reindex(test_idx)
            eq_bh = (100_000.0 / float(px.iloc[0])) * px
            stitched_bh = pd.concat([stitched_bh, eq_bh]) if not stitched_bh.empty else eq_bh.copy()
        folds_detail.append(
            {
                "fold": f + 1,
                "dates": {"train": [str(train_idx[0]), str(train_idx[-1])] if train_idx else None, "val": [str(val_idx[0]), str(val_idx[-1])] if val_idx else None, "test": [str(idx[test_start]), str(idx[test_end - 1])] if test_end - test_start > 0 else None},
                "chosen_params": {"fast": fast, "slow": slow},
                "train": res_train_stats.__dict__,
                "val": res_val_stats.__dict__,
                "oos": res_test_stats.__dict__,
                "tried_combos": [{"fast": a, "slow": b, "val_sharpe": s} for (a, b), s in tried_all[-len(param_grid) :]],
                "oos_equity": [[str(t), float(v)] for t, v in test_eq.items()],
                "oos_trades": [{"date": d, "symbol": s, "qty": int(q), "price": float(p)} for d, s, q, p in res_test_span.trades if pd.Timestamp(d) in test_eq.index],
            }
        )
    # Aggregate stitched OOS stats
    stitched_oos_stats = {}
    if len(stitched_eq) > 1:
        stitched_rets = stitched_eq.pct_change().fillna(0.0)
        st = _cs(stitched_eq, stitched_rets)
        stitched_oos_stats = {
            "cagr": st.cagr,
            "sharpe": st.sharpe,
            "sortino": st.sortino,
            "calmar": st.calmar,
            "max_dd": st.max_drawdown,
            "trade_count": int(total_oos_trades),
        }
    wf = WFResult(
        params=chosen or param_grid[0],
        train_stats=folds_detail[-1]["train"] if folds_detail else {},
        val_stats=folds_detail[-1]["val"] if folds_detail else {},
        test_stats=folds_detail[-1]["oos"] if folds_detail else {},
        stitched_oos=stitched_oos_stats,
        per_fold=folds_detail,
    )
    # Buy&Hold on stitched OOS
    bh = None
    if len(stitched_bh) > 1:
        ret = stitched_bh.pct_change().fillna(0.0)
        bh = {
            "cagr": float((stitched_bh.iloc[-1] / stitched_bh.iloc[0]) ** (252 / max(len(stitched_bh), 1)) - 1.0),
            "sharpe": float((ret.mean() / (ret.std(ddof=0) or 1e-9)) * (252 ** 0.5)),
            "max_dd": float((stitched_bh / stitched_bh.cummax() - 1.0).min()),
        }
    summary = {
        "buy_hold_oos": bh,
        "folds": folds_detail,
        "oos_total_trades": int(total_oos_trades),
        "tried_param_count": len(tried_all),
        "stitched_oos_equity": [[str(t), float(v)] for t, v in stitched_eq.items()],
        "stitched_bh_equity": [[str(t), float(v)] for t, v in stitched_bh.items()],
    }
    return wf, summary
