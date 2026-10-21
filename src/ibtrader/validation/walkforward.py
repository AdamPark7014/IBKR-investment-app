from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as _np
import pandas as pd

from ..backtest.engine import backtest, restricted_counts
from ..backtest.metrics import compute_stats as _cs
from ..backtest.reasons import TradeReason
from ..config import AppSettings, CommissionConfig
from ..regime.gmm import build_regime_features, fit_gmm_regime
from ..risk.manager import RiskManager, RiskState
from ..strategy.sma_crossover import SMACrossover

_NAN = float("nan")


@dataclass
class WFResult:
    """Walk-forward aggregate.

    ``params`` is intentionally None: each fold may choose different SMA windows.
    Use ``per_fold`` / summary ``per_fold_params`` for the real picks. Never treat
    a single fold's train/val stats as the whole-run result.
    """

    params: Tuple[int, int] | None
    train_stats: dict | None
    val_stats: dict | None
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
        "total_commission": stats.total_commission,
        "turnover": stats.turnover,
        "profit_factor": stats.profit_factor,
        "expectancy": stats.expectancy,
    }


def _commission_for_fills(cc: CommissionConfig, trades: List[dict]) -> float:
    total = 0.0
    for tr in trades:
        qty = abs(int(tr["qty"]))
        price = float(tr["price"])
        per_sh = cc.per_share * qty
        adv = (cc.percent_of_value / 100.0) * qty * price
        total += float(max(per_sh + adv, cc.min_per_order))
    return total


def _turnover_for_fills(trades: List[dict], initial_equity: float) -> float:
    if initial_equity <= 0:
        return _NAN
    notional = sum(abs(int(tr["qty"])) * float(tr["price"]) for tr in trades)
    return float(notional / initial_equity)


def _roundtrip_trade_metrics(trades: List[dict]) -> Tuple[float, float]:
    """FIFO pair fills per symbol into round-trips; return (profit_factor, expectancy).

    If no completed round-trips exist, return (NaN, NaN) — never fake zeros.
    """
    from collections import defaultdict, deque

    open_lots: Dict[str, deque] = defaultdict(deque)
    pnls: List[float] = []
    for tr in sorted(trades, key=lambda t: str(t["date"])):
        sym = str(tr["symbol"])
        qty = int(tr["qty"])
        px = float(tr["price"])
        if qty == 0:
            continue
        lots = open_lots[sym]
        # Opening or adding in same direction
        if not lots or (lots[0][0] > 0 and qty > 0) or (lots[0][0] < 0 and qty < 0):
            lots.append([qty, px])
            continue
        # Closing / reducing opposite side
        remaining = qty
        while remaining != 0 and lots:
            lot_qty, lot_px = lots[0]
            # opposite signs
            if lot_qty * remaining >= 0:
                break
            closed = min(abs(lot_qty), abs(remaining))
            if lot_qty > 0:
                # was long, now selling
                pnls.append(closed * (px - lot_px))
                lot_qty -= closed
                remaining += closed  # remaining is negative when selling
            else:
                # was short, now buying
                pnls.append(closed * (lot_px - px))
                lot_qty += closed
                remaining -= closed
            if lot_qty == 0:
                lots.popleft()
            else:
                lots[0][0] = lot_qty
        if remaining != 0:
            lots.append([remaining, px])
    if not pnls:
        return _NAN, _NAN
    wins = sum(p for p in pnls if p > 0)
    losses = sum(-p for p in pnls if p < 0)
    pf = (wins / losses) if losses > 0 else (_NAN if wins == 0 else float("inf"))
    exp = float(sum(pnls) / len(pnls))
    return float(pf) if pf == pf or pf == float("inf") else _NAN, exp


def _restricted_frac(restricted_bars: int, total_bars: int) -> float:
    """Share of OOS bars under risk lockout; 0.0 when the window is empty."""
    return float(restricted_bars) / float(total_bars) if total_bars > 0 else 0.0


