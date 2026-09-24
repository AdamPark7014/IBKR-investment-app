from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Quote:
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None


@dataclass
class Order:
    symbol: str
    side: str  # "BUY" | "SELL"
    quantity: int
    order_type: str = "MKT"  # "MKT" | "LMT"
    limit_price: Optional[float] = None
    time_in_force: str = "DAY"
    attach_stop: Optional[float] = None
    attach_target: Optional[float] = None
    client_tag: Optional[str] = None  # for journal/debug


@dataclass
class Fill:
    symbol: str
    side: str
    quantity: int
    price: float
    commission: float = 0.0
    timestamp: Optional[str] = None
    order_id: Optional[str] = None


class Broker(abc.ABC):
    @abc.abstractmethod
    def connect(self) -> None:
        ...

    @abc.abstractmethod
    def disconnect(self) -> None:
        ...

    @abc.abstractmethod
    def is_connected(self) -> bool:
        ...

    @abc.abstractmethod
    def account_info(self) -> Dict[str, Any]:
        ...

    @abc.abstractmethod
    def get_positions(self) -> Dict[str, int]:
        ...

    @abc.abstractmethod
    def place_order(self, order: Order) -> str:
        ...

    @abc.abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        ...

    @abc.abstractmethod
    def cancel_all(self) -> None:
        ...

