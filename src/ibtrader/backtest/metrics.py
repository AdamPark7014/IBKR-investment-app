from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


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


def compute_stats(
    equity_curve: pd.Series, returns: pd.Series, rf: float = 0.0
) -> PerformanceStats:
    equity_curve = equity_curve.dropna()
    returns = returns.loc[equity_curve.index].fillna(0.0)
    if equity_curve.index.freq == "B":
        periods_per_year = 252
    else:
        # Approximate by daily
        periods_per_year = 252
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0
    n_periods = max(len(returns), 1)
    cagr = (1 + total_return) ** (periods_per_year / n_periods) - 1 if n_periods > 0 else 0.0
    vol = float(returns.std(ddof=0) * np.sqrt(periods_per_year))
    downside = returns[returns < 0]
    downside_vol = float(downside.std(ddof=0) * np.sqrt(periods_per_year)) or 1e-9
    sharpe = 0.0 if vol == 0 else float((returns.mean() * periods_per_year - rf) / vol)
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
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0
    recovery_factor = float(total_return / abs(max_drawdown)) if max_drawdown < 0 else 0.0
    return PerformanceStats(
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

