"""Time-series momentum research evaluation via anchored walk-forward folds."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

import pandas as pd

from ..backtest.engine import backtest, restricted_counts
from ..backtest.metrics import compute_stats, copy_oos_cost_metrics
from ..config import AppSettings
from ..risk.manager import RiskManager, RiskState
from ..strategy.tsmom import TimeSeriesMomentum
from .runner import evaluate_gates_with_restricted_frac

DEFAULT_TSMOM_LOOKBACKS: List[int] = [21, 63, 126]


def _commission_for_trades(settings: AppSettings, trades: List[tuple]) -> float:
    cc = settings.commission
    total = 0.0
    for _d, _s, q, p, _r in trades:
        qty = abs(int(q))
        price = float(p)
        per_sh = cc.per_share * qty
        adv = (cc.percent_of_value / 100.0) * qty * price
        total += float(max(per_sh + adv, cc.min_per_order))
    return total


def run_tsmom_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    lookbacks: Sequence[int] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    warmup_bars: int = 100,
) -> List[Dict[str, Any]]:
    """Anchored multi-fold OOS evaluation for TSMOM lookbacks (no look-ahead).

    Fold geometry mirrors ``walk_forward_sma`` (last 40% OOS, n folds) but the
    strategy is frozen TSMOM(lookback) — no in-fold parameter search.

    OOS gates use ``restricted_bar_frac`` from stitched stats: the share of OOS
    bars on which the engine's RiskManager would have blocked new exposure
    (``BacktestResult.restricted`` summed over the test windows).
    """
    lbs = list(lookbacks) if lookbacks is not None else list(DEFAULT_TSMOM_LOOKBACKS)
    df = data[symbol]
    idx = list(df.index)
    n = len(idx)
    oos_start = int(n * 0.6)
    oos_indices = idx[oos_start:]
    fold_size = max(1, len(oos_indices) // n_folds)
    direction = direction or settings.trading.direction
    allow_short = direction != "long_only"
    initial_equity = 100_000.0

    results: List[Dict[str, Any]] = []
    for lookback in lbs:
        agg_total_costs = 0.0
        agg_notional = 0.0
        agg_n_orders = 0
        agg_commission = 0.0
        agg_reg_fees = 0.0
        folds_eq: List[pd.Series] = []
        oos_trades_all: List[tuple] = []
        restricted_bars = 0
        total_bars = 0
        for f in range(n_folds):
            test_start = oos_start + f * fold_size
            test_end = oos_start + (f + 1) * fold_size if f < n_folds - 1 else n
            warm_start = max(0, test_start - warmup_bars)
            span_idx = idx[warm_start:test_end]
            test_idx = idx[test_start:test_end]
            span_data = {k: v.reindex(span_idx) for k, v in data.items()}
            strat = TimeSeriesMomentum(lookback=int(lookback), allow_short=allow_short)
            res = backtest(
                data=span_data,
                strategy=strat,
                commission_cfg=settings.commission,
                slippage_cfg=settings.slippage,
                direction=direction,
                risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
                target_vol_annual=float(settings.risk.target_vol_annual),
                reg_fees_cfg=settings.reg_fees,
            )
            test_dates = set(test_idx)
            test_eq = res.equity_curve.reindex(test_idx).dropna()
            folds_eq.append(test_eq)
            for tr in res.trades:
                if pd.Timestamp(tr[0]) in test_dates:
                    oos_trades_all.append(tr)
            rb, tb = restricted_counts(res, (test_idx[0], test_idx[-1])) if test_idx else (0, 0)
            restricted_bars += int(rb)
            total_bars += int(tb)
        restricted_frac = (restricted_bars / total_bars) if total_bars > 0 else 0.0

        # Stitch OOS via chained returns (same idea as walkforward)
        stitched_rets = pd.Series(dtype=float)
        for eq in folds_eq:
            if len(eq) < 2:
                continue
            rets = eq.pct_change().dropna()
            stitched_rets = pd.concat([stitched_rets, rets]) if not stitched_rets.empty else rets.copy()
        oos: Dict[str, Any] = {}
        if len(stitched_rets) > 0:
            chain = (1.0 + stitched_rets).cumprod() * initial_equity
            st = compute_stats(chain, stitched_rets)
            t_c = getattr(st, "total_costs", 0.0)
            tn = getattr(st, "notional_traded", 0.0)
            n_o = getattr(st, "n_orders", 0)
            t_com = getattr(st, "total_commission", 0.0)
            t_reg = getattr(st, "total_reg_fees", 0.0)
            agg_total_costs += t_c
            agg_notional += tn
            agg_n_orders += n_o
            agg_commission += t_com
            agg_reg_fees += t_reg

            years = max(len(stitched_rets), 1) / 252.0
            avg_cost_bps = (agg_total_costs / agg_notional * 1e4) if agg_notional > 0 else 0.0
            cost_drag = (agg_total_costs / initial_equity / years * 100) if initial_equity > 0 and years > 0 else 0.0
            copy_oos_cost_metrics(oos, {"avg_cost_bps_per_order": avg_cost_bps, "cost_drag_annual_pct": cost_drag})
            t_com_final = agg_commission if agg_commission > 0 else oos.get("_commission_for_trades")
            oos["total_commission"] = t_com_final if isinstance(t_com_final, float) else oos.get("total_commission", 0.0)
            if agg_reg_fees > 0:
                oos["total_reg_fees"] = agg_reg_fees
        else:
            oos = {
                "cagr": float("nan"),
                "sharpe": float("nan"),
                "sortino": float("nan"),
                "calmar": float("nan"),
                "max_dd": float("nan"),
                "restricted_bar_frac": restricted_frac,
                "trade_count": 0,
                "_commission_for_trades": _commission_for_trades(settings, oos_trades_all),
            }
            avg_cost_bps_per_order = 0.0
            cost_drag_annual_pct = 0.0
            total_costs = 0.0
            n_orders = 0
            notional_traded = 0.0

        # B&H on same stitched OOS windows
        bh = None
        bh_rets = pd.Series(dtype=float)
        for eq in folds_eq:
            test_idx_bh = list(eq.index)
            if len(test_idx_bh) < 2 or settings.universe.benchmark not in data:
                continue