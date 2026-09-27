"""Cross-sectional momentum research (relative strength rotation) via anchored OOS."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from ..backtest.engine import backtest
from ..backtest.metrics import compute_stats
from ..config import AppSettings
from ..risk.manager import RiskManager, RiskState
from ..strategy.rotation import CrossSectionalMomentum
from .gates import evaluate_candidate_gates

DEFAULT_XSECTION_CANDIDATES: List[Tuple[int, int]] = [
    (60, 2),
    (126, 3),
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


def run_xsection_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    candidates: Sequence[Tuple[int, int]] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    warmup_bars: int = 130,
) -> List[Dict[str, Any]]:
    """Evaluate cross-sectional momentum configs on multi-name ``data``.

    Requires ≥2 symbols. Uses the first symbol's calendar for fold cuts; the
    strategy itself allocates across the universe.
    """
    if len(data) < 2:
        return []
    grid = list(candidates) if candidates is not None else list(DEFAULT_XSECTION_CANDIDATES)
    direction = direction or settings.trading.direction
    # Anchor folds on benchmark or first key
    bench = settings.universe.benchmark if settings.universe.benchmark in data else next(iter(data))
    idx = list(data[bench].index)
    n = len(idx)
    oos_start = int(n * 0.6)
    oos_indices = idx[oos_start:]
    fold_size = max(1, len(oos_indices) // n_folds)
    initial_equity = 100_000.0

    results: List[Dict[str, Any]] = []
    for lookback, top_n in grid:
        folds_eq: List[pd.Series] = []
        oos_trades_all: List[tuple] = []
        strat = CrossSectionalMomentum(lookback_days=int(lookback), top_n=int(top_n))
        for f in range(n_folds):
            test_start = oos_start + f * fold_size
            test_end = oos_start + (f + 1) * fold_size if f < n_folds - 1 else n
            warm_start = max(0, test_start - warmup_bars)
            span_idx = idx[warm_start:test_end]
            test_idx = idx[test_start:test_end]
            span_data = {k: v.reindex(span_idx) for k, v in data.items()}
            res = backtest(
                data=span_data,
                strategy=strat,
                commission_cfg=settings.commission,
                slippage_cfg=settings.slippage,
                direction=direction,
                risk_manager=RiskManager(
                    settings.risk, RiskState(starting_equity_today=initial_equity)
                ),
                target_vol_annual=float(settings.risk.target_vol_annual),
            )
            test_dates = set(test_idx)
            # Portfolio equity is the engine curve
            folds_eq.append(res.equity_curve.reindex(test_idx).dropna())
            for tr in res.trades:
                if pd.Timestamp(tr[0]) in test_dates:
                    oos_trades_all.append(tr)

        stitched_rets = pd.Series(dtype=float)
        for eq in folds_eq:
            if len(eq) < 2:
                continue
            rets = eq.pct_change().dropna()
            stitched_rets = (
                pd.concat([stitched_rets, rets]) if not stitched_rets.empty else rets.copy()
            )
        if len(stitched_rets) > 0:
            chain = (1.0 + stitched_rets).cumprod() * initial_equity
            st = compute_stats(chain, stitched_rets)
            oos: Dict[str, Any] = {
                "cagr": st.cagr,
                "sharpe": st.sharpe,
                "sortino": st.sortino,
                "calmar": st.calmar,
                "max_dd": st.max_drawdown,
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
                "trade_count": 0,
                "total_commission": 0.0,
                "turnover": float("nan"),
            }

        bh = None
        if bench in data:
            bh_rets = pd.Series(dtype=float)
            for eq in folds_eq:
                test_idx_bh = list(eq.index)
                if len(test_idx_bh) < 2:
                    continue
                px = data[bench]["close"].astype(float).reindex(test_idx_bh)
                if px.isna().any() or float(px.iloc[0]) == 0:
                    continue
                bh_eq = (initial_equity / float(px.iloc[0])) * px
                r = bh_eq.pct_change().dropna()
                bh_rets = pd.concat([bh_rets, r]) if not bh_rets.empty else r.copy()
            if len(bh_rets) > 0:
                bh_chain = (1.0 + bh_rets).cumprod() * initial_equity
                vol = float(bh_rets.std(ddof=0))
                bh = {
                    "cagr": float(
                        (bh_chain.iloc[-1] / bh_chain.iloc[0]) ** (252 / max(len(bh_chain), 1))
                        - 1.0
                    ),
                    "sharpe": (
                        float((bh_rets.mean() / vol) * (252**0.5)) if vol > 0 else float("nan")
                    ),
                    "max_dd": float((bh_chain / bh_chain.cummax() - 1.0).min()),
                }

        gate = evaluate_candidate_gates(oos, bh, restricted_bar_frac=0.0)
        results.append(
            {
                "candidate_id": f"xsection_{int(lookback)}_top{int(top_n)}",
                "params": {
                    "family": "xsection_momentum",
                    "lookback": int(lookback),
                    "top_n": int(top_n),
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
