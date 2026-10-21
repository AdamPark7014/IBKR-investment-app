"""Loss-mitigation overlays evaluated under the same OOS gates as other V3 tracks.

Hypothesis (institutional, not promotional):
  Overlays that cut exposure in hostile regimes may *lower max drawdown* and
  fail-sooner on fragile edges — even when they also lower Sharpe.
  Success metric here is DD / lockout discipline, not "win much more."
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from ..backtest.engine import backtest, restricted_counts
from ..backtest.metrics import compute_stats
from ..config import AppSettings
from ..risk.manager import RiskManager, RiskState
from ..strategy.base import Strategy
from ..strategy.sma_crossover import SMACrossover
from .runner import evaluate_gates_with_restricted_frac


class TrendFilteredSMA(Strategy):
    """SMA crossover flattened when price is below a long moving average."""

    def __init__(self, fast: int = 10, slow: int = 30, trend_ma: int = 200) -> None:
        self.fast = int(fast)
        self.slow = int(slow)
        self.trend_ma = int(trend_ma)
        self._base = SMACrossover(fast_window=self.fast, slow_window=self.slow)

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base = self._base.generate_signals(data)
        out: Dict[str, pd.Series] = {}
        for sym, sig in base.items():
            close = data[sym]["close"].astype(float)
            ma = close.rolling(self.trend_ma).mean()
            allow = (close > ma).fillna(False)
            out[sym] = (sig.where(allow, 0)).fillna(0).astype(int)
        return out


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


def _with_risk_overlay(
    settings: AppSettings,
    *,
    stop_loss_pct: Optional[float] = None,
    drawdown_limit_pct: Optional[float] = None,
    daily_loss_limit_pct: Optional[float] = None,
    target_vol: Optional[float] = None,
) -> AppSettings:
    try:
        s = settings.model_copy(deep=True)
    except Exception:
        s = deepcopy(settings)
    if stop_loss_pct is not None:
        s.risk.stop_loss_per_position_pct = float(stop_loss_pct)
    if drawdown_limit_pct is not None:
        s.risk.drawdown_limit_pct = float(drawdown_limit_pct)
    if daily_loss_limit_pct is not None:
        s.risk.daily_loss_limit_pct = float(daily_loss_limit_pct)
    if target_vol is not None:
        s.risk.target_vol_annual = float(target_vol)
    return s


def _anchored_oos(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    strategy: Strategy,
    *,
    direction: str,
    n_folds: int,
    warmup_bars: int = 120,
) -> Dict[str, Any]:
    df = data[symbol]
    idx = list(df.index)
    n = len(idx)
    oos_start = int(n * 0.6)
    oos_indices = idx[oos_start:]
    fold_size = max(1, len(oos_indices) // n_folds)
    initial_equity = 100_000.0
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
        res = backtest(
            data=span_data,
            strategy=strategy,
            commission_cfg=settings.commission,
            slippage_cfg=settings.slippage,
            direction=direction,
            risk_manager=RiskManager(settings.risk, RiskState(starting_equity_today=initial_equity)),
            target_vol_annual=float(settings.risk.target_vol_annual),
        )
        test_dates = set(test_idx)
        folds_eq.append(res.equity_curve.reindex(test_idx).dropna())
        for tr in res.trades:
            if pd.Timestamp(tr[0]) in test_dates:
                oos_trades_all.append(tr)
        rb, tb = restricted_counts(res, (test_idx[0], test_idx[-1])) if test_idx else (0, 0)
        restricted_bars += int(rb)
        total_bars += int(tb)
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
        oos = {
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
            "sharpe": float((bh_rets.mean() / vol) * (252**0.5)) if vol > 0 else float("nan"),
            "max_dd": float((bh_chain / bh_chain.cummax() - 1.0).min()),
        }
    return {"oos": oos, "buy_hold_oos": bh, "oos_trades": oos_trades_all}


DEFAULT_LOSS_MITIGATION_SPECS: List[Dict[str, Any]] = [
    {"id": "baseline_sma", "overlay": "none"},
    {"id": "trend_filter_sma200", "overlay": "trend_ma", "trend_ma": 200},
    {
        "id": "stop5_dd12_vol08",
        "overlay": "risk_tight",
        "stop_loss_pct": 5.0,
        "drawdown_limit_pct": 12.0,
        "target_vol": 0.08,
    },
]


def run_loss_mitigation_research(
    settings: AppSettings,
    data: Mapping[str, pd.DataFrame],
    symbol: str,
    specs: Sequence[Mapping[str, Any]] | None = None,
    direction: str | None = None,
    n_folds: int = 3,
    fast: int = 10,
    slow: int = 30,
) -> List[Dict[str, Any]]:
    """Compare baseline SMA vs loss-mitigation overlays on stitched OOS.

    Gate lockout fraction (``restricted_bar_frac``) is the share of OOS bars on
    which the engine's RiskManager would have blocked new exposure.
    """
    direction = direction or settings.trading.direction
    grid = list(specs) if specs is not None else list(DEFAULT_LOSS_MITIGATION_SPECS)
    results: List[Dict[str, Any]] = []
    baseline_dd: Optional[float] = None

    for spec in grid:
        sid = str(spec.get("id") or "overlay")
        overlay = str(spec.get("overlay") or "none")
        s_run = settings
        if overlay == "trend_ma":
            strat: Strategy = TrendFilteredSMA(fast=fast, slow=slow, trend_ma=int(spec.get("trend_ma") or 200))
        elif overlay == "risk_tight":
            s_run = _with_risk_overlay(
                settings,
                stop_loss_pct=float(spec.get("stop_loss_pct") or 5.0),
                drawdown_limit_pct=float(spec.get("drawdown_limit_pct") or 12.0),
                target_vol=float(spec.get("target_vol") or 0.08),
            )
            strat = SMACrossover(fast_window=fast, slow_window=slow)
        else:
            strat = SMACrossover(fast_window=fast, slow_window=slow)

        pack = _anchored_oos(s_run, data, symbol, strat, direction=direction, n_folds=n_folds)
        oos = pack["oos"]
        bh = pack["buy_hold_oos"]
        gate = evaluate_gates_with_restricted_frac(oos, bh)
        dd = oos.get("max_dd")
        try:
            dd_f = float(dd) if dd is not None else float("nan")
        except (TypeError, ValueError):
            dd_f = float("nan")
        if overlay == "none" and dd_f == dd_f:
            baseline_dd = dd_f
        dd_improved = None
        if baseline_dd is not None and dd_f == dd_f:
            # Less negative DD is an improvement
            dd_improved = bool(dd_f > baseline_dd + 1e-12)

        results.append(
            {
                "candidate_id": f"lossmit_{sid}",
                "params": {
                    "family": "loss_mitigation",
                    "overlay": overlay,
                    "fast": int(fast),
                    "slow": int(slow),
                    **{k: v for k, v in dict(spec).items() if k not in {"id", "overlay"}},
                },
                "oos": oos,
                "buy_hold_oos": bh,
                "oos_total_trades": len(pack["oos_trades"]),
                "oos_commission_approx": oos.get("total_commission"),
                "gate_passed": gate.passed,
                "gate_reasons": list(gate.reasons),
                "gate_checks": dict(gate.checks),
                "dd_improved_vs_baseline": dd_improved,
            }
        )
    return results


def summarize_loss_mitigation(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Digest which overlays improved drawdown vs baseline."""
    improved = [r.get("candidate_id") for r in rows if r.get("dd_improved_vs_baseline") is True]
    return {
        "n": len(rows),
        "overlays_improved_dd": improved,
        "any_dd_improvement": bool(improved),
        "note": (
            "DD improvement without gate PASS is still useful research: "
            "loss mitigation can reject fragile gross edge. Not a profit claim."
        ),
    }
