"""Order manager: approved orders → IBKR with state tracking (audit 2026-11-07, §3.5).

What the old ``IBKRBroker.place_order`` did not do, and this does:

1. **State machine per order** (``OrderState``): every transition is appended to an orders
   ledger (JSONL), with the broker status, filled quantity and average price.
2. **Idempotency**: each order carries a deterministic ``orderRef``
   (``<prefix>-<YYYYMMDD>-<SYMBOL>-<SIDE>``). Before sending, the manager asks the broker for
   open orders and today's executions with that ref; if one exists the order is skipped as
   ``DUPLICATE``. A crash and restart cannot double an order.
3. **Broker errors are seen**: the gateway records ``errorEvent`` per order id; a rejected
   order ends ``REJECTED`` with the IBKR message instead of disappearing silently (the
   "Read-Only API" case in the playbook).
4. **Patient → aggressive**: limit at the midpoint (± ``limit_offset_bps``), wait up to
   ``order_timeout_sec``, then cancel and (if enabled) send the remainder as an IBKR
   ``Adaptive`` market order, regular hours only, wait again, cancel what is left.
5. **Rate limit**: a token bucket under the API's 50 msg/s (``max_msgs_per_sec``).
6. **Modes**: ``shadow`` sends nothing and records ``SHADOW`` rows; ``paper_orders`` requires
   ``MODE=PAPER`` on the paper port and ``TRADING__ALLOW_BROKER_ORDERS=true``; ``live_orders``
   additionally requires every LIVE check of ``AppSettings.live_safety_ok``.

Only orders approved by ``risk.pretrade.check_orders`` should be passed in.
"""

from __future__ import annotations

import abc
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import AppSettings, ExecutionConfig
from ..ops.slippage_ledger import record_slip
from .rebalance import ProposedOrder


class OrderState(str, Enum):
    SHADOW = "SHADOW"
    DUPLICATE = "DUPLICATE"
    SKIPPED = "SKIPPED"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


TERMINAL = {OrderState.SHADOW, OrderState.DUPLICATE, OrderState.SKIPPED, OrderState.FILLED,
            OrderState.CANCELLED, OrderState.REJECTED}


@dataclass
class BrokerOrderStatus:
    status: str  # IBKR status string: Submitted, Filled, Cancelled, Inactive, ...
    filled: float = 0.0
    remaining: float = 0.0
    avg_fill_price: float = 0.0
    error: Optional[str] = None


@dataclass
class ManagedOrder:
    order_ref: str
    symbol: str
    side: str
    quantity: int
    decision_price: float
    state: OrderState = OrderState.SKIPPED
    limit_price: Optional[float] = None
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    broker_ids: List[str] = field(default_factory=list)
    reason: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


class OrderGateway(abc.ABC):
    """Narrow broker surface the manager needs (IBKR in production, a fake in tests)."""

    @abc.abstractmethod
    def existing_refs(self, prefix: str) -> Dict[str, str]:
        """orderRef → status for open orders and today's executions whose ref starts with prefix."""

    @abc.abstractmethod
    def midpoint(self, symbol: str) -> Optional[float]:
        ...

    @abc.abstractmethod
    def place_limit(self, symbol: str, side: str, qty: int, limit: float, order_ref: str) -> str:
        ...

    @abc.abstractmethod
    def place_adaptive_market(self, symbol: str, side: str, qty: int, order_ref: str) -> str:
        ...

    @abc.abstractmethod
    def status(self, broker_id: str) -> BrokerOrderStatus:
        ...

    @abc.abstractmethod
    def cancel(self, broker_id: str) -> None:
        ...

    def sleep(self, seconds: float) -> None:  # pragma: no cover - overridden by IB gateway
        time.sleep(seconds)


