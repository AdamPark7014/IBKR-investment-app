from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class OrderSpec:
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    order_type: str = "MKT"  # MKT or LMT
    limit_price: Optional[float] = None
    time_in_force: str = "DAY"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_tag: Optional[str] = None


def build_bracket_order(
    symbol: str,
    side: str,
    quantity: int,
    entry_type: str = "MKT",
    entry_price: Optional[float] = None,
    take_profit: Optional[float] = None,
    stop_loss: Optional[float] = None,
    time_in_force: str = "DAY",
) -> Dict[str, Any]:
    """
    Return a normalized bracket spec to be mapped by the broker adapter.
    """
    return {
        "parent": {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": entry_type,
            "limit_price": entry_price,
            "tif": time_in_force,
        },
        "children": {
            "take_profit": take_profit,
            "stop_loss": stop_loss,
        },
    }

