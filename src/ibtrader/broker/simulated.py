from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..config import CommissionConfig, SlippageConfig
from .base import Broker, Order, Quote


@dataclass
class SimulatedMarketState:
    last_prices: Dict[str, float]
    equity: float


class SimulatedBroker(Broker):
    """
    Simple simulated broker for backtesting and dry-run.
    Fills market orders at last price +/- slippage; limit orders if touchable.
    """

    def __init__(
        self,
        market_state: SimulatedMarketState,
        commission: CommissionConfig,
        slippage: SlippageConfig,
        dry_run: bool = False,
    ) -> None:
        self.market_state = market_state
        self.commission_cfg = commission
        self.slippage_cfg = slippage
        self.dry_run = dry_run
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

    def _commission_for(self, quantity: int, price: float) -> float:
        if self.commission_cfg.percent_of_value:
            ad_valorem = self.commission_cfg.percent_of_value / 100.0 * abs(quantity) * price
        else:
            ad_valorem = 0.0
        per_share = self.commission_cfg.per_share * abs(quantity)
        commission = max(per_share + ad_valorem, self.commission_cfg.min_per_order)
        return commission

    def _slip(self, price: float, side: str) -> float:
        # Apply simple bps slippage
        bps = self.slippage_cfg.bps / 10000.0
        if side.upper() == "BUY":
            return price * (1 + bps)
        return price * (1 - bps)

    def place_order(self, order: Order) -> str:
        self._order_seq += 1
        order_id = f"SIM-{self._order_seq}"
        if self.dry_run:
            return order_id
        last = self.market_state.last_prices.get(order.symbol)
        if last is None:
            raise ValueError(f"No price for {order.symbol}")
        fill_price: Optional[float] = None
        if order.order_type == "MKT":
            fill_price = self._slip(last, order.side)
        elif order.order_type == "LMT" and order.limit_price is not None:
            if order.side.upper() == "BUY":
                if order.limit_price >= last:
                    fill_price = min(order.limit_price, self._slip(last, order.side))
            else:
                if order.limit_price <= last:
                    fill_price = max(order.limit_price, self._slip(last, order.side))
        if fill_price is None:
            return order_id  # unfilled

        commission = self._commission_for(order.quantity, fill_price)
        signed_qty = order.quantity if order.side.upper() == "BUY" else -order.quantity
        # Update positions and equity
        pos = self._positions.get(order.symbol, 0)
        new_pos = pos + signed_qty
        self._positions[order.symbol] = new_pos
        cash_effect = -signed_qty * fill_price - commission
        self.market_state.equity += cash_effect
        return order_id

    def get_quote(self, symbol: str) -> Quote:
        p = self.market_state.last_prices.get(symbol)
        if p is None:
            return Quote(symbol=symbol)
        spread = max(0.01, p * 0.0005)
        return Quote(symbol=symbol, bid=p - spread / 2, ask=p + spread / 2, last=p)

    def cancel_all(self) -> None:
        # Nothing to do for now in simple simulator
        return