def _enrich_window_stats(
    base_stats_dict: dict,
    trades: List[dict],
    commission: float,
    initial_equity: float,
) -> dict:
    """Overlay trade-derived metrics onto equity-only compute_stats output."""
    out = dict(base_stats_dict)
    pf, exp = _roundtrip_trade_metrics(trades)
    out["trade_count"] = int(len(trades))
    out["commission"] = float(commission)
    out["total_commission"] = float(commission)
    out["turnover"] = _turnover_for_fills(trades, initial_equity)
    out["profit_factor"] = pf
    out["expectancy"] = exp
    return out


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
    # Use expanding train and rolling OOS folds
    folds_detail: List[Dict[str, Any]] = []
    tried_all: List[Tuple[Tuple[int, int], float]] = []
    total_oos_trades = 0
    total_oos_commission = 0.0
    total_oos_restricted_bars = 0
    total_oos_bars = 0
    stitched_eq = pd.Series(dtype=float)
    stitched_bh = pd.Series(dtype=float)
    initial_equity = 100_000.0
    for f in range(n_folds):
        test_start = oos_start + f * fold_size
        test_end = oos_start + (f + 1) * fold_size if f < n_folds - 1 else n
        train_idx = idx[:test_start]
        # Validation: last 20% of train
        v_start = int(len(train_idx) * 0.8)
        val_idx = train_idx[v_start:]
        # Warmup indices before val/test start
        warm_start = max(0, min(v_start, test_start) - warmup_bars)
        span_idx = idx[warm_start:test_end]
        # Fit regime model on train and build risk_on series over span
        bench = settings.universe.benchmark if settings.universe.benchmark in data else symbol
        model, _ = fit_gmm_regime(
            data[bench]["close"].reindex(train_idx), n_components=2, train_slice=slice(None)
        )
        feats_span = build_regime_features(data[bench]["close"].reindex(span_idx))
        proba_span = model.predict_proba(feats_span)
        # Pre-warmup / missing features → 0.0 (neutral / flat), NEVER implicit risk-on
        risk_on_series = pd.Series(
            _np.where(
                proba_span.argmax(axis=1) == model.risk_on_label,
                proba_span[:, model.risk_on_label],
                0.0,
            ),
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
                risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
            )
            # Recompute stats on val window only
            eq = res_span.equity_curve.reindex(val_idx).dropna()
            rets = res_span.returns.reindex(val_idx).dropna()
            res_val_stats = _cs(eq, rets)
            sharpe_val = float(res_val_stats.sharpe)
            # Prefer finite Sharpe; first finite wins over NaN; among finite, max wins
            if best is None:
                best = (fast, slow)
                best_sharpe = sharpe_val if sharpe_val == sharpe_val else -1e9
            elif sharpe_val == sharpe_val and sharpe_val > best_sharpe:
                best_sharpe = sharpe_val
                best = (fast, slow)
            tried_all.append(
                (
                    (fast, slow),
                    sharpe_val if sharpe_val == sharpe_val else _NAN,
                )
            )
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
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
        )
        train_eq = res_train_span.equity_curve.reindex(train_idx).dropna()
        train_rets = res_train_span.returns.reindex(train_idx).dropna()
        res_train_stats = _cs(train_eq, train_rets)
        train_dates = set(train_idx)
        train_trades = [
            {
                "date": d,
                "symbol": s,
                "qty": int(q),
                "price": float(p),
                "reason": TradeReason.coerce(r),
                "exit_reason": TradeReason.coerce(r),
            }
            for d, s, q, p, r in res_train_span.trades
            if pd.Timestamp(d) in train_dates
        ]
        train_comm = _commission_for_fills(settings.commission, train_trades)
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
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
        )
        val_eq = res_val_span.equity_curve.reindex(val_idx).dropna()
        val_rets = res_val_span.returns.reindex(val_idx).dropna()
        res_val_stats = _cs(val_eq, val_rets)
        val_dates = set(val_idx)
        val_trades = [
            {
                "date": d,
                "symbol": s,
                "qty": int(q),
                "price": float(p),
                "reason": TradeReason.coerce(r),
                "exit_reason": TradeReason.coerce(r),
            }
            for d, s, q, p, r in res_val_span.trades
            if pd.Timestamp(d) in val_dates
        ]
        val_comm = _commission_for_fills(settings.commission, val_trades)
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
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
        )
        test_idx = idx[test_start:test_end]
        test_eq = res_test_span.equity_curve.reindex(test_idx).dropna()
        test_rets = res_test_span.returns.reindex(test_idx).dropna()
        res_test_stats = _cs(test_eq, test_rets)
        # Count only trades whose date is inside the test window
        test_dates = set(test_idx)
        oos_trades_list = []
        for d, s, q, p, r in res_test_span.trades:
            if pd.Timestamp(d) in test_dates:
                reason = TradeReason.coerce(r)
                oos_trades_list.append(
                    {
                        "date": d,
                        "symbol": s,
                        "qty": int(q),
                        "price": float(p),
                        "reason": reason,
                        "exit_reason": reason,
                    }
                )
        oos_trades_this = len(oos_trades_list)
        total_oos_trades += int(oos_trades_this)
        comm_fold = _commission_for_fills(settings.commission, oos_trades_list)
        total_oos_commission += float(comm_fold)
        # Risk lockout bars inside the test window only (engine span includes warmup)
        restricted_fold, bars_fold = (
            restricted_counts(res_test_span, (test_idx[0], test_idx[-1])) if test_idx else (0, 0)
        )
        total_oos_restricted_bars += int(restricted_fold)
        total_oos_bars += int(bars_fold)
        oos_fold_stats = _enrich_window_stats(
            res_test_stats.__dict__, oos_trades_list, comm_fold, initial_equity
        )
        oos_fold_stats["restricted_bar_frac"] = _restricted_frac(restricted_fold, bars_fold)
        # Stitch OOS equity and B&H for this fold
        stitched_eq = pd.concat([stitched_eq, test_eq]) if not stitched_eq.empty else test_eq.copy()
        # B&H for same test window
        bench = settings.universe.benchmark
        if bench in data:
            px = data[bench]["close"].astype(float).reindex(test_idx)
            eq_bh = (initial_equity / float(px.iloc[0])) * px
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
                "train": _enrich_window_stats(
                    res_train_stats.__dict__, train_trades, train_comm, initial_equity
                ),
                "val": _enrich_window_stats(
                    res_val_stats.__dict__, val_trades, val_comm, initial_equity
                ),
                "oos": oos_fold_stats,
                "tried_combos": [
                    {"fast": a, "slow": b, "val_sharpe": s}
                    for (a, b), s in tried_all[-len(param_grid) :]
                ],
                "oos_equity": [[str(t), float(v)] for t, v in test_eq.items()],
                "oos_trades": oos_trades_list,
            }
        )
    # Aggregate stitched OOS stats: chain daily returns across folds
    stitched_oos_stats: Dict[str, Any] = {}
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
            eq0 = initial_equity
            stitched_eq_chain = (1.0 + stitched_rets).cumprod() * eq0
            st = _cs(stitched_eq_chain, stitched_rets)
            all_oos_trades = [tr for fd in folds_detail for tr in fd["oos_trades"]]
            oos_trade_count = len(all_oos_trades)
            stitched_oos_stats = _enrich_window_stats(
                {
                    "cagr": st.cagr,
                    "sharpe": st.sharpe,
                    "sortino": st.sortino,
                    "calmar": st.calmar,
                    "max_dd": st.max_drawdown,
                    "max_drawdown": st.max_drawdown,
                    "win_rate": st.win_rate,
                    "trade_count": 0,
                    "total_commission": 0.0,
                    "turnover": 0.0,
                    "profit_factor": 0.0,
                    "expectancy": 0.0,
                },
                all_oos_trades,
                float(total_oos_commission),
                initial_equity,
            )
            stitched_oos_stats["trade_count"] = int(oos_trade_count)
            stitched_oos_stats["restricted_bar_frac"] = _restricted_frac(
                total_oos_restricted_bars, total_oos_bars
            )
    per_fold_params = [
        {"fold": fd["fold"], "fast": fd["chosen_params"]["fast"], "slow": fd["chosen_params"]["slow"]}
        for fd in folds_detail
    ]
    wf = WFResult(
        params=None,  # never present a single fold as 'the' best
        train_stats=None,  # per-fold only; do not promote last fold
        val_stats=None,
        test_stats=stitched_oos_stats if stitched_oos_stats else {},
        stitched_oos=stitched_oos_stats,
        per_fold=folds_detail,
    )
    # Buy&Hold on stitched OOS
    bh = None
    if len(folds_detail) > 0:
        stitched_bh_rets = pd.Series(dtype=float)
        for fd in folds_detail:
            test_idx_bh = [pd.Timestamp(t) for t, _ in fd["oos_equity"]]
            if settings.universe.benchmark in data and len(test_idx_bh) > 1:
                px = data[settings.universe.benchmark]["close"].astype(float).reindex(test_idx_bh)
                bh_eq = (initial_equity / float(px.iloc[0])) * px
                rets_fold = bh_eq.pct_change().dropna()
                stitched_bh_rets = (
                    pd.concat([stitched_bh_rets, rets_fold])
                    if not stitched_bh_rets.empty
                    else rets_fold
                )
        if len(stitched_bh_rets) > 0:
            eq0 = initial_equity
            bh_chain = (1.0 + stitched_bh_rets).cumprod() * eq0
            ret = stitched_bh_rets
            vol = float(ret.std(ddof=0))
            sharpe_bh = (
                float((ret.mean() / vol) * (252 ** 0.5)) if vol > 0 else _NAN
            )
            bh = {
                "cagr": float(
                    (bh_chain.iloc[-1] / bh_chain.iloc[0]) ** (252 / max(len(bh_chain), 1)) - 1.0
                ),
                "sharpe": sharpe_bh,
                "max_dd": float((bh_chain / bh_chain.cummax() - 1.0).min()),
            }
    summary = {
        "buy_hold_oos": bh,
        "folds": folds_detail,
        "per_fold_params": per_fold_params,
        "oos_total_trades": int(total_oos_trades),
        "oos_commission_approx": float(total_oos_commission),
        "oos_restricted_bars": int(total_oos_restricted_bars),
        "oos_total_bars": int(total_oos_bars),
        "restricted_bar_frac": _restricted_frac(total_oos_restricted_bars, total_oos_bars),
        "tried_param_count": len(tried_all),
        "stitched_oos_equity": [[str(t), float(v)] for t, v in stitched_eq.items()],
        "stitched_bh_equity": [[str(t), float(v)] for t, v in stitched_bh.items()],
    }
    return wf, summary
