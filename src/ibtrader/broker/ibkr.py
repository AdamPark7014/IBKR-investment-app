from __future__ import annotations

import threading
from typing import Any, Dict

from ib_async import IB, LimitOrder, MarketOrder, Stock
from ib_async.contract import Contract

from ..config import AppSettings
from ..logging import setup_logging
from .base import Broker, Order, Quote


class IBKRBroker(Broker):
    """
    Interactive Brokers broker via ib_insync (official API wrapper).
    Handles reconnects and basic order placement (market/limit).
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.ib = IB()
        self._connected = False
        self._lock = threading.Lock()
        self.log = setup_logging()

    def connect(self) -> None:
        host = self.settings.ib.host
        port = self.settings.ib_port()
        client_id = self.settings.ib.client_id
        self.log.info(
            "ib_connect_start host=%s port=%s client_id=%s", host, port, client_id
        )
        readonly = not self.settings.trading.allow_broker_orders
        with self._lock:
            if not self._connected:
                self.ib.connect(
                    host, port, clientId=client_id, readonly=readonly, timeout=5
                )
                self._connected = self.ib.isConnected()
        self.log.info("ib_connect_end connected=%s", self._connected)

    def disconnect(self) -> None:
        with self._lock:
            if self._connected:
                self.ib.disconnect()
                self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self.ib.isConnected()

    def account_info(self) -> Dict[str, Any]:
        if not self.is_connected():
            self.connect()
        accounts = self.ib.managedAccounts()
        acct = accounts[0] if accounts else ""
        values = self.ib.accountValues()
        equity = next((float(v.value) for v in values if v.tag == "NetLiquidation"), 0.0)
        return {"account": acct, "equity": equity}

    def _ib_contract(self, symbol: str) -> Contract:
        return Stock(symbol, "SMART", "USD")

    def _ensure_live_safety(self) -> None:
        ok, msg = self.settings.live_safety_ok()
        if not ok:
            raise RuntimeError(msg)
        expected = self.settings.ib.expected_account
        if expected:
            acct = self.account_info().get("account", "")
            if acct != expected:
                raise RuntimeError(
                    f"Cuenta LIVE conectada '{acct}' no coincide con IB_EXPECTED_ACCOUNT."
                )

    def place_order(self, order: Order) -> str:
        if not self.settings.trading.allow_broker_orders:
            raise RuntimeError(
                "Broker orders disabled (set TRADING__ALLOW_BROKER_ORDERS=true to enable)."
            )
        if not self.is_connected():
            self.connect()
        if self.settings.mode.upper() == "LIVE":
            self._ensure_live_safety()
        contract = self._ib_contract(order.symbol)
        action = "BUY" if order.side.upper() == "BUY" else "SELL"
        if order.order_type == "MKT":
            ib_order: Any = MarketOrder(action, order.quantity)
        else:
            ib_order = LimitOrder(action, order.quantity, float(order.limit_price or 0.0))
        # Set time in force when available
        try:
            ib_order.tif = order.time_in_force
        except Exception:
            pass
        trade = self.ib.placeOrder(contract, ib_order)
        self.ib.sleep(0.1)
        return str(trade.order.orderId)

    def get_quote(self, symbol: str) -> Quote:
        if not self.is_connected():
            self.connect()
        contract = self._ib_contract(symbol)
        ticker = self.ib.reqMktData(contract, "", False, False)
        # Let a tick arrive
        for _ in range(10):
            if ticker.last or ticker.bid or ticker.ask:
                break
            self.ib.sleep(0.2)
        return Quote(
            symbol=symbol,
            bid=float(ticker.bid or 0) or None,
            ask=float(ticker.ask or 0) or None,
            last=float(ticker.last or 0) or None,
        )

    def get_positions(self) -> Dict[str, int]:
        if not self.is_connected():
            self.connect()
        positions = self.ib.positions()
        by_symbol: Dict[str, int] = {}
        for p in positions:
            sym = p.contract.symbol
            by_symbol[sym] = by_symbol.get(sym, 0) + int(p.position)
        return by_symbol

    def cancel_all(self) -> None:
        if not self.is_connected():
            self.connect()
        self.ib.reqGlobalCancel()

