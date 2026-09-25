from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from typing import cast as _cast

import pandas as pd

from ..backtest.engine import backtest
from ..backtest.metrics import compute_stats as _cs
from ..config import AppSettings
from ..regime.gmm import build_regime_features, fit_gmm_regime
from ..risk.manager import RiskManager, RiskState
from ..strategy.sma_crossover import SMACrossover


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
    folds_detail: List[Dict[str, Any]] = []
    tried_all: List[Tuple[Tuple[int, int], float]] = []
    total_oos_trades = 0
    total_oos_commission = 0.0
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
        if best is None:
            # Fallback to first grid item (should not happen with non-empty grid)
            best = param_grid[0]
        fast, slow = best
        strat = SMACrossover(fast_window=fast, slow_window=slow, allow_short=True)
        # Train span and compute on train window
        train_span_idx = idx[:test_start]
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
        # Count only trades whose date is inside the test window
        test_dates = set(test_idx)
        # Map trades and recompute commission for OOS trades
        from typing import cast as _cast_t
        oos_trades_list = []
        for d, s, q, p, r in res_test_span.trades:
            if pd.Timestamp(d) in test_dates:
                oos_trades_list.append({"date": d, "symbol": s, "qty": int(q), "price": float(p), "reason": r})
        oos_trades_this = len(oos_trades_list)
        total_oos_trades += int(oos_trades_this)
        # Commission per OOS trade
        cc = settings.commission
        comm_fold = 0.0
        for tr in oos_trades_list:
            per_sh = cc.per_share * abs(int(_cast_t(int, tr["qty"])))
            adv = (cc.percent_of_value / 100.0) * abs(int(_cast_t(int, tr["qty"]))) * float(
                _cast_t(float, tr["price"])
            )
            comm_fold += float(max(per_sh + adv, cc.min_per_order))
        total_oos_commission += float(comm_fold)
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
                "dates": {
                    "train": [str(train_idx[0]), str(train_idx[-1])] if train_idx else None,
                    "val": [str(val_idx[0]), str(val_idx[-1])] if val_idx else None,
                    "test": (
                        [str(idx[test_start]), str(idx[test_end - 1])]
                        if test_end - test_start > 0
                        else None
                    ),
                },
                "chosen_params": {"fast": fast, "slow": slow},
                "train": res_train_stats.__dict__,
                "val": res_val_stats.__dict__,
                "oos": {
                    **res_test_stats.__dict__,
                    "trade_count": int(oos_trades_this),
                    "commission": float(comm_fold),
                },
                "tried_combos": [
                    {"fast": a, "slow": b, "val_sharpe": s}
                    for (a, b), s in tried_all[-len(param_grid) :]
                ],
                "oos_equity": [[str(t), float(v)] for t, v in test_eq.items()],
                "oos_trades": oos_trades_list,
            }
        )
    # Aggregate stitched OOS stats: chain daily returns across folds
    stitched_oos_stats = {}
    if len(folds_detail) > 0:
        # Build stitched returns across folds from per-fold equity
        stitched_rets = pd.Series(dtype=float)
        for fd in folds_detail:
            oos_eq = pd.Series({pd.Timestamp(t): v for t, v in fd["oos_equity"]}).sort_index()
            rets_fold = oos_eq.pct_change().dropna()
            stitched_rets = (
                pd.concat([stitched_rets, rets_fold]) if not stitched_rets.empty else rets_fold.copy()
            )
        if len(stitched_rets) > 0:
            eq0 = 100_000.0
            stitched_eq_chain = (1.0 + stitched_rets).cumprod() * eq0
            st = _cs(stitched_eq_chain, stitched_rets)
            # Count only trades occurring within OOS dates
            oos_trade_count = sum(len(fd["oos_trades"]) for fd in folds_detail)
            stitched_oos_stats = {
                "cagr": st.cagr,
                "sharpe": st.sharpe,
                "sortino": st.sortino,
                "calmar": st.calmar,
                "max_dd": st.max_drawdown,
                "trade_count": int(oos_trade_count),
            }
    wf = WFResult(
        params=chosen or param_grid[0],
        train_stats=_cast(Dict[str, Any], folds_detail[-1]["train"]) if folds_detail else {},
        val_stats=_cast(Dict[str, Any], folds_detail[-1]["val"]) if folds_detail else {},
        test_stats=_cast(Dict[str, Any], stitched_oos_stats) if stitched_oos_stats else {},
        stitched_oos=stitched_oos_stats,
        per_fold=folds_detail,
    )
    # Buy&Hold on stitched OOS
    bh = None
    if len(folds_detail) > 0:
        stitched_bh_rets = pd.Series(dtype=float)
        for fd in folds_detail:
            test_idx = [pd.Timestamp(t) for t, _ in fd["oos_equity"]]
            if settings.universe.benchmark in data and len(test_idx) > 1:
                px = data[settings.universe.benchmark]["close"].astype(float).reindex(test_idx)
                bh_eq = (100_000.0 / float(px.iloc[0])) * px
                rets_fold = bh_eq.pct_change().dropna()
                stitched_bh_rets = (
                    pd.concat([stitched_bh_rets, rets_fold]) if not stitched_bh_rets.empty else rets_fold
                )
        if len(stitched_bh_rets) > 0:
            eq0 = 100_000.0
            bh_chain = (1.0 + stitched_bh_rets).cumprod() * eq0
            ret = stitched_bh_rets
            bh = {
                "cagr": float((bh_chain.iloc[-1] / bh_chain.iloc[0]) ** (252 / max(len(bh_chain), 1)) - 1.0),
                "sharpe": float((ret.mean() / (ret.std(ddof=0) or 1e-9)) * (252 ** 0.5)),
                "max_dd": float((bh_chain / bh_chain.cummax() - 1.0).min()),
            }
    # Approximate OOS commission using per-trade commission for test-window trades
    oos_commission = 0.0
    if folds_detail:
        for fd in folds_detail:
            cc = settings.commission
            # We only have qty and price; recompute commission per trade
            for tr in fd["oos_trades"]:
                per_sh = cc.per_share * abs(int(_cast_t(int, tr["qty"])))
                adv = (cc.percent_of_value / 100.0) * abs(int(_cast_t(int, tr["qty"]))) * float(
                    _cast_t(float, tr["price"])
                )
                oos_commission += float(max(per_sh + adv, cc.min_per_order))
    summary = {
        "buy_hold_oos": bh,
        "folds": folds_detail,
        "oos_total_trades": int(total_oos_trades),
        "oos_commission_approx": float(oos_commission),
        "tried_param_count": len(tried_all),
        "stitched_oos_equity": [[str(t), float(v)] for t, v in stitched_eq.items()],
        "stitched_bh_equity": [[str(t), float(v)] for t, v in stitched_bh.items()],
    }
    return wf, summary
