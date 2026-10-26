from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from ..config import CommissionConfig, RegFeesConfig, SlippageConfig
from ..execution.costs import (
    OrderCost,
    estimated_fill_price,
    rolling_adv_and_sigma,
    slippage_legacy_bps,
    total_order_cost,
)
from ..execution.costs import (
    commission as _commission_cost,
)
from ..logging import setup_logging
from ..risk.manager import RiskManager
from ..risk.sizing import volatility_target_weight
from ..risk.state_machine import RiskState as RiskFSMState
from ..strategy.base import Strategy
from .metrics import CostTotals, PerformanceStats, compute_stats
from .reasons import TradeReason

log = setup_logging()


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    positions: Dict[str, pd.Series]
    # (date, symbol, qty, price, exit_reason)
    trades: List[Tuple[str, str, int, float, str]]
    stats: PerformanceStats
    # Per-bar lockout flag (bool, same index as equity_curve): True when the
    # RiskManager would block new exposure on that bar. All False without a
    # risk manager; a failed probe marks the bar True (fail-closed).
    restricted: pd.Series = field(default_factory=lambda: pd.Series(dtype=bool))
    # Every executed order with its all-in cost: (bar date, OrderCost). Lets callers sum costs over a
    # window (an OOS test segment) instead of the whole backtest including its warm-up.
    order_costs: List[Tuple[Any, OrderCost]] = field(default_factory=list)


def _probe_restricted(risk_manager: RiskManager | None) -> bool:
    """Read-only probe: would the risk manager block new exposure right now?

    True on daily halt, any non-NORMAL FSM state or an active kill switch.
    Any exception while probing is treated as restricted (fail-closed). The
    probe never mutates risk state, so it cannot change fills or metrics.
    """
    if risk_manager is None:
        return False
    try:
        if bool(risk_manager.state.halted):
            return True
        fsm = getattr(risk_manager, "fsm", None)
        if fsm is not None and fsm.state != RiskFSMState.NORMAL:
            return True
        if risk_manager.killswitch_active():
            return True
        return False
    except Exception as exc:
        log.warning("risk_fail_closed restricted_probe err=%s", exc)
        return True


def restricted_counts(
    res: BacktestResult,
    window: slice | Tuple[Any, Any] | None = None,
) -> Tuple[int, int]:
    """Return ``(restricted_bars, total_bars)`` from ``res.restricted``.

    ``window`` selects a sub-range by index label: ``None`` for the whole
    series, a ``slice(start, stop)`` of labels, or an inclusive ``(start, end)``
    tuple (either end may be ``None``). Missing/NaN values inside the window
    count as restricted (fail-closed). Returns ``(0, 0)`` when nothing is
    selected.
    """
    series = getattr(res, "restricted", None)
    if series is None or len(series) == 0:
        return 0, 0
    sel = series
    if window is not None:
        if isinstance(window, slice):
            sel = sel.loc[window]
        else:
            start, end = window
            sel = sel.loc[start:end]
    total = int(len(sel))
    if total == 0:
        return 0, 0
    restricted = int(sel.fillna(True).astype(bool).sum())
    return restricted, total


def _commission(commission_cfg: CommissionConfig, qty: int, price: float) -> float:
    """Commission for one fill (delegates to ``execution.costs.commission``)."""
    return _commission_cost(commission_cfg, qty, price)


