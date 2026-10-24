from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

from ..config import CommissionConfig, RegFeesConfig, SlippageConfig
from ..execution import costs as cost_model
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
        reg_fees: RegFeesConfig | None = None,
    ) -> None:
        self.market_state = market_state
        self.commission_cfg = commission
        self.slippage_cfg = slippage
        self.dry_run = dry_run
        self.reg_fees_cfg = reg_fees if reg_fees is not None else RegFeesConfig()
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
        signed = quantity if quantity >= 0 else -abs(quantity)
        return cost_model.commission(self.commission_cfg, signed, price)

    def _reg_fees_for(self, quantity: int, price: float, is_sell: bool) -> float:
        return cost_model.reg_fees(
            self.reg_fees_cfg, quantity, price, date.today(), is_sell=is_sell,
        )

    def _slip(self, symbol: str, price: float, side: str) -> float:
        side_int = 1 if side.upper() == "BUY" else -1
        if self.slippage_cfg.model == "bps":
            return cost_model.slippage_legacy_bps(self.slippage_cfg, price, side_int)
        hs_frac = cost_model.half_spread_fraction(self.slippage_cfg, symbol)
        return float(price) * (1.0 + side_int * hs_frac)

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
            fill_price = self._slip(order.symbol, last, order.side)
        elif order.order_type == "LMT" and order.limit_price is not None:
            if order.side.upper() == "BUY":
                if order.limit_price >= last:
                    fill_price = min(order.limit_price, self._slip(order.symbol, last, order.side))
            else:
                if order.limit_price <= last:
                    fill_price = max(order.limit_price, self._slip(order.symbol, last, order.side))
        if fill_price is None:
            return order_id  # unfilled

        is_sell = order.side.upper() == "SELL"
        signed_qty = order.quantity if not is_sell else -order.quantity
        commission = self._commission_for(signed_qty, fill_price)
        regulatory = self._reg_fees_for(order.quantity, fill_price, is_sell=is_sell)
        pos = self._positions.get(order.symbol, 0)
        new_pos = pos + signed_qty
        self._positions[order.symbol] = new_pos
        cash_effect = -signed_qty * fill_price - commission - regulatory
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
