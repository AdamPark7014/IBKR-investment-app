from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from ..config import CommissionConfig, SlippageConfig
from ..logging import setup_logging
from ..strategy.base import Strategy
from .metrics import PerformanceStats, compute_stats
from ..risk.sizing import volatility_target_weight
from ..risk.manager import RiskManager

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
    rebalance_band_pct: float = 0.0,
    benefit_bps: float = 0.0,
    risk_cost_bps: float = 0.0,
    # Risk integration (optional)
    direction: str | None = None,  # long_only | short_only | long_short
    risk_on: pd.Series | None = None,  # 0/1 series aligned to dates (dt_prev)
    risk_on_threshold: float = 0.0,
    target_vol_annual: float | None = None,
    risk_manager: RiskManager | None = None,
) -> BacktestResult:
    # Validate band units
    if rebalance_band_pct < 0.0 or rebalance_band_pct > 1.0:
        raise ValueError("rebalance_band_pct debe estar en [0,1]. Usa fracción (e.g., 0.02 para 2%).")
    # Prepare signals
    signals = strategy.generate_signals(data)
    # Align dates
    all_dates = sorted(set().union(*[df.index for df in data.values()]))
    positions: Dict[str, pd.Series] = {
        sym: pd.Series(0, index=all_dates, dtype=int) for sym in data
    }
    cash = initial_equity
    holdings: Dict[str, int] = {sym: 0 for sym in data}
    avg_price: Dict[str, float] = {sym: 0.0 for sym in data}
    trades: List[Tuple[str, str, int, float]] = []
    equity_curve = []
    returns = []
    prev_equity = initial_equity
    # Track last executed targets to reduce churn
    last_targets: Dict[str, int] = {sym: 0 for sym in data}
    total_commission = 0.0
    turnover_notional = 0.0
    realized_pnl = 0.0
    realized_wins = 0.0
    realized_losses = 0.0
    realized_trades = 0
    # Accumulate partial P&L per open trade; finalize on round-trip close
    cur_trade_pnl: Dict[str, float] = {sym: 0.0 for sym in data}
    win_trades = 0
    loss_trades = 0
    for i, dt in enumerate(all_dates):
        if i == 0:
            # No execution possible on first bar; mark-to-market at close
            close_prices = {
                sym: float(data[sym].reindex([dt])["close"].iloc[0]) for sym in data if dt in data[sym].index
            }
            equity = cash + sum(qty * close_prices.get(sym, 0.0) for sym, qty in holdings.items())
            equity_curve.append((dt, equity))
            returns.append((dt, 0.0))
            prev_equity = equity
            for sym in data.keys():
                positions[sym].loc[dt] = holdings.get(sym, 0)
            continue
        dt_prev = all_dates[i - 1]
        # Reset daily risk state at day open
        if risk_manager is not None:
            # Use previous equity as starting equity for the day
            risk_manager.on_new_day(str(dt), float(prev_equity))
        close_prev = {
            sym: float(data[sym].reindex([dt_prev])["close"].iloc[0])
            for sym in data
            if dt_prev in data[sym].index
        }
        open_now = {
            sym: float(data[sym].reindex([dt])["open"].iloc[0])
            for sym in data
            if dt in data[sym].index
        }
        # Equal-weight targets based on signals at dt_prev
        # Build raw sign per symbol from signals with direction and risk gating
        raw_sign: Dict[str, int] = {}
        for sym, s in signals.items():
            sig = int(s.reindex([dt_prev]).fillna(0).iloc[0])
            # Enforce direction
            if direction == "long_only":
                sig = max(sig, 0)
            elif direction == "short_only":
                sig = min(sig, 0)
            # Risk-on veto
            if risk_on is not None:
                ro = float(risk_on.reindex([dt_prev]).fillna(1.0).iloc[0])
                if ro < risk_on_threshold:
                    sig = 0
            raw_sign[sym] = sig
        actives = [sym for sym, sign in raw_sign.items() if sign != 0]
        targets: Dict[str, int] = {sym: 0 for sym in data}
        n_active = len(actives)
        base_alloc = (position_size_pct / 100.0) / max(n_active, 1)
        nav_prev = cash + sum(holdings[s] * close_prev.get(s, 0.0) for s in holdings)
        for sym in actives:
            if sym in open_now and open_now[sym] > 0:
                # Volatility-target sizing factor (if enabled)
                vt = 1.0
                if target_vol_annual is not None and target_vol_annual > 0:
                    rets_hist = (
                        pd.Series(close_prev.get(sym, 0.0), index=[dt_prev])
                    )  # placeholder to satisfy typing
                    # Use symbol history up to dt_prev for realized vol
                    hist_series = data[sym]["close"].astype(float)
                    hist_series = hist_series.loc[:dt_prev]
                    rets = hist_series.pct_change().fillna(0.0)
                    vt = volatility_target_weight(rets, target_vol_annual=target_vol_annual)
                w = base_alloc * vt * (1 if raw_sign[sym] > 0 else -1)
                qty = int(nav_prev * abs(w) / open_now[sym])
                proposed = qty if w >= 0 else -qty
                # Only trade on signal changes, or when drift exceeds band (if configured)
                prev_target = last_targets.get(sym, 0)
                sign_change = (prev_target == 0 and proposed != 0) or (prev_target * proposed < 0)
                if not sign_change and rebalance_band_pct <= 0.0:
                    proposed = prev_target
                targets[sym] = proposed
        # Execute at today's open
        for sym, target in targets.items():
            price = open_now.get(sym)
            if price is None:
                continue
            pos = holdings.get(sym, 0)
            delta = target - pos
            if delta == 0:
                continue
            if pos != 0 and rebalance_band_pct > 0:
                rel_change = abs(delta) / max(1, abs(pos))
                if rel_change < rebalance_band_pct:
                    continue
            side = 1 if delta > 0 else -1
            fill_price = _slip(slippage_cfg, price, side)
            commission = _commission(commission_cfg, delta, fill_price)
            if ((benefit_bps > 0.0) or (risk_cost_bps > 0.0)) and (pos != 0) and (target != 0) and (pos * target > 0):
                slippage_cost = abs(delta) * price * (slippage_cfg.bps / 10000.0)
                risk_cost = abs(delta) * price * (risk_cost_bps / 10000.0)
                expected_benefit = abs(delta) * price * (benefit_bps / 10000.0)
                total_cost = commission + slippage_cost + risk_cost
                if expected_benefit <= total_cost:
                    log.info(
                        "no_rebalance delta=%s sym=%s exp_benefit=%.4f total_cost=%.4f",
                        int(delta),
                        sym,
                        expected_benefit,
                        total_cost,
                    )
                    continue
            # Risk manager veto (optional)
            if risk_manager is not None:
                eq_prev = nav_prev
                cur_pos_val = sum(holdings[s] * close_prev.get(s, 0.0) for s in holdings)
                ok, msg = risk_manager.approve_order(
                    symbol=sym,
                    equity=eq_prev,
                    price=fill_price,
                    quantity=int(delta),
                    current_positions_value=float(cur_pos_val),
                    current_position_qty=int(pos),
                )
                if not ok:
                    log.info("risk_veto sym=%s reason=%s", sym, msg)
                    continue
            cash -= delta * fill_price + commission
            holdings[sym] = pos + delta
            turnover_notional += abs(delta) * fill_price
            total_commission += commission
            if risk_manager is not None:
                risk_manager.notify_order_sent()
            if pos == 0 or (pos > 0 and delta > 0) or (pos < 0 and delta < 0):
                # Opening/increasing: update average and include entry commission in trade bucket
                new_qty = pos + delta
                if new_qty != 0:
                    avg_price[sym] = (
                        (avg_price[sym] * pos + fill_price * delta) / new_qty
                        if pos != 0
                        else fill_price
                    )
                cur_trade_pnl[sym] = cur_trade_pnl.get(sym, 0.0) - commission
            else:
                reduce_qty = min(abs(delta), abs(pos))
                if pos > 0 and delta < 0:
                    pnl = reduce_qty * (fill_price - avg_price[sym]) - commission
                elif pos < 0 and delta > 0:
                    pnl = reduce_qty * (avg_price[sym] - fill_price) - commission
                else:
                    pnl = 0.0
                cur_trade_pnl[sym] = cur_trade_pnl.get(sym, 0.0) + pnl
                new_pos = pos + delta
                closed_round_trip = (new_pos == 0) or (pos * new_pos < 0)
                if closed_round_trip:
                    total_trade_pnl = cur_trade_pnl.get(sym, 0.0)
                    realized_pnl += total_trade_pnl
                    if total_trade_pnl > 0:
                        realized_wins += total_trade_pnl
                        win_trades += 1
                    elif total_trade_pnl < 0:
                        realized_losses += -total_trade_pnl
                        loss_trades += 1
                    realized_trades += 1
                    cur_trade_pnl[sym] = 0.0
                if new_pos == 0:
                    avg_price[sym] = 0.0
                elif (pos > 0 and new_pos < 0) or (pos < 0 and new_pos > 0):
                    avg_price[sym] = fill_price
            trades.append((str(dt), sym, int(delta), float(fill_price)))
            # Update last target after execution
            last_targets[sym] = target
        # Mark-to-market at today's close
        close_today = {
            sym: float(data[sym].reindex([dt])["close"].iloc[0])
            for sym in data
            if dt in data[sym].index
        }
        equity = cash + sum(qty * close_today.get(sym, 0.0) for sym, qty in holdings.items())
        equity_curve.append((dt, equity))
        ret = (equity / prev_equity - 1.0) if prev_equity else 0.0
        # Do not force zero returns; compute from equity curve directly
        returns.append((dt, ret))
        if risk_manager is not None:
            risk_manager.update_equity(float(equity))
        prev_equity = equity
        for sym in data.keys():
            positions[sym].loc[dt] = holdings.get(sym, 0)
    equity_series = pd.Series({dt: eq for dt, eq in equity_curve}).sort_index()
    returns_series = pd.Series({dt: r for dt, r in returns}).sort_index()
    stats = compute_stats(equity_series, returns_series)
    # Extend stats with trade-level metrics
    trade_count = len(trades)
    profit_factor = (realized_wins / realized_losses) if realized_losses > 0 else 0.0
    expectancy = (realized_pnl / realized_trades) if realized_trades > 0 else 0.0
    stats.trade_count = trade_count
    stats.total_commission = float(total_commission)
    stats.turnover = float(turnover_notional / initial_equity if initial_equity else 0.0)
    stats.win_rate_trades = float((win_trades / realized_trades) if realized_trades > 0 else 0.0)
    # use pnl share separately through profit_factor
    stats.profit_factor = float(profit_factor)
    stats.expectancy = float(expectancy)
    return BacktestResult(
        equity_curve=equity_series,
        returns=returns_series,
        positions=positions,
        trades=trades,
        stats=stats,
    )

