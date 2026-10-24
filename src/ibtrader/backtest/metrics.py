from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 252


@dataclass
class CostTotals:
    """Running sums of execution costs across every fill of a backtest (USD)."""

    commission: float = 0.0
    reg_fees: float = 0.0
    half_spread: float = 0.0
    impact: float = 0.0
    n_orders: int = 0
    notional: float = 0.0

    @property
    def total(self) -> float:
        return float(self.commission + self.reg_fees + self.half_spread + self.impact)

    def add(self, order_cost: Any) -> None:
        """Accumulate an ``ibtrader.execution.costs.OrderCost`` (duck-typed to avoid a cycle)."""
        self.commission += float(order_cost.commission)
        self.reg_fees += float(order_cost.reg_fees)
        self.half_spread += float(order_cost.half_spread)
        self.impact += float(order_cost.impact)
        self.n_orders += 1
        self.notional += float(order_cost.notional)


@dataclass
class PerformanceStats:
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float  # daily win rate
    exposure: float
    total_return: float
    volatility: float
    trade_count: int = 0
    total_commission: float = 0
    turnover: float = 0.0
    win_rate_trades: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    calmar: float = 0.0
    recovery_factor: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    current_underwater_days: int = 0
    max_underwater_days: int = 0
    # Execution-cost breakdown (USD unless noted). See COST_MODEL.md.
    total_slippage: float = 0.0  # half-spread paid (flat bps when slippage model == "bps")
    total_impact: float = 0.0
    total_reg_fees: float = 0.0
    total_costs: float = 0.0  # commission + reg fees + slippage + impact
    n_orders: int = 0
    notional_traded: float = 0.0
    avg_cost_bps_per_order: float = 0.0  # total_costs / notional_traded * 1e4
    cost_drag_annual_pct: float = 0.0  # total_costs / initial equity / years * 100


COST_METRIC_FIELDS = (
    "total_commission",
    "total_slippage",
    "total_impact",
    "total_reg_fees",
    "total_costs",
    "n_orders",
    "notional_traded",
    "avg_cost_bps_per_order",
    "cost_drag_annual_pct",
    "turnover",
)


def attach_cost_metrics(
    stats: PerformanceStats,
    costs: CostTotals,
    *,
    initial_equity: float,
    n_periods: int,
    periods_per_year: int = PERIODS_PER_YEAR,
) -> PerformanceStats:
    """Fill the cost fields of ``stats`` from ``costs`` (in place; returned for chaining)."""
    stats.total_commission = float(costs.commission)
    stats.total_reg_fees = float(costs.reg_fees)
    stats.total_slippage = float(costs.half_spread)
    stats.total_impact = float(costs.impact)
    stats.total_costs = float(costs.total)
    stats.n_orders = int(costs.n_orders)
    stats.notional_traded = float(costs.notional)
    stats.avg_cost_bps_per_order = (
        float(costs.total / costs.notional * 1e4) if costs.notional > 0.0 else 0.0
    )
    years = max(int(n_periods), 1) / float(periods_per_year)
    stats.cost_drag_annual_pct = (
        float(costs.total / float(initial_equity) / years * 100.0)
        if initial_equity and initial_equity > 0.0 and years > 0.0
        else 0.0
    )
    return stats


def cost_metrics_dict(stats: PerformanceStats) -> Dict[str, Any]:
    """Only the execution-cost metrics (for JSON artifacts and HTML reports)."""
    return {k: getattr(stats, k) for k in COST_METRIC_FIELDS}




OOS_COST_METRIC_KEYS = ("avg_cost_bps_per_order", "cost_drag_annual_pct")


def copy_oos_cost_metrics(into: Dict[str, Any], source: Any) -> Dict[str, Any]:
    """Copy OOS cost headline fields from backtest PerformanceStats or a mapping."""
    if source is None:
        return into
    for key in OOS_COST_METRIC_KEYS:
        raw = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val == val:
            into[key] = val
    return into

