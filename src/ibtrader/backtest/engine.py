from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from ..config import CommissionConfig, SlippageConfig
from ..logging import setup_logging
from ..risk.manager import RiskManager
from ..risk.sizing import volatility_target_weight
from ..strategy.base import Strategy
from .metrics import PerformanceStats, compute_stats

log = setup_logging()


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    positions: Dict[str, pd.Series]
    # (date, symbol, qty, price, reason)
    trades: List[Tuple[str, str, int, float, str]]
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
    trades: List[Tuple[str, str, int, float, str]] = []
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
    # Per-run cooldown (no cross-run contamination)
    cooldown_until: Dict[str, int] = {}
    # Close-based stop scheduling: decide at bar close, execute at next open
    stop_scheduled: Dict[str, bool] = {sym: False for sym in data}
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
                ro_val = risk_on.reindex([dt_prev]).iloc[0]
                # During warm-up (regime unknown / NaN), do not apply veto implicitly
                if pd.notna(ro_val) and float(ro_val) < risk_on_threshold:
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
                    # Use symbol history up to dt_prev for realized vol
                    hist_series = data[sym]["close"].astype(float)
                    hist_series = hist_series.loc[:dt_prev]
                    rets = hist_series.pct_change().fillna(0.0)
                    vt = volatility_target_weight(rets, target_vol_annual=target_vol_annual)
                w = base_alloc * vt * (1 if raw_sign[sym] > 0 else -1)
                # Compute against slippage-adjusted estimated fill to avoid oversizing
                est_fill = _slip(slippage_cfg, open_now[sym], 1 if w >= 0 else -1)
                qty = int(nav_prev * abs(w) / est_fill) if est_fill > 0 else 0
                proposed = qty if w >= 0 else -qty
                # Only trade on signal changes, or when drift exceeds band (if configured)
                prev_target = last_targets.get(sym, 0)
                sign_change = (prev_target == 0 and proposed != 0) or (prev_target * proposed < 0)
                if not sign_change and rebalance_band_pct <= 0.0:
                    proposed = prev_target
                targets[sym] = proposed
        # Execute at today's open
        # Cooldown tracking is per-run via local cooldown_until dict (no shared/module state)
        for sym, target in targets.items():
            price = open_now.get(sym)
            if price is None:
                continue
            pos = holdings.get(sym, 0)
            # Handle a previously scheduled stop-loss exit at the open, before anything else
            if risk_manager is not None and stop_scheduled.get(sym, False) and pos != 0:
                side_exit = -1 if pos > 0 else 1
                fill_exit = _slip(slippage_cfg, price, side_exit)
                comm_exit = _commission(commission_cfg, -pos, fill_exit)
                cash -= (-pos) * fill_exit + comm_exit
                turnover_notional += abs(pos) * fill_exit
                total_commission += comm_exit
                # Book realized P&L for full close
                reduce_qty = abs(pos)
                pnl = (
                    reduce_qty * (fill_exit - avg_price[sym]) - comm_exit
                    if pos > 0
                    else reduce_qty * (avg_price[sym] - fill_exit) - comm_exit
                )
                cur_trade_pnl[sym] = cur_trade_pnl.get(sym, 0.0) + pnl
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
                avg_price[sym] = 0.0
                holdings[sym] = 0
                stop_scheduled[sym] = False
                trades.append((str(dt), sym, int(-pos), float(fill_exit), "stop_loss"))
                last_targets[sym] = 0
                # Enter cooldown if configured
                if risk_manager.cfg.cooldown_bars > 0:
                    cooldown_until[sym] = i + int(risk_manager.cfg.cooldown_bars) + 1
                # Do not attempt any other action on this symbol today
                continue
            # Emergency flatten via kill-switch (if configured): must run before any other gating
            if risk_manager is not None and pos != 0:
                try:
                    if hasattr(risk_manager, "killswitch_active") and risk_manager.killswitch_active():
                        ks_action = getattr(risk_manager.cfg, "killswitch_action", "flatten")
                        if ks_action == "flatten" and risk_manager.cfg.emergency_flatten_on_kill:
                            side_exit = -1 if pos > 0 else 1
                            fill_exit = _slip(slippage_cfg, price, side_exit)
                            comm_exit = _commission(commission_cfg, -pos, fill_exit)
                            cash -= (-pos) * fill_exit + comm_exit
                            turnover_notional += abs(pos) * fill_exit
                            total_commission += comm_exit
                            # Book realized P&L for full close
                            reduce_qty = abs(pos)
                            pnl = (
                                reduce_qty * (fill_exit - avg_price[sym]) - comm_exit
                                if pos > 0
                                else reduce_qty * (avg_price[sym] - fill_exit) - comm_exit
                            )
                            cur_trade_pnl[sym] = cur_trade_pnl.get(sym, 0.0) + pnl
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
                            avg_price[sym] = 0.0
                            holdings[sym] = 0
                            log.info("forced_exit reason=kill_switch sym=%s qty=%s", sym, int(-pos))
                            trades.append((str(dt), sym, int(-pos), float(fill_exit), "kill_switch"))
                            last_targets[sym] = 0
                            if risk_manager.cfg.cooldown_bars > 0:
                                cooldown_until[sym] = i + int(risk_manager.cfg.cooldown_bars) + 1
                            # Do not attempt any other action on this symbol today
                            continue
                except Exception:
                    pass
            # Forced exits (stop/emergency) must run even if target==pos
            force_close = False
            is_emergency = False
            if risk_manager is not None:
                # Emergency flatten via killswitch if configured (apply only when holding)
                # Emergency flatten via killswitch if configured (apply only when holding)
                try:
                    if hasattr(risk_manager, "killswitch_active") and risk_manager.killswitch_active() and pos != 0:
                        ks_action = getattr(risk_manager.cfg, "killswitch_action", "flatten")
                        if ks_action == "flatten" and risk_manager.cfg.emergency_flatten_on_kill:
                            force_close = True
                            is_emergency = True
                except Exception:
                    pass
                # (Open-time stop processing removed; stops are scheduled at prior close)
            if force_close:
                target = 0
            delta = target - pos
            # After forced exit, respect cooldown before reopening
            # Set cooldown on forced exit
            if force_close and risk_manager is not None and risk_manager.cfg.cooldown_bars > 0:
                cooldown_until[sym] = i + int(risk_manager.cfg.cooldown_bars) + 1
            # Hard gate: if daily-loss halt is active, block new opens/increases entirely
            if risk_manager is not None and risk_manager.state.halted:
                if (pos == 0 and delta != 0) or (pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))):
                    delta = 0
                    target = pos
            # Enforce cooldown gating for new opens
            if (
                pos == 0
                and delta != 0
                and sym in cooldown_until
                and isinstance(cooldown_until[sym], int)
                and i < int(cooldown_until[sym])
            ):
                delta = 0
                target = 0
            # Also enforce daily-loss hard-gate based on previous day's return
            if risk_manager is not None and delta != 0:
                try:
                    # Prefer equity_curve chain to avoid reliance on returns list contents
                    if len(equity_curve) >= 2:
                        eq_y = float(equity_curve[-1][1])
                        eq_y_1 = float(equity_curve[-2][1])
                        prev_ret = (eq_y / eq_y_1 - 1.0) if eq_y_1 else 0.0
                    else:
                        prev_ret = float(returns[-1][1]) if returns else 0.0
                    if prev_ret <= -abs(risk_manager.cfg.daily_loss_limit_pct) / 100.0:
                        if (pos == 0) or (pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))):
                            delta = 0
                            target = pos
                except Exception:
                    pass
            # Hard gate: if drawdown restriction is active, block exposure-increasing orders
            if risk_manager is not None and delta != 0:
                try:
                    # Evaluate drawdown at open-equity
                    eq_open_now = cash + sum(holdings[s] * open_now.get(s, 0.0) for s in holdings)
                    ok_dd, _ = risk_manager.check_drawdown(float(eq_open_now))
                    exposure_increasing = (pos == 0 and delta != 0) or (
                        pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))
                    )
                    if (not ok_dd) and exposure_increasing:
                        delta = 0
                        target = pos
                except Exception:
                    pass
            if delta == 0:
                continue
            if pos != 0 and rebalance_band_pct > 0:
                rel_change = abs(delta) / max(1, abs(pos))
                if rel_change < rebalance_band_pct:
                    continue
            side = 1 if delta > 0 else -1
            # Use slippage-adjusted estimate for sizing checks
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
            # Risk manager veto (optional) with flip handling
            if risk_manager is not None:
                eq_prev = nav_prev
                # Value equity at current open to evaluate daily loss vs start-of-day
                eq_open = cash + sum(holdings[s] * open_now.get(s, 0.0) for s in holdings)
                cur_pos_val = sum(holdings[s] * close_prev.get(s, 0.0) for s in holdings)
                # Detect flip
                is_flip = pos != 0 and target != 0 and (pos > 0 > target or pos < 0 < target)
                # If forced close, bypass risk checks for the close leg (always allowed)
                if force_close and pos != 0:
                    dclose = -pos
                    dfill = _slip(slippage_cfg, price, (1 if dclose > 0 else -1))
                    dcomm = _commission(commission_cfg, dclose, dfill)
                    cash -= dclose * dfill + dcomm
                    holdings[sym] = 0
                    turnover_notional += abs(dclose) * dfill
                    total_commission += dcomm
                    reduce_qty = abs(pos)
                    pnl = (dfill - avg_price[sym]) * reduce_qty if pos > 0 else (avg_price[sym] - dfill) * reduce_qty
                    pnl -= dcomm
                    cur_trade_pnl[sym] = cur_trade_pnl.get(sym, 0.0) + pnl
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
                    avg_price[sym] = 0.0
                    trades.append(
                        (
                            str(dt),
                            sym,
                            int(dclose),
                            float(dfill),
                            "kill_switch" if is_emergency else "stop_loss",
                        )
                    )
                    last_targets[sym] = 0
                    if risk_manager is not None:
                        risk_manager.notify_order_sent()
                    continue
                if is_flip:
                    # Try full flip first
                    ok, msg = risk_manager.approve_order(
                        symbol=sym,
                        equity=eq_open,
                        price=fill_price,
                        quantity=int(delta),
                        current_positions_value=float(cur_pos_val),
                        current_position_qty=int(pos),
                    )
                    if not ok:
                        # Attempt close-only leg; open leg vetoed
                        delta_close = -pos
                        okc, msgc = risk_manager.approve_order(
                            symbol=sym,
                            equity=eq_prev,
                            price=_slip(slippage_cfg, price, (1 if delta_close > 0 else -1)),
                            quantity=int(delta_close),
                            current_positions_value=float(cur_pos_val),
                            current_position_qty=int(pos),
                            is_stop=False,
                            is_emergency=is_emergency,
                        )
                        if okc and delta_close != 0:
                            # Execute close-only
                            dfill = _slip(slippage_cfg, price, (1 if delta_close > 0 else -1))
                            dcomm = _commission(commission_cfg, delta_close, dfill)
                            cash -= delta_close * dfill + dcomm
                            holdings[sym] = 0
                            turnover_notional += abs(delta_close) * dfill
                            total_commission += dcomm
                            # Bookkeeping for realized P&L on full close
                            reduce_qty = min(abs(delta_close), abs(pos))
                            if pos > 0 and delta_close < 0:
                                pnl = reduce_qty * (dfill - avg_price[sym]) - dcomm
                            elif pos < 0 and delta_close > 0:
                                pnl = reduce_qty * (avg_price[sym] - dfill) - dcomm
                            else:
                                pnl = 0.0
                            cur_trade_pnl[sym] = cur_trade_pnl.get(sym, 0.0) + pnl
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
                            avg_price[sym] = 0.0
                            trades.append((str(dt), sym, int(delta_close), float(dfill), "flip_close_only"))
                            last_targets[sym] = 0
                            if risk_manager is not None:
                                risk_manager.notify_order_sent()
                            # Skip open leg
                            continue
                        else:
                            log.info("risk_veto_flip sym=%s reason=%s", sym, msg)
                            continue
                else:
                    ok, msg = risk_manager.approve_order(
                        symbol=sym,
                        equity=eq_open,
                        price=fill_price,
                        quantity=int(delta),
                        current_positions_value=float(cur_pos_val),
                        current_position_qty=int(pos),
                        is_stop=force_close,
                        is_emergency=is_emergency,
                    )
                    if not ok:
                        log.info("risk_veto sym=%s reason=%s", sym, msg)
                        continue
                    # Final hard-gate before execution: block any exposure-increasing order under daily halt
                    try:
                        prev_ret_exec = 0.0
                        if len(equity_curve) >= 2:
                            eq_y = float(equity_curve[-1][1])
                            eq_y_1 = float(equity_curve[-2][1])
                            prev_ret_exec = (eq_y / eq_y_1 - 1.0) if eq_y_1 else 0.0
                        daily_limit = abs(risk_manager.cfg.daily_loss_limit_pct) / 100.0
                        if risk_manager.state.halted or (prev_ret_exec <= -daily_limit):
                            exposure_increasing = (pos == 0 and delta != 0) or (
                                pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))
                            )
                            if exposure_increasing:
                                log.info("risk_veto sym=%s reason=daily_halt_hard_gate", sym)
                                continue
                    except Exception:
                        pass
            # Execute order
            cash -= delta * fill_price + commission
            holdings[sym] = pos + delta
            turnover_notional += abs(delta) * fill_price
            total_commission += commission
            if risk_manager is not None:
                risk_manager.notify_order_sent()
            if force_close:
                reason = "kill_switch" if is_emergency else "stop_loss"
                log.info("forced_exit reason=%s sym=%s qty=%s", reason, sym, int(delta))
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
            trades.append((str(dt), sym, int(delta), float(fill_price), "signal"))
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
        # Decide close-based stop for next bar (schedule)
        if risk_manager is not None and float(risk_manager.cfg.stop_loss_per_position_pct or 0.0) > 0.0:
            stop_frac = float(risk_manager.cfg.stop_loss_per_position_pct) / 100.0
            for sym in data.keys():
                pos_now = holdings.get(sym, 0)
                if pos_now == 0 or avg_price.get(sym, 0.0) <= 0.0:
                    continue
                thresh = (
                    avg_price[sym] * (1 - stop_frac) if pos_now > 0 else avg_price[sym] * (1 + stop_frac)
                )
                px_close = close_today.get(sym, None)
                if px_close is None:
                    continue
                if (pos_now > 0 and px_close <= thresh) or (pos_now < 0 and px_close >= thresh):
                    stop_scheduled[sym] = True
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

