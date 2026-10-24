"""Mean-reversion (Bollinger) research evaluation via anchored walk-forward folds."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..backtest.engine import backtest, restricted_counts
from ..backtest.metrics import compute_stats
from ..config import AppSettings
from ..risk.manager import RiskManager, RiskState
from ..strategy.mean_reversion import MeanReversion
from .runner import evaluate_gates_with_restricted_frac

# (window, num_std) — keep small; mean-rev is a second family stress, not a grid hunt.
DEFAULT_MR_CANDIDATES: List[Tuple[int, float]] = [
    (20, 2.0),
    (40, 2.0),
]


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


def run_mean_reversion_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    candidates: Sequence[Tuple[int, float]] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    warmup_bars: int = 100,
) -> List[Dict[str, Any]]:
    """Anchored multi-fold OOS evaluation for Bollinger mean-reversion configs.

    ``restricted_bar_frac`` in the OOS stats is the share of test-window bars on
    which the engine's RiskManager would have blocked new exposure.
    """
    from ..backtest.cost_metrics import copy_oos_cost_metrics
    grid = list(candidates) if candidates is not None else list(DEFAULT_MR_CANDIDATES)
    df = data[symbol]
    idx = list(df.index)
    n = len(idx)
    oos_start = int(n * 0.6)
    oos_indices = idx[oos_start:]
    fold_size = max(1, len(oos_indices) // n_folds)
    direction = direction or settings.trading.direction
    initial_equity = 100_000.0

    results: List[Dict[str, Any]] = []
    for window, num_std in grid:
        folds_eq: List[pd.Series] = []
        oos_trades_all: List[tuple] = []
        restricted_bars = 0
        total_bars = 0
        res_stats_list: List[Dict[str, Any]] = []
        for f in range(n_folds):
            test_start = oos_start + f * fold_size
            test_end = oos_start + (f + 1) * fold_size if f < n_folds - 1 else n
            warm_start = max(0, test_start - warmup_bars)
            span_idx = idx[warm_start:test_end]
            test_idx = idx[test_start:test_end]
            span_data = {k: v.reindex(span_idx) for k, v in data.items()}
            strat = MeanReversion(window=int(window), num_std=float(num_std))
            res = backtest(
                data=span_data,
                strategy=strat,
                commission_cfg=settings.commission,
                slippage_cfg=settings.slippage,
                direction=direction,
                risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
                target_vol_annual=float(settings.risk.target_vol_annual),
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
            res_stats = compute_stats(res.equity_curve.reindex(test_idx).dropna(), res.trades)
            # accumulate per fold from res.stats (total_costs, notional_traded, n_orders, total_commission, total_reg_fees)
            stats_agg = {
                'notional_traded': stats_agg.get('notional_traded', 0) + res_stats.notional_traded if hasattr(res_stats, 'notional_traded') else res_stats.get('notional_traded', 0),
                'n_orders': stats_agg.get('n_orders', 0) + res_stats.n_orders if hasattr(res_stats, 'n_orders') else res_stats.get('n_orders', 0),
                'total_commission': stats_agg.get('total_commission', 0.0) + res_stats.total_commission if hasattr(res_stats, 'total_commission') else res_stats.get('total_commission', 0.0),
            }
            # accumulate total_costs and total_reg_fees if they exist in the metrics structure
            if hasattr(res_stats, 'total_costs'):
                stats_agg['total_costs'] = stats_agg.get('total_costs', 0) + res_stats.total_costs
            if hasattr(res_stats, 'total_reg_fees'):
                stats_agg['total_reg_fees'] = stats_agg.get('total_reg_fees', 0.0) + res_stats.total_reg_fees
            stats_agg['fold_idx'] = f
            res_stats_list.append(stats_agg)
        # Aggregate accumulated stats after the loop implicitly handled by accumulating in loop? No, accumulate from list
        # Re-accumulating properly outside or during loop: let's do proper accumulation here based on logic
        if len(res_stats_list) > 0:
            agg_stats = {'fold_idx': None, 'total_costs': res_stats_list[0].get('total_costs', 0), 'notional_traded': res_stats_list[0].get('notional_traded', 0), 'n_orders': res_stats_list[0].get('n_orders', 0), 'total_commission': res_stats_list[0].get('total_commission', 0.0), 'total_reg_fees': res_stats_list[0].get('total_reg_fees', 0.0)}
            for stat_dict in res_stats_list:
                agg_stats['notional_traded'] += stat_dict.get('notional_traded', 0)
                agg_stats['n_orders'] += stat_dict.get('n_orders', 0)
                agg_stats['total_commission'] += stat_dict.get('total_commission', 0.0)
                if 'total_costs' in stat_dict:
                    agg_stats['total_costs'] += stat_dict['total_costs']
                if 'total_reg_fees' in stat_dict:
                    agg_stats['total_reg_fees'] += stat_dict['total_reg_fees']
        else:
            agg_stats = {'total_costs': 0.0, 'notional_traded': 0.0, 'n_orders': 0, 'total_commission': 0.0, 'total_reg_fees': 0.0}

        restricted_frac = (restricted_bars / total_bars) if total_bars > 0 else 0.0

        stitched_rets = pd.Series(dtype=float)
        for eq in folds_eq:
            if len(eq) < 2:
                continue
            rets = eq.pct_change().dropna()
            stitched_rets = pd.concat([stitched_rets, rets]) if not stitched_rets.empty else rets.copy()
        if len(stitched_rets) > 0:
            chain = (1.0 + stitched_rets).cumprod() * initial_equity
            st = compute_stats(chain, stitched_rets)
            oos: Dict[str, Any] = {
                "cagr": st.cagr,
                "sharpe": st.sharpe,
                "sortino": st.sortino,
                "calmar": st.calmar,
                "max_dd": st.max_drawdown,
                "restricted_bar_frac": restricted_frac,
                "trade_count": len(oos_trades_all),
                "total_commission": _commission_for_trades(settings, oos_trades_all),
                "turnover": float(st.turnover) if st.turnover is not None else float("nan"),
            }
        else:
            oos = {
                "cagr": float("nan"),
                "sharpe": float("nan"),
                "sortino": float("nan"),
                "calmar": float("nan"),
                "max_dd": float("nan"),
                "restricted_bar_frac": restricted_frac,
                "trade_count": 0,
                "total_commission": 0.0,
                "turnover": float("nan"),
            }

        bh = None
        bh_rets = pd.Series(dtype=float)
        for eq in folds_eq:
            test_idx_bh = list(eq.index)