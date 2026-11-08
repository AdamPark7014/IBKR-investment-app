"""Pre-trade risk checks: the last gate before the broker (audit 2026-11-07, §3.4).

The strategy proposes, risk disposes. Every order that reaches ``OrderManager`` must have come
out of ``check_orders`` as approved. Global blocks (kill switch, wrong account, stale data,
risk FSM halted) stop all risk-increasing orders; reductions and exits always pass global
blocks, because refusing to reduce risk is itself a risk.

Per-order rules: whitelist, positive integer quantity, max notional, fat-finger limit price,
stale reference price, no shorts unless allowed, post-trade weight and gross exposure caps,
and a per-run order count (exits first).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..config import PretradeConfig
from ..execution.rebalance import ProposedOrder


@dataclass
class PretradeContext:
    nav: float
    positions: Mapping[str, int]
    prices: Mapping[str, float]
    allowed_symbols: Sequence[str] = ()
    allow_short: bool = False
    killswitch_active: bool = False
    account_ok: bool = True
    data_fresh: bool = True
    risk_can_increase: bool = True  # False when the risk FSM is RESTRICTED / HALTED
    reference_date: Optional[date] = None  # date of the reference prices
    today: Optional[date] = None
    #: Cash-equivalent ETFs (T-bills): exempt from ``max_weight_per_symbol`` (holding 100 % in BIL
    #: when every trend is negative is the point of the cash sweep, not a concentration risk).
    cash_symbols: Sequence[str] = ()


@dataclass
class PretradeDecision:
    approved: List[ProposedOrder] = field(default_factory=list)
    rejected: List[Tuple[ProposedOrder, str]] = field(default_factory=list)
    global_blocks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": [o.to_dict() for o in self.approved],
            "rejected": [{**o.to_dict(), "reason": r} for o, r in self.rejected],
            "global_blocks": list(self.global_blocks),
            "n_approved": len(self.approved),
            "n_rejected": len(self.rejected),
        }


def _reduces_risk(order: ProposedOrder, cur: int) -> bool:
    new = cur + order.signed_qty
    return abs(new) < abs(cur) and (new == 0 or (new > 0) == (cur > 0))


def check_orders(orders: Sequence[ProposedOrder], ctx: PretradeContext, cfg: PretradeConfig) -> PretradeDecision:
    dec = PretradeDecision()
    if ctx.killswitch_active:
        dec.global_blocks.append("kill_switch")
    if not ctx.account_ok:
        dec.global_blocks.append("account_mismatch")
    if not ctx.data_fresh:
        dec.global_blocks.append("stale_data")
    if not ctx.risk_can_increase:
        dec.global_blocks.append("risk_restricted")
    if not (ctx.nav > 0 and math.isfinite(ctx.nav)):
        dec.global_blocks.append("nav_invalid")
    if ctx.reference_date is not None and ctx.today is not None:
        age = (ctx.today - ctx.reference_date).days
        if age > cfg.max_reference_age_days:
            dec.global_blocks.append(f"reference_prices_stale: {age}d > {cfg.max_reference_age_days}d")
    hard_stop = "account_mismatch" in dec.global_blocks or "nav_invalid" in dec.global_blocks

    allowed = {s.upper() for s in ctx.allowed_symbols}
    pos: Dict[str, int] = {k: int(v) for k, v in ctx.positions.items()}
    nav = float(ctx.nav) if ctx.nav and math.isfinite(ctx.nav) else 0.0

    def gross(p: Mapping[str, int]) -> float:
        if nav <= 0:
            return float("inf")
        return sum(abs(q) * float(ctx.prices.get(s) or 0.0) for s, q in p.items()) / nav

    cash = {s.upper() for s in ctx.cash_symbols}
    # Reductions first: a purchase must see the gross exposure the same run's sales already freed.
    ordered = sorted(orders, key=lambda o: 0 if _reduces_risk(o, pos.get(o.symbol, 0)) else 1)
    for o in ordered:
        cur = pos.get(o.symbol, 0)
        reduces = _reduces_risk(o, cur)
        reason: Optional[str] = None
        if hard_stop:
            reason = "global_block: " + ",".join(dec.global_blocks)
        elif dec.global_blocks and not reduces:
            reason = "global_block: " + ",".join(dec.global_blocks)
        elif o.quantity <= 0 or int(o.quantity) != o.quantity:
            reason = f"bad_quantity: {o.quantity}"
        elif o.side not in ("BUY", "SELL"):
            reason = f"bad_side: {o.side}"
        elif allowed and o.symbol.upper() not in allowed:
            reason = "symbol_not_allowed"
        elif not (o.ref_price > 0 and math.isfinite(o.ref_price)):
            reason = "bad_reference_price"
        elif o.limit_price is not None and (
            abs(o.limit_price / o.ref_price - 1.0) * 100.0 > cfg.max_limit_deviation_pct
        ):
            reason = (
                f"fat_finger: limit {o.limit_price:.4f} vs ref {o.ref_price:.4f} "
                f"> {cfg.max_limit_deviation_pct}%"
            )
        elif o.notional > cfg.max_order_notional_usd + 1e-9 and not o.is_exit:
            reason = f"max_order_notional: {o.notional:.2f} > {cfg.max_order_notional_usd:.2f}"
        elif not reduces:
            new_qty = cur + o.signed_qty
            if new_qty < 0 and not ctx.allow_short:
                reason = "short_not_allowed"
            else:
                trial = dict(pos)
                trial[o.symbol] = new_qty
                w = abs(new_qty) * o.ref_price / nav if nav > 0 else float("inf")
                if w > cfg.max_weight_per_symbol + 1e-9 and o.symbol.upper() not in cash:
                    reason = f"max_weight_per_symbol: {w:.3f} > {cfg.max_weight_per_symbol:.3f}"
                elif gross(trial) > cfg.max_gross_exposure + 1e-9:
                    reason = f"max_gross_exposure: {gross(trial):.3f} > {cfg.max_gross_exposure:.3f}"
        if reason is None and len(dec.approved) >= cfg.max_orders_per_run:
            reason = f"max_orders_per_run: {cfg.max_orders_per_run}"
        if reason is None:
            dec.approved.append(o)
            pos[o.symbol] = cur + o.signed_qty
        else:
            dec.rejected.append((o, reason))
    return dec


__all__ = ["PretradeContext", "PretradeDecision", "check_orders"]