def stats_to_dict(stats: PerformanceStats) -> Dict[str, Any]:
    """Every metric as a plain dict (dataclass fields, JSON-friendly scalars)."""
    return dict(asdict(stats))


def compute_stats(
    equity_curve: pd.Series,
    returns: pd.Series,
    rf: float = 0.0,
    *,
    costs: Optional[CostTotals] = None,
    initial_equity: Optional[float] = None,
) -> PerformanceStats:
    """Performance metrics from an equity curve; with ``costs`` also the cost breakdown.

    ``initial_equity`` defaults to the first point of ``equity_curve`` and is the base
    of ``cost_drag_annual_pct``.
    """
    equity_curve = equity_curve.dropna()
    returns = returns.loc[equity_curve.index].fillna(0.0)
    if equity_curve.index.freq == "B":
        periods_per_year = PERIODS_PER_YEAR
    else:
        # Approximate by daily
        periods_per_year = PERIODS_PER_YEAR
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0
    n_periods = max(len(returns), 1)
    cagr = (1 + total_return) ** (periods_per_year / n_periods) - 1 if n_periods > 0 else 0.0
    vol = float(returns.std(ddof=0) * np.sqrt(periods_per_year))
    downside = returns[returns < 0]
    downside_vol = float(downside.std(ddof=0) * np.sqrt(periods_per_year)) if len(downside) else 0.0
    # Undefined risk-adjusted ratios must stay NaN (not 0.0) so reporters can emit null.
    _nan = float("nan")
    if vol == 0.0 or not np.isfinite(vol):
        sharpe = _nan
    else:
        sharpe = float((returns.mean() * periods_per_year - rf) / vol)
    if len(downside) == 0 or downside_vol <= 0.0 or not np.isfinite(downside_vol):
        sortino = _nan
    else:
        sortino = float((returns.mean() * periods_per_year - rf) / downside_vol)
    # drawdown
    roll_max = equity_curve.cummax()
    dd = equity_curve / roll_max - 1.0
    max_drawdown = float(dd.min())
    # underwater durations
    underwater = dd < 0
    max_underwater_days = 0
    cur = 0
    for is_uw in underwater:
        if is_uw:
            cur += 1
            if cur > max_underwater_days:
                max_underwater_days = cur
        else:
            cur = 0
    current_underwater_days = cur
    # win rate
    wins = (returns > 0).sum()
    win_rate = float(wins) / float(len(returns)) if len(returns) else 0.0
    # exposure: fraction of time invested (assumes signal != 0 means invested)
    # For now approximate by non-zero returns (backtest sets to 0 when flat)
    exposure = float((returns != 0).sum()) / float(len(returns)) if len(returns) else 0.0
    # tail risk (historical)
    var_95 = float(np.percentile(returns.dropna().values, 5)) if len(returns.dropna()) else 0.0
    cvar_95 = float(returns[returns <= var_95].mean()) if len(returns.dropna()) else 0.0
    # calmar & recovery
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else _nan
    recovery_factor = float(total_return / abs(max_drawdown)) if max_drawdown < 0 else _nan
    stats = PerformanceStats(
        cagr=float(cagr),
        sharpe=float(sharpe),
        sortino=float(sortino),
        max_drawdown=float(max_drawdown),
        win_rate=float(win_rate),
        exposure=float(exposure),
        total_return=float(total_return),
        volatility=float(vol),
        calmar=calmar,
        recovery_factor=recovery_factor,
        var_95=var_95,
        cvar_95=cvar_95,
        current_underwater_days=int(current_underwater_days),
        max_underwater_days=int(max_underwater_days),
    )
    if costs is not None:
        base_equity = (
            float(initial_equity)
            if initial_equity is not None
            else float(equity_curve.iloc[0]) if len(equity_curve) else 0.0
        )
        attach_cost_metrics(
            stats,
            costs,
            initial_equity=base_equity,
            n_periods=len(returns),
            periods_per_year=periods_per_year,
        )
    return stats

