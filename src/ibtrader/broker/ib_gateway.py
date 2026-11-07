"""``OrderGateway`` over ``ib_async`` (audit 2026-11-07, §3.5).

Thin on purpose: the logic lives in ``execution.order_manager`` and is tested with a fake.
This class only translates calls and records broker errors per order id from ``errorEvent``.
It never places an order on its own; ``OrderManager`` decides.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..execution.order_manager import BrokerOrderStatus, OrderGateway

# IBKR informational codes that arrive on errorEvent but are not order failures.
_INFO_CODES = {
    399,  # order warning (e.g. will be held until open)
    2104, 2106, 2107, 2108, 2158,  # market data / HMDS farm OK
    2109,  # outside RTH attribute ignored
    10167,  # displaying delayed market data
}


class IBGateway(OrderGateway):
    def __init__(self, ib: Any, *, regular_hours_only: bool = True, market_data_type: int = 1) -> None:
        """``ib`` is a connected ``ib_async.IB``. ``market_data_type`` 1 = live, 3 = delayed."""
        self.ib = ib
        self.rth = regular_hours_only
        self._errors: Dict[int, str] = {}
        self._trades: Dict[str, Any] = {}
        self.ib.errorEvent += self._on_error
        try:
            self.ib.reqMarketDataType(int(market_data_type))
        except Exception:  # noqa: BLE001 - older gateways ignore it
            pass

    # -- events ------------------------------------------------------------------------
    def _on_error(self, req_id: int, code: int, msg: str, *_: Any) -> None:
        if int(code) in _INFO_CODES or int(req_id) <= 0:
            return
        self._errors[int(req_id)] = f"IBKR {code}: {msg}"

    # -- helpers -----------------------------------------------------------------------
    @staticmethod
    def _contract(symbol: str) -> Any:
        from ib_async import Stock

        return Stock(symbol.upper(), "SMART", "USD")

    def _qualified(self, symbol: str) -> Any:
        c = self._contract(symbol)
        q = self.ib.qualifyContracts(c)
        if not q:
            raise RuntimeError(f"contract not found: {symbol}")
        return q[0]

    # -- OrderGateway ------------------------------------------------------------------
    def existing_refs(self, prefix: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        try:
            self.ib.reqAllOpenOrders()
        except Exception:  # noqa: BLE001
            pass
        for t in self.ib.openTrades():
            ref = str(getattr(t.order, "orderRef", "") or "")
            if ref.startswith(prefix):
                out[ref] = str(t.orderStatus.status)
        today = datetime.now(timezone.utc).date()
        try:
            fills: List[Any] = list(self.ib.reqExecutions())
        except Exception:  # noqa: BLE001
            fills = list(self.ib.fills())
        for f in fills:
            ref = str(getattr(f.execution, "orderRef", "") or "")
            t = getattr(f, "time", None) or getattr(f.execution, "time", None)
            if ref.startswith(prefix) and (t is None or t.date() == today):
                out.setdefault(ref, "Filled")
        return out

    def midpoint(self, symbol: str) -> Optional[float]:
        c = self._qualified(symbol)
        tickers = self.ib.reqTickers(c)
        if not tickers:
            return None
        tk = tickers[0]
        bid, ask = tk.bid, tk.ask
        if bid and ask and bid > 0 and ask > 0 and math.isfinite(bid) and math.isfinite(ask) and ask >= bid:
            return (float(bid) + float(ask)) / 2.0
        return None  # no two-sided quote → the manager skips the order

    def _place(self, symbol: str, order: Any) -> str:
        c = self._qualified(symbol)
        trade = self.ib.placeOrder(c, order)
        self.ib.sleep(0.5)
        oid = str(trade.order.orderId)
        self._trades[oid] = trade
        return oid

    def place_limit(self, symbol: str, side: str, qty: int, limit: float, order_ref: str) -> str:
        from ib_async import LimitOrder

        o = LimitOrder(side.upper(), int(qty), float(limit))
        o.orderRef = order_ref
        o.tif = "DAY"
        o.outsideRth = not self.rth
        return self._place(symbol, o)

    def place_adaptive_market(self, symbol: str, side: str, qty: int, order_ref: str) -> str:
        from ib_async import MarketOrder, TagValue

        o = MarketOrder(side.upper(), int(qty))
        o.orderRef = order_ref
        o.tif = "DAY"
        o.algoStrategy = "Adaptive"
        o.algoParams = [TagValue("adaptivePriority", "Normal")]
        return self._place(symbol, o)

    def status(self, broker_id: str) -> BrokerOrderStatus:
        self.ib.sleep(0)
        trade = self._trades.get(str(broker_id))
        err = self._errors.get(int(broker_id)) if str(broker_id).isdigit() else None
        if trade is None:
            return BrokerOrderStatus(status="Unknown", error=err or "unknown order id")
        st = trade.orderStatus
        return BrokerOrderStatus(
            status=str(st.status),
            filled=float(st.filled or 0.0),
            remaining=float(st.remaining or 0.0),
            avg_fill_price=float(st.avgFillPrice or 0.0),
            error=err,
        )

    def cancel(self, broker_id: str) -> None:
        trade = self._trades.get(str(broker_id))
        if trade is not None:
            self.ib.cancelOrder(trade.order)
            self.ib.sleep(0.5)

    def sleep(self, seconds: float) -> None:
        self.ib.sleep(seconds)


__all__ = ["IBGateway"]