class RateLimiter:
    """Token bucket: at most ``rate`` calls per second, bursts up to ``rate``."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.rate = float(rate)
        self.tokens = float(rate)
        self.clock = clock
        self.sleeper = sleeper
        self.last = clock()

    def acquire(self) -> None:
        now = self.clock()
        self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1.0:
            wait = (1.0 - self.tokens) / self.rate
            self.sleeper(wait)
            self.last = self.clock()
            self.tokens = 0.0
        else:
            self.tokens -= 1.0


def order_ref_for(prefix: str, run_date: date, symbol: str, side: str) -> str:
    return f"{prefix}-{run_date:%Y%m%d}-{symbol.upper()}-{side.upper()}"


def execution_permission(settings: AppSettings) -> Tuple[bool, str]:
    """Can orders actually be sent with these settings? Shadow is always allowed."""
    mode = settings.execution.mode
    if mode == "shadow":
        return True, "shadow: nothing is sent"
    if not settings.trading.allow_broker_orders:
        return False, "TRADING__ALLOW_BROKER_ORDERS=false"
    if mode == "paper_orders":
        if settings.mode.upper() != "PAPER":
            return False, "execution.mode=paper_orders requires MODE=PAPER"
        if settings.ib_port() != settings.ib.paper_port:
            return False, "paper_orders must use the paper port"
        return True, "paper orders allowed"
    ok, msg = settings.live_safety_ok()
    return (ok, msg if not ok else "live orders allowed")


_DONE = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}


class OrderManager:
    def __init__(
        self,
        gateway: Optional[OrderGateway],
        cfg: ExecutionConfig,
        *,
        ledger_path: str | Path,
        slippage_path: Optional[str | Path] = None,
        poll_interval_sec: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.gw = gateway
        self.cfg = cfg
        self.ledger_path = Path(ledger_path)
        self.slippage_path = Path(slippage_path) if slippage_path else None
        self.poll = float(poll_interval_sec)
        self.clock = clock
        self.limiter = limiter or RateLimiter(cfg.max_msgs_per_sec)

    # -- ledger -----------------------------------------------------------------------
    def _log(self, mo: ManagedOrder, state: OrderState, **info: Any) -> None:
        mo.state = state
        row = {"ts": datetime.now(timezone.utc).isoformat(), "order_ref": mo.order_ref, "state": state.value,
               "symbol": mo.symbol, "side": mo.side, "quantity": mo.quantity, **info}
        mo.history.append(row)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")

    # -- main entry -------------------------------------------------------------------
    def execute(self, orders: Sequence[ProposedOrder], run_date: date, *, send: bool) -> List[ManagedOrder]:
        """Run approved orders. ``send=False`` (shadow or not permitted) records SHADOW rows only."""
        out: List[ManagedOrder] = []
        existing: Dict[str, str] = {}
        if send:
            if self.gw is None:
                raise RuntimeError("send=True needs a broker gateway")
            self.limiter.acquire()
            existing = self.gw.existing_refs(self.cfg.order_ref_prefix)
        for o in orders:
            ref = order_ref_for(self.cfg.order_ref_prefix, run_date, o.symbol, o.side)
            mo = ManagedOrder(order_ref=ref, symbol=o.symbol, side=o.side, quantity=int(o.quantity),
                              decision_price=float(o.ref_price))
            if not send:
                self._log(mo, OrderState.SHADOW, ref_price=o.ref_price, target_qty=o.target_qty)
            elif ref in existing or f"{ref}-A" in existing:
                mo.reason = f"orderRef already at broker ({existing.get(ref) or existing.get(ref + '-A')})"
                self._log(mo, OrderState.DUPLICATE, reason=mo.reason)
            else:
                self._run_one(mo)
            out.append(mo)
        return out

    def _limit_price(self, side: str, mid: float) -> float:
        off = self.cfg.limit_offset_bps / 1e4
        px = mid * (1.0 + off) if side == "BUY" else mid * (1.0 - off)
        return round(px, 2)

    def _wait(self, mo: ManagedOrder, broker_id: str, timeout: float) -> BrokerOrderStatus:
        assert self.gw is not None
        start = self.clock()
        st = BrokerOrderStatus(status="Submitted")
        while True:
            self.limiter.acquire()
            st = self.gw.status(broker_id)
            if st.error or st.status in _DONE:
                return st
            if self.clock() - start >= timeout:
                return st
            self.gw.sleep(self.poll)

    def _absorb_fill(self, mo: ManagedOrder, st: BrokerOrderStatus, prior_filled: int, prior_cost: float) -> None:
        new_filled = int(round(st.filled))
        total = prior_filled + new_filled
        cost = prior_cost + new_filled * float(st.avg_fill_price or 0.0)
        mo.filled_qty = total
        mo.avg_fill_price = cost / total if total > 0 else 0.0

    def _run_one(self, mo: ManagedOrder) -> None:
        assert self.gw is not None
        self.limiter.acquire()
        mid = self.gw.midpoint(mo.symbol)
        if mid is None or not (mid > 0):
            mo.reason = "no_midpoint"
            self._log(mo, OrderState.SKIPPED, reason=mo.reason)
            return
        mo.limit_price = self._limit_price(mo.side, mid)
        self.limiter.acquire()
        bid = self.gw.place_limit(mo.symbol, mo.side, mo.quantity, mo.limit_price, mo.order_ref)
        mo.broker_ids.append(bid)
        self._log(mo, OrderState.SUBMITTED, broker_id=bid, limit=mo.limit_price, mid=mid)
        st = self._wait(mo, bid, self.cfg.order_timeout_sec)
        self._absorb_fill(mo, st, 0, 0.0)
        if st.error and mo.filled_qty == 0:
            mo.reason = st.error
            self._log(mo, OrderState.REJECTED, broker_id=bid, error=st.error)
            return
        if mo.filled_qty >= mo.quantity:
            self._finish_filled(mo)
            return
        if st.status not in _DONE:
            self.limiter.acquire()
            self.gw.cancel(bid)
            self.limiter.acquire()
            st = self.gw.status(bid)
            self._absorb_fill(mo, st, 0, 0.0)
        remaining = mo.quantity - mo.filled_qty
        if remaining <= 0:
            self._finish_filled(mo)
            return
        if mo.filled_qty > 0:
            self._log(mo, OrderState.PARTIAL, filled=mo.filled_qty, avg=mo.avg_fill_price)
        if not self.cfg.escalate_to_adaptive:
            mo.reason = "limit_timeout"
            self._log(mo, OrderState.CANCELLED, filled=mo.filled_qty, reason=mo.reason)
            self._record_slippage(mo)
            return
        prior_filled, prior_cost = mo.filled_qty, mo.filled_qty * mo.avg_fill_price
        self.limiter.acquire()
        bid2 = self.gw.place_adaptive_market(mo.symbol, mo.side, remaining, f"{mo.order_ref}-A")
        mo.broker_ids.append(bid2)
        self._log(mo, OrderState.SUBMITTED, broker_id=bid2, escalated=True, qty=remaining)
        st2 = self._wait(mo, bid2, self.cfg.order_timeout_sec)
        self._absorb_fill(mo, st2, prior_filled, prior_cost)
        if mo.filled_qty >= mo.quantity:
            self._finish_filled(mo)
            return
        if st2.status not in _DONE:
            self.limiter.acquire()
            self.gw.cancel(bid2)
        mo.reason = st2.error or "adaptive_timeout"
        state = OrderState.REJECTED if (st2.error and mo.filled_qty == 0) else OrderState.CANCELLED
        self._log(mo, state, filled=mo.filled_qty, reason=mo.reason)
        self._record_slippage(mo)

    def _finish_filled(self, mo: ManagedOrder) -> None:
        self._log(mo, OrderState.FILLED, filled=mo.filled_qty, avg=mo.avg_fill_price)
        self._record_slippage(mo)

    def _record_slippage(self, mo: ManagedOrder) -> None:
        if self.slippage_path is None or mo.filled_qty <= 0 or mo.avg_fill_price <= 0:
            return
        record_slip(self.slippage_path, symbol=mo.symbol, side=mo.side, decision_px=mo.decision_price,
                    fill_px=mo.avg_fill_price, qty=mo.filled_qty, source="ibkr")


__all__ = [
    "BrokerOrderStatus",
    "ManagedOrder",
    "OrderGateway",
    "OrderManager",
    "OrderState",
    "RateLimiter",
    "execution_permission",
    "order_ref_for",
]
