"""Target weights → share orders (audit 2026-11-07, §5 step 3).

Pure function, no broker: given the NAV, current positions and reference prices, compute the
integer share change that moves each symbol toward its target weight. Changes smaller than
``min_notional`` are skipped (the IBKR USD 1 minimum makes a USD 1,000 order cost 10 bp), and
increases larger than ``max_notional`` are clipped so one run moves at most that much per symbol;
the next run keeps converging. Full exits are never skipped or clipped.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional


@dataclass
class ProposedOrder:
    symbol: str
    side: str  # "BUY" | "SELL"
    quantity: int
    ref_price: float
    target_weight: float
    current_qty: int
    target_qty: int
    limit_price: Optional[float] = None
    is_exit: bool = False  # brings the position to zero
    notes: List[str] = field(default_factory=list)

    @property
    def notional(self) -> float:
        return float(self.quantity) * float(self.ref_price)

    @property
    def signed_qty(self) -> int:
        return self.quantity if self.side == "BUY" else -self.quantity

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["notional"] = self.notional
        return d


def build_rebalance_orders(
    target_weights: Mapping[str, float],
    positions: Mapping[str, int],
    prices: Mapping[str, float],
    nav: float,
    *,
    min_notional: float = 0.0,
    max_notional: Optional[float] = None,
    hold: Optional[Iterable[str]] = None,
) -> List[ProposedOrder]:
    """Orders that move ``positions`` toward ``target_weights`` × ``nav``.

    Symbols held but absent from ``target_weights`` get target 0 (exit). A symbol without a
    positive finite price is skipped (no order on a price we cannot trust). Exits come first in
    the returned list so a per-run order cap never keeps a reduction waiting behind a purchase.
    Symbols in ``hold`` (no fresh data today) are never traded.
    """
    frozen = {str(s).upper() for s in (hold or ())}
    if not (nav > 0 and math.isfinite(nav)):
        return []
    symbols = sorted(set(target_weights) | {s for s, q in positions.items() if int(q) != 0})
    out: List[ProposedOrder] = []
    for sym in symbols:
        if sym.upper() in frozen:
            continue
        px = float(prices.get(sym) or 0.0)
        if not (px > 0 and math.isfinite(px)):
            continue
        w = float(target_weights.get(sym, 0.0) or 0.0)
        cur = int(positions.get(sym, 0) or 0)
        tgt = int(math.floor(abs(w) * nav / px)) * (1 if w >= 0 else -1)
        delta = tgt - cur
        if delta == 0:
            continue
        is_exit = tgt == 0 and cur != 0
        reduces = abs(tgt) < abs(cur) and (tgt == 0 or (tgt > 0) == (cur > 0))
        notes: List[str] = []
        if not is_exit and abs(delta) * px < min_notional:
            continue
        if max_notional is not None and not is_exit and not reduces and abs(delta) * px > max_notional:
            clipped = int(math.floor(max_notional / px))
            if clipped <= 0:
                continue
            notes.append(f"clipped_from={abs(delta)}")
            delta = clipped if delta > 0 else -clipped
        out.append(
            ProposedOrder(
                symbol=sym,
                side="BUY" if delta > 0 else "SELL",
                quantity=abs(delta),
                ref_price=px,
                target_weight=w,
                current_qty=cur,
                target_qty=tgt,
                is_exit=is_exit,
                notes=notes,
            )
        )
    out.sort(key=lambda o: (not o.is_exit, o.side != "SELL", o.symbol))
    return out


__all__ = ["ProposedOrder", "build_rebalance_orders"]
