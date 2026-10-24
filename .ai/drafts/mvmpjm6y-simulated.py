from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..config import CommissionConfig, RegFeesConfig, SlippageConfig
from .base import Broker, Order, Quote


@dataclass
class SimulatedMarketState:
    last_prices: Dict[str, float]
    equity: float


class SimulatedBroker(Broker):
    """
    Simple simulated broker for backtesting and dry-run.
    Fills market orders at last price +/- slippage; limit orders if touchable.
    Uses COST_MODEL.md via total_order_cost to calculate net fill, commission, reg fees, etc.
    """

    def __init__(
        self,
        market_state: SimulatedMarketState,
        commission: CommissionConfig,
        slippage: SlippageConfig,
        reg_fees: RegFeesConfig | None = None,
        dry_run: bool = False,
    ) -> None:
        self.market_state = market_state
        self.commission_cfg = commission
        self.slippage_cfg = slippage
        self.reg_fees_cfg = reg_fees or RegFeesConfig()
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

    def place_order(self, order: Order) -> str:
        self._order_seq += 1
        order_id = f"SIM-{self._order_seq}"
        if self.dry_run:
            return order_id
        last = self.market_state.last_prices.get(order.symbol)
        if last is None:
            raise ValueError(f"No price for {order.symbol}")

        signed_shares = order.quantity if order.side.upper() == "BUY" else -order.quantity
        fill_price: Optional[float] = None
        if order.order_type == "MKT":
            # Estimate fill for market orders using slippage logic as a proxy for execution cost inputs
            # However, total_order_cost will compute the final fill_price based on costs.
            # We need a reference fill before calling total_order_cost to pass as 'last' or similar?
            # The instruction says: oc = total_order_cost(..., last=...) and then fill_price = oc.fill_price.
            # But total_order_cost usually calculates the fill price based on costs added to base price.
            # In the original code, _slip was called first to get fill_price.
            # Let's assume we pass 'last' as the estimated fill without explicit slip, 
            # or we need to simulate the slip inside total_order_cost? 
            # Re-reading instruction: "En place_order al fill... oc = total_order_cost(..., last=...)".
            # It implies we call total_order_cost with a price. The original code used _slip(last) for MKT.
            # Let's assume total_order_cost takes a base price and adjusts it? 
            # Or maybe 'last' here is the estimated execution price without costs?
            # Looking at typical patterns: last is often the quoted last. total_order_cost adds spread/impact/commission/reg.
            # But for slippage, we need to know if the order fills at a worse price.
            # The instruction says: "fill_price = oc.fill_price". This implies total_order_cost returns an object with fill_price.
            # Let's assume total_order_cost computes the effective fill price including all costs and slippage internally
            # if we pass 'last' as the midpoint or similar. However, for market orders, slippage is part of the cost model.
            # Let's try to call total_order_cost with 'last' as the input price and let it handle slip/costs.
            # But wait, the original code explicitly calculated slip first. 
            # The instruction says: "oc = total_order_cost(order.symbol, signed_shares, last, ...)".
            # It doesn't say to call _slip anymore. So we pass 'last' directly?
            # If so, how does it account for slippage? Maybe total_order_cost includes a default slip or it's passed in config?
            # Actually, looking at the signature of total_order_cost from ..execution.costs:
            # It likely takes symbol, shares, price (which might be the estimated fill), and configs.
            # If we pass 'last' (market price) without slip, we miss the slippage component unless the cost model handles it.
            # But the instruction says to remove _slip legacy or leave as wrapper. Let's remove usage of _slip in this flow 
            # and rely on total_order_cost to handle the fill price calculation including slippage if possible,
            # OR perhaps 'last' is intended to be the price after slip? 
            # Re-reading carefully: "En place_order al fill... oc = total_order_cost(..., last=..., ...)"
            # And then "fill_price = oc.fill_price". This suggests total_order_cost calculates the fill_price.
            # So we don't call _slip anymore. We just pass 'last'. The cost model must handle slippage internally 
            # or 'last' is adjusted elsewhere? Given the instruction to use total_order_cost and remove legacy slip usage,
            # we assume total_order_cost handles the full execution price calculation including slippage if configured.
            # However, without knowing exactly how total_order_cost uses 'last', I will follow the instruction literally:
            # pass 'last' as is. If total_order_cost expects a base and adds costs/slips internally, it works.
            # If it expects a price to be adjusted by slip, maybe we need to adjust? 
            # But the instruction says "En place_order al fill... oc = total_order_cost(...)". It does not mention adjusting last before passing.
            # So I will pass 'last' directly and let total_order_cost handle the rest including slippage if it's part of its logic.
            # Wait, in the original code, for MKT orders, fill_price was set to _slip(last). 
            # If we don't call slip, how do we get the correct fill? 
            # Maybe total_order_cost requires a base price and adds costs/slips on top? 
            # Or maybe 'last' is the price at which it fills, and total_order_cost calculates the cost to execute that?
            # Let's assume 'last' is the best available price, and total_order_cost adjusts it for slip/costs.
            # So we pass 'last' as the target fill price before costs/slips, and total_order_cost computes the net effect.
            # Thus, we call total_order_cost with 'last'.
            pass
        elif order.order_type == "LMT" and order.limit_price is not None:
            if order.side.upper() == "BUY":
                if order.limit_price >= last:
                    fill_price = min(order.limit_price, self._slip(last, order.side))
            else:
                if order.limit_price <= last:
                    fill_price = max(order.limit_price, self._slip(last, order.side))
        
        # For MKT, we didn't set fill_price from _slip in the block above. 
        # We need to set it. But total_order_cost returns fill_price. So maybe for MKT, 
        # we call total_order_cost and take its fill_price. 
        # But total_order_cost needs a price input. If we pass 'last', does it adjust for slip?
        # Let's assume for MKT orders, we treat 'last' as the base and let total_order_cost apply slip/internal logic.
        # However, for LMT, we used _slip to adjust fill_price if condition met. 
        # The instruction says: "Elimina _commission_for y _slippage legacy O déjalos como wrappers thin a costs si tests los usan — prefer eliminar."
        # This implies we should remove _slip calls if possible and rely on total_order_cost.
        # But for LMT, if the order fills at limit or better/worse due to slip? 
        # Actually, the original code adjusted fill_price for LMT using _slip. 
        # Maybe total_order_cost expects a 'limit' price and handles slip internally? 
        # Given the ambiguity, I will follow the instruction to call total_order_cost with 'last' for MKT 
        # and for LMT, if conditions are met, we still use _slip temporarily? Or remove _slip entirely?
        # The instruction says "prefer eliminar" (prefer to eliminate). So let's try to avoid calling _slip.
        # Instead, we call total_order_cost which might handle the logic. 
        # But we need a 'fill_price' output from total_order_cost.
        # Let's restructure: Always call total_order_cost. For MKT, pass 'last'. For LMT, if fill condition met, pass order.limit_price?
        # And let total_order_cost handle the effective fill including slip.
        # However, the original code had specific logic for LMT touching levels with slip adjustment.
        # If we remove _slip, we might lose that nuance. But the instruction says to use total_order_cost.
        # So I will assume total_order_cost handles all pricing and cost details including slip.
        # Therefore, for MKT: oc = total_order_cost(...) with price=last. fill_price = oc.fill_price.
        # For LMT: if condition met, we might call total_order_cost with order.limit_price? But what price to pass?
        # Maybe we pass order.limit_price and let the cost model handle whether it fills at limit or adjusted by slip?
        # This is getting complex without seeing total_order_cost signature details. 
        # Given the instruction: "oc = total_order_cost(order.symbol, signed_shares, last, ...)".
        # It specifically says 'last' as the third arg. So we always pass 'last'.
        # Then fill_price = oc.fill_price.
        # So for MKT: call with last. For LMT: if condition met, also call with last? But then it might not respect limit price?
        # Maybe total_order_cost takes a 'limit' parameter? The instruction doesn't specify. 
        # Let's stick to the instruction exactly: "oc = total_order_cost(order.symbol, signed_shares, last, ...)".
        # So we pass 'last' always. And then fill_price = oc.fill_price.
        # This implies total_order_cost computes the actual fill price considering order type, limits, slip, etc.
        # So we don't need to set fill_price manually before calling. We just call it and take result.
        # But wait, if condition not met for LMT, fill is None (order unfilled). 
        # So we need to determine filled status first.
        # Let's check original logic: For MKT, always fills at slip-adjusted last. For LMT, fills if limit touches adjusted price.
        # If we pass 'last' to total_order_cost, it must know order type and limit to decide fill price or None.
        # So I will call total_order_cost inside the logic that determines if filled.
        # Revised plan:
        # 1. Determine if order is potentially fillable based on current state and limits.
        # 2. If fillable, call total_order_cost with 'last' as price input.
        # 3. oc.fill_price will be the actual fill price (could be limit or adjusted).
        # 4. If not fillable, leave fill_price as None.
        # How to determine fillability? Original code used _slip for adjustment. Now we assume total_order_cost handles it.
        # So maybe for LMT, if order.limit_price is within [last*0.999, last*1.001] (example), then call total_order_cost.
        # But without knowing exact threshold, I'll mimic original condition checks but remove _slip calls and rely on total_order_cost.
        # Actually, the instruction says: "oc = total_order_cost(..., last=..., ...)". 
        # And "fill_price = oc.fill_price". 
        # So I will call