def _slip(slippage_cfg: SlippageConfig, price: float, side: int) -> float:
    """Legacy flat-bps fill (``slippage.model == "bps"``); kept for callers/tests."""
    return slippage_legacy_bps(slippage_cfg, price, side)


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
    reg_fees_cfg: Optional[RegFeesConfig] = None,
) -> BacktestResult:
    # Validate band units
    if rebalance_band_pct < 0.0 or rebalance_band_pct > 1.0:
        raise ValueError("rebalance_band_pct debe estar en [0,1]. Usa fracción (e.g., 0.02 para 2%).")
    # Execution-cost model (COST_MODEL.md). Regulatory fees default to the IBKR schedule.
    reg_cfg = reg_fees_cfg if reg_fees_cfg is not None else RegFeesConfig()
    spread_impact = slippage_cfg.model != "bps"
    adv_by_sym: Dict[str, pd.Series] = {}
    sigma_by_sym: Dict[str, pd.Series] = {}
    if spread_impact:
        for sym_, df_ in data.items():
            adv_by_sym[sym_], sigma_by_sym[sym_] = rolling_adv_and_sigma(
                df_, slippage_cfg.adv_window_days, slippage_cfg.sigma_window_days
            )
    impact_warned: Set[str] = set()
    costs = CostTotals()
    order_costs: List[Tuple[Any, OrderCost]] = []

    def _order_cost(sym_: str, qty_: int, ref_price_: float, dt_: Any) -> OrderCost:
        """Fill price and all-in cost of ``qty_`` shares of ``sym_`` at the open ``ref_price_``."""
        sigma_: Optional[float] = None
        adv_: Optional[float] = None
        if spread_impact:
            s_ = sigma_by_sym.get(sym_)
            a_ = adv_by_sym.get(sym_)
            if s_ is not None and dt_ in s_.index:
                sigma_ = float(s_.loc[dt_])
            if a_ is not None and dt_ in a_.index:
                adv_ = float(a_.loc[dt_])
        return total_order_cost(
            sym_,
            int(qty_),
            float(ref_price_),
            dt_,
            commission_cfg=commission_cfg,
            slippage_cfg=slippage_cfg,
            reg_fees_cfg=reg_cfg,
            sigma_daily=sigma_,
            adv_shares=adv_,
            warned=impact_warned,
        )

    # Prepare signals
    signals = strategy.generate_signals(data)
    # Weight mode (pipeline strategies): signals are signed target weights (fraction of NAV),
    # already sized and buffered upstream; the engine only enforces direction, regime veto and risk.
    weight_mode = getattr(strategy, "signal_kind", "direction") == "weight"
    last_weights: Dict[str, float] = {sym: 0.0 for sym in data}
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
    # Per-bar lockout flags (read-only probes; never alter risk state or fills)
    restricted_flags: List[Tuple[Any, bool]] = []
    for i, dt in enumerate(all_dates):
        if i == 0:
            # No execution possible on first bar; mark-to-market at close
            close_prices = {
                sym: float(data[sym].reindex([dt])["close"].iloc[0]) for sym in data if dt in data[sym].index
            }
            equity = cash + sum(qty * close_prices.get(sym, 0.0) for sym, qty in holdings.items())
            equity_curve.append((dt, equity))
            returns.append((dt, 0.0))
            restricted_flags.append((dt, _probe_restricted(risk_manager)))
            prev_equity = equity
            for sym in data.keys():
                positions[sym].loc[dt] = holdings.get(sym, 0)
            continue
        dt_prev = all_dates[i - 1]
        # Reset daily risk state at day open
        if risk_manager is not None:
            # Use previous equity as starting equity for the day
            risk_manager.on_new_day(str(dt), float(prev_equity))
        # Lockout at the open (prior-day halt, kill switch, FSM carried into today)
        bar_restricted = _probe_restricted(risk_manager)
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
        raw_weight: Dict[str, float] = {}
        for sym, s in signals.items():
            raw_val = s.reindex([dt_prev]).fillna(0).iloc[0]
            if weight_mode:
                wv = float(raw_val)
                if not math.isfinite(wv):
                    wv = 0.0
                raw_weight[sym] = wv
                sig = 1 if wv > 0 else (-1 if wv < 0 else 0)
            else:
                sig = int(raw_val)
            # Enforce direction
            if direction == "long_only":
                sig = max(sig, 0)
            elif direction == "short_only":
                sig = min(sig, 0)
            # Risk-on veto
            if risk_on is not None:
                ro_val = risk_on.reindex([dt_prev]).iloc[0]
                # During warm-up (regime unknown / NaN), treat as neutral (no trades)
                if pd.isna(ro_val) or float(ro_val) < risk_on_threshold:
                    sig = 0
            raw_sign[sym] = sig
            if weight_mode and (sig == 0 or (raw_weight[sym] > 0) != (sig > 0)):
                raw_weight[sym] = 0.0
        actives = [sym for sym, sign in raw_sign.items() if sign != 0]
        targets: Dict[str, int] = {sym: 0 for sym in data}
        # Weight mode: the weight each target stands for. ``last_weights`` only moves when the order
        # actually executes, so a rebalance vetoed by the risk manager is proposed again next bar.
        bar_weights: Dict[str, float] = {sym: 0.0 for sym in data}
        n_active = len(actives)
        base_alloc = (position_size_pct / 100.0) / max(n_active, 1)
        nav_prev = cash + sum(holdings[s] * close_prev.get(s, 0.0) for s in holdings)
        for sym in actives:
            if sym in open_now and open_now[sym] > 0:
                if weight_mode:
                    w = raw_weight[sym]
                else:
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
                est_fill = estimated_fill_price(slippage_cfg, sym, open_now[sym], 1 if w >= 0 else -1)
                qty = int(nav_prev * abs(w) / est_fill) if est_fill > 0 else 0
                proposed = qty if w >= 0 else -qty
                # Only trade on signal changes, or when drift exceeds band (if configured)
                prev_target = last_targets.get(sym, 0)
                sign_change = (prev_target == 0 and proposed != 0) or (prev_target * proposed < 0)
                if weight_mode:
                    # Trade only when the (already buffered) target weight moved since the last
                    # executed order; otherwise hold the executed share count.
                    bar_weights[sym] = w
                    if abs(w - last_weights.get(sym, 0.0)) < 1e-12 and prev_target != 0:
                        proposed = prev_target
                elif not sign_change and rebalance_band_pct <= 0.0:
                    proposed = prev_target
                targets[sym] = proposed
        # Execute at today's open
        # Cooldown tracking is per-run via local cooldown_until dict (no shared/module state)
        for sym, target in targets.items():
            price = open_now.get(sym)
            if price is None:
                continue
            pos = holdings.get(sym, 0)
            block_exposure_increase = False
            # Handle a previously scheduled stop-loss exit at the open, before anything else
            if risk_manager is not None and stop_scheduled.get(sym, False) and pos != 0:
                oc_exit = _order_cost(sym, -pos, price, dt)
                fill_exit = oc_exit.fill_price
                comm_exit = oc_exit.explicit_fees  # commission + regulatory fees
                cash -= (-pos) * fill_exit + comm_exit
                turnover_notional += abs(pos) * fill_exit
                costs.add(oc_exit)
                order_costs.append((dt, oc_exit))
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
                trades.append(
                    (str(dt), sym, int(-pos), float(fill_exit), TradeReason.STOP_LOSS.value)
                )
                last_targets[sym] = 0
                last_weights[sym] = 0.0
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
                            oc_exit = _order_cost(sym, -pos, price, dt)
                            fill_exit = oc_exit.fill_price
                            comm_exit = oc_exit.explicit_fees  # commission + regulatory fees
                            cash -= (-pos) * fill_exit + comm_exit
                            turnover_notional += abs(pos) * fill_exit
                            costs.add(oc_exit)
                            order_costs.append((dt, oc_exit))
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
                            trades.append(
                                (
                                    str(dt),
                                    sym,
                                    int(-pos),
                                    float(fill_exit),
                                    TradeReason.KILL_SWITCH.value,
                                )
                            )
                            last_targets[sym] = 0
                            last_weights[sym] = 0.0
                            if risk_manager.cfg.cooldown_bars > 0:
                                cooldown_until[sym] = i + int(risk_manager.cfg.cooldown_bars) + 1
                            # Do not attempt any other action on this symbol today
                            continue
                except Exception as exc:
                    log.warning("risk_fail_closed killswitch_flatten sym=%s err=%s", sym, exc)
                    block_exposure_increase = True
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
                except Exception as exc:
                    log.warning("risk_fail_closed killswitch_force_close sym=%s err=%s", sym, exc)
                    block_exposure_increase = True
                # (Open-time stop processing removed; stops are scheduled at prior close)
            if force_close:
                target = 0
            delta = target - pos
            if block_exposure_increase:
                exposure_increasing = (pos == 0 and delta != 0) or (
                    pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))
                )
                if exposure_increasing:
                    delta = 0
                    target = pos
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
                except Exception as exc:
                    log.warning("risk_fail_closed daily_loss_prev_ret sym=%s err=%s", sym, exc)
                    if (pos == 0 and delta != 0) or (
                        pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))
                    ):
                        delta = 0
                        target = pos
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
                except Exception as exc:
                    log.warning("risk_fail_closed drawdown sym=%s err=%s", sym, exc)
                    exposure_increasing = (pos == 0 and delta != 0) or (
                        pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))
                    )
                    if exposure_increasing:
                        delta = 0
                        target = pos
            if delta == 0:
                continue
            if pos != 0 and rebalance_band_pct > 0:
                rel_change = abs(delta) / max(1, abs(pos))
                if rel_change < rebalance_band_pct:
                    continue
            # Modelled fill (spread + impact, or legacy flat bps) and explicit fees for this order
            oc = _order_cost(sym, delta, price, dt)
            fill_price = oc.fill_price
            commission = oc.explicit_fees  # commission + regulatory fees (sells)
            if ((benefit_bps > 0.0) or (risk_cost_bps > 0.0)) and (pos != 0) and (target != 0) and (pos * target > 0):
                slippage_cost = oc.half_spread + oc.impact
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
                    oc_close = _order_cost(sym, dclose, price, dt)
                    dfill = oc_close.fill_price
                    dcomm = oc_close.explicit_fees
                    cash -= dclose * dfill + dcomm
                    holdings[sym] = 0
                    turnover_notional += abs(dclose) * dfill
                    costs.add(oc_close)
                    order_costs.append((dt, oc_close))
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
                            (
                                TradeReason.KILL_SWITCH.value
                                if is_emergency
                                else TradeReason.STOP_LOSS.value
                            ),
                        )
                    )
                    last_targets[sym] = 0
                    last_weights[sym] = 0.0
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
                        oc_close = _order_cost(sym, delta_close, price, dt)
                        okc, msgc = risk_manager.approve_order(
                            symbol=sym,
                            equity=eq_prev,
                            price=oc_close.fill_price,
                            quantity=int(delta_close),
                            current_positions_value=float(cur_pos_val),
                            current_position_qty=int(pos),
                            is_stop=False,
                            is_emergency=is_emergency,
                        )
                        if okc and delta_close != 0:
                            # Execute close-only
                            dfill = oc_close.fill_price
                            dcomm = oc_close.explicit_fees
                            cash -= delta_close * dfill + dcomm
                            holdings[sym] = 0
                            turnover_notional += abs(delta_close) * dfill
                            costs.add(oc_close)
                            order_costs.append((dt, oc_close))
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
                            trades.append(
                                (
                                    str(dt),
                                    sym,
                                    int(delta_close),
                                    float(dfill),
                                    TradeReason.FLIP_CLOSE_ONLY.value,
                                )
                            )
                            last_targets[sym] = 0
                            last_weights[sym] = 0.0
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
                    except Exception as exc:
                        log.warning("risk_fail_closed daily_halt_hard_gate sym=%s err=%s", sym, exc)
                        exposure_increasing = (pos == 0 and delta != 0) or (
                            pos != 0 and ((pos > 0 and delta > 0) or (pos < 0 and delta < 0))
                        )
                        if exposure_increasing:
                            continue
            # Execute order
            cash -= delta * fill_price + commission
            holdings[sym] = pos + delta
            turnover_notional += abs(delta) * fill_price
            costs.add(oc)
            order_costs.append((dt, oc))
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
            trades.append(
                (str(dt), sym, int(delta), float(fill_price), TradeReason.SIGNAL.value)
            )
            # Update last target after execution
            last_targets[sym] = target
            if weight_mode:
                last_weights[sym] = bar_weights.get(sym, 0.0) if target != 0 else 0.0
        # Lockout asserted during the bar (drawdown / cumulative / intraday daily-loss probes)
        if not bar_restricted:
            bar_restricted = _probe_restricted(risk_manager)
        restricted_flags.append((dt, bar_restricted))
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
    restricted_series = pd.Series(
        {dt: bool(flag) for dt, flag in restricted_flags}, dtype=bool
    ).sort_index()
    if not restricted_series.index.equals(equity_series.index):
        # Defensive: any bar without a probe counts as restricted (fail-closed)
        restricted_series = restricted_series.reindex(equity_series.index, fill_value=True).astype(bool)
    stats = compute_stats(equity_series, returns_series, costs=costs, initial_equity=initial_equity)
    # Extend stats with trade-level metrics
    trade_count = len(trades)
    profit_factor = (realized_wins / realized_losses) if realized_losses > 0 else 0.0
    expectancy = (realized_pnl / realized_trades) if realized_trades > 0 else 0.0
    stats.trade_count = trade_count
    stats.total_commission = float(costs.commission)
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
        restricted=restricted_series,
        order_costs=order_costs,
    )

