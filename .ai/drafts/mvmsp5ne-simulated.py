from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from ..config import CommissionConfig, RegFeesConfig, SlippageConfig
from ..execution.costs import total_order_cost
from ..execution.session import is_rth
from ..ops.slippage_ledger import record_slip
from .base import Broker, Order, Quote


@dataclass
class SimulatedMarketState:
    last_prices: Dict[str, float]
    equity: float


class SimulatedBroker(Broker):
    """
    Simple simulated broker for backtesting and dry-run.
    Fills market orders via ``total_order_cost``; limit orders if touchable
    (probabilistic fill when ``prob_fill_on_limit`` < 1).
    """

    def __init__(
        self,
        market_state: SimulatedMarketState,
        commission: CommissionConfig,
        slippage: SlippageConfig,
        dry_run: bool = False,
        reg_fees: RegFeesConfig | None = None,
        *,
        prob_fill_on_limit: float = 0.7,
        ledger_path: str | None = None,
        rng: random.Random | None = None,
        latency_ms: float = 0.0,
        require_rth: bool = False,
        now_fn: Any | None = None,
    ) -> None:
        self.market_state = market_state
        self.commission_cfg = commission
        self.slippage_cfg = slippage
        self.dry_run = dry_run
        self.reg_fees_cfg = reg_fees if reg_fees is not None else RegFeesConfig()
        self.prob_fill_on_limit = float(prob_fill_on_limit)
        self.ledger_path = ledger_path
        self._rng = rng if rng is not None else random.Random()
        self.latency_ms = float(latency_ms)
        self.require_rth = bool(require_rth)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.last_latency_ms: float | None = None
        self._positions: Dict[str, int] = {}
        self._connected = True
        self._order_seq = 0

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def account_info(self) -> Dict[str, Any]:
        return {"equity": self.market_state.equity, "currency": "USD", "paper": True}

    def get_positions(self) -> Dict[str, int]:
        return dict(self._positions)

    def place_order(self, order: Order) -> str:
        self._order_seq += 1
        order_id = f"SIM-{self._order_seq}"
        if self.require_rth and not is_rth(self._now_fn()):
            self.last_latency_ms = None
            return order_id
        if self.dry_run:
            return order_id
        last = self.market_state.last_prices.get(order.symbol)
        if last is None:
            raise ValueError(f"No price for {order.symbol}")

        signed = int(order.quantity) if order.side.upper() == "BUY" else -int(order.quantity)
        probe = total_order_cost(
            order.symbol,
            signed,
            float(last),
            date.today(),
            commission_cfg=self.commission_cfg,
            slippage_cfg=self.slippage_cfg,
            reg_fees_cfg=self.reg_fees_cfg,
        )
        fill_price: Optional[float] = None
        touchable = False
        if order.order_type == "MKT":
            fill_price = float(probe.fill_price)
        elif order.order_type == "LMT" and order.limit_price is not None:
            lim = float(order.limit_price)
            if order.side.upper() == "BUY" and lim >= float(last):
                touchable = True
                fill_price = min(lim, float(probe.fill_price))
            elif order.side.upper() == "SELL" and lim <= float(last):
                touchable = True
                fill_price = max(lim, float(probe.fill_price))
            if touchable and self._rng.random() >= self.prob_fill_on_limit:
                fill_price = None

        if fill_price is None:
            return order_id

        if order.order_type == "LMT":
            oc = total_order_cost(
                order.symbol,
                signed,
                float(fill_price),
                date.today(),
                commission_cfg=self.commission_cfg,
                slippage_cfg=SlippageConfig(model="bps", bps=0.0),
                reg_fees_cfg=self.reg_fees_cfg,
            )
            exec_px = float(fill_price)
        else:
            oc = probe
            exec_px = float(oc.fill_price)

        if self.ledger_path:
            record_slip(
                self.ledger_path,
                symbol=order.symbol,
                side=order.side,
                decision_px=float(last),
                fill_px=exec_px,
                qty=int(order.quantity),
                source="sim",
            )

        pos = self._positions.get(order.symbol, 0)
        self._positions[order.symbol] = pos + signed
        self.market_state.equity += -signed * exec_px - oc.explicit_fees
        self.last_latency_ms = self.latency_ms
        return order_id

    def get_quote(self, symbol: str) -> Quote:
        p = self.market_state.last_prices.get(symbol)
        if p is None:
            return Quote(symbol=symbol)
        spread = max(0.01, p * 0.0005)
        return Quote(symbol=symbol, bid=p - spread / 2, ask=p + spread / 2, last=p)

    def cancel_all(self) -> None:
        return