from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from ..config import CommissionConfig, SlippageConfig
from ..logging import setup_logging
from ..strategy.base import Strategy
from .metrics import PerformanceStats, compute_stats

log = setup_logging()


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    positions: Dict[str, pd.Series]
    trades: List[Tuple[str, str, int, float]]  # (date, symbol, qty, price)
    stats: PerformanceStats


def _commission(commission_cfg: CommissionConfig, qty: int, price: float) -> float:
    per_share = commission_cfg.per_share * abs(qty)
    ad_valorem = commission_cfg.percent_of_value / 100.0 * abs(qty) * price
    return max(per_share + ad_valorem, commission_cfg.min_per_order)


def _slip(slippage_cfg: SlippageConfig, price: float, side: int) -> float:
    bps = slippage_cfg.bps / 10000.0
    return price * (1 + bps * side)


def backtest(
    data: Dict[str, pd.DataFrame],
    strategy: Strategy,
    commission_cfg: CommissionConfig,
    slippage_cfg: SlippageConfig,
    initial_equity: float = 100_000.0,
    position_size_pct: float = 100.0,
) -> BacktestResult:
    # Prepare signals
    signals = strategy.generate_signals(data)
    # Align dates
    all_dates = sorted(set().union(*[df.index for df in data.values()]))
    positions: Dict[str, pd.Series] = {
        sym: pd.Series(0, index=all_dates, dtype=int) for sym in data
    }
    cash = initial_equity
    holdings: Dict[str, int] = {sym: 0 for sym in data}
    trades: List[Tuple[str, str, int, float]] = []
    equity_curve = []
    returns = []
    prev_equity = initial_equity
    for dt in all_dates:
        # Price snapshot
        prices = {
            sym: float(data[sym].reindex([dt])["close"].iloc[0])
            for sym in data
            if dt in data[sym].index
        }
        # Target generation: full allocation equally distributed among positive signals
        longs = [
            sym for sym, s in signals.items() if int(s.reindex([dt]).fillna(0).iloc[0]) > 0
        ]
        shorts = [
            sym for sym, s in signals.items() if int(s.reindex([dt]).fillna(0).iloc[0]) < 0
        ]
        targets: Dict[str, int] = {sym: 0 for sym in data}
        n_active = len(longs) + len(shorts)
        alloc_per = (position_size_pct / 100.0) / max(n_active, 1)
        for sym in longs:
            if sym in prices:
                qty = int(
                    (cash + sum(holdings[s] * prices.get(s, 0) for s in holdings))
                    * alloc_per
                    / prices[sym]
                )
                targets[sym] = max(qty, 0)
        for sym in shorts:
            if sym in prices:
                qty = int(
                    (cash + sum(holdings[s] * prices.get(s, 0) for s in holdings))
                    * alloc_per
                    / prices[sym]
                )
                targets[sym] = -max(qty, 0)
        # Rebalance toward targets (simple market orders at close with slippage)
        for sym, target in targets.items():
            price = prices.get(sym)
            if price is None:
                continue
            pos = holdings.get(sym, 0)
            delta = target - pos
            if delta == 0:
                continue
            side = 1 if delta > 0 else -1
            fill_price = _slip(slippage_cfg, price, side)
            commission = _commission(commission_cfg, delta, fill_price)
            cash -= delta * fill_price + commission
            holdings[sym] = pos + delta
            trades.append((str(dt), sym, int(delta), float(fill_price)))
        # Mark-to-market
        equity = cash + sum(qty * prices.get(sym, 0.0) for sym, qty in holdings.items())
        equity_curve.append((dt, equity))
        ret = (equity / prev_equity - 1.0) if prev_equity else 0.0
        # If flat everywhere, set return zero to help exposure proxy
        if all(qty == 0 for qty in holdings.values()):
            ret = 0.0
        returns.append((dt, ret))
        prev_equity = equity
        # Record positions
        for sym in data.keys():
            positions[sym].loc[dt] = holdings.get(sym, 0)
    equity_series = pd.Series({dt: eq for dt, eq in equity_curve}).sort_index()
    returns_series = pd.Series({dt: r for dt, r in returns}).sort_index()
    stats = compute_stats(equity_series, returns_series)
    return BacktestResult(
        equity_curve=equity_series,
        returns=returns_series,
        positions=positions,
        trades=trades,
        stats=stats,
    )

