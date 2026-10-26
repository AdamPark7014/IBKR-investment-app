"""Mean-reversion (Bollinger) research evaluation via anchored walk-forward folds."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..backtest.engine import backtest, restricted_counts
from ..backtest.metrics import compute_stats, copy_oos_cost_metrics, window_cost_totals
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
            strat = MeanReversion(window=int(window), num_std=float(num_std))
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
            # Costs of the orders inside the test window only (the span also holds the warm-up).
            if len(test_idx):
                wc = window_cost_totals(res.order_costs, test_idx[0], test_idx[-1])
                agg_total_costs += wc["total_costs"]
                agg_notional += wc["notional_traded"]
                agg_n_orders += wc["n_orders"]
                agg_commission += wc["total_commission"]
                agg_reg_fees += wc["total_reg_fees"]
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
            years = max(len(stitched_rets), 1) / 252.0
            avg_bps = (agg_total_costs / agg_notional * 1e4) if agg_notional > 0 else 0.0
            drag = (
                (agg_total_costs / initial_equity / years * 100)
                if initial_equity > 0 and years > 0
                else 0.0
            )
            oos["total_costs"] = agg_total_costs
            oos["notional_traded"] = agg_notional
            oos["n_orders"] = agg_n_orders
            if agg_commission > 0:
                oos["total_commission"] = agg_commission
            if agg_reg_fees > 0:
                oos["total_reg_fees"] = agg_reg_fees
            copy_oos_cost_metrics(
                oos,
                {"avg_cost_bps_per_order": avg_bps, "cost_drag_annual_pct": drag},
            )
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
                "avg_cost_bps_per_order": 0.0,
                "cost_drag_annual_pct": 0.0,
                "total_costs": 0.0,
                "n_orders": 0,
                "notional_traded": 0.0,
            }

        bh = None
        bh_rets = pd.Series(dtype=float)
        for eq in folds_eq:
            test_idx_bh = list(eq.index)
            if len(test_idx_bh) < 2 or settings.universe.benchmark not in data:
                continue
            px = data[settings.universe.benchmark]["close"].astype(float).reindex(test_idx_bh)
            if px.isna().any() or float(px.iloc[0]) == 0:
                continue
            bh_eq = (initial_equity / float(px.iloc[0])) * px
            r = bh_eq.pct_change().dropna()
            bh_rets = pd.concat([bh_rets, r]) if not bh_rets.empty else r.copy()
        if len(bh_rets) > 0:
            bh_chain = (1.0 + bh_rets).cumprod() * initial_equity
            vol = float(bh_rets.std(ddof=0))
            bh = {
                "cagr": float((bh_chain.iloc[-1] / bh_chain.iloc[0]) ** (252 / max(len(bh_chain), 1)) - 1.0),
                "sharpe": (float((bh_rets.mean() / vol) * (252**0.5)) if vol > 0 else float("nan")),
                "max_dd": float((bh_chain / bh_chain.cummax() - 1.0).min()),
            }

        gate = evaluate_gates_with_restricted_frac(oos, bh)
        results.append(
            {
                "candidate_id": f"mr_{int(window)}_{float(num_std):g}",
                "params": {
                    "window": int(window),
                    "num_std": float(num_std),
                    "family": "mean_reversion",
                },
                "oos": oos,
                "buy_hold_oos": bh,
                "oos_total_trades": len(oos_trades_all),
                "oos_commission_approx": oos.get("total_commission"),
                "gate_passed": gate.passed,
                "gate_reasons": list(gate.reasons),
                "gate_checks": dict(gate.checks),
            }
        )
    return results
