"""OrderManager state machine, idempotency, escalation and modes (audit 2026-11-07, §3.5)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from ibtrader.config import AppSettings, ExecutionConfig
from ibtrader.execution.order_manager import (
    BrokerOrderStatus,
    OrderGateway,
    OrderManager,
    OrderState,
    RateLimiter,
    execution_permission,
    order_ref_for,
)
from ibtrader.execution.rebalance import ProposedOrder

D = date(2026, 11, 9)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class FakeGateway(OrderGateway):
    """Scripted broker: ``behaviour`` per order kind ('limit'/'adaptive') → final status."""

    def __init__(self, clock: FakeClock, behaviour: Dict[str, BrokerOrderStatus],
                 existing: Optional[Dict[str, str]] = None, mid: Optional[float] = 100.0) -> None:
        self.clock = clock
        self.behaviour = behaviour
        self.existing = existing or {}
        self.mid = mid
        self.placed: List[tuple] = []
        self.cancelled: List[str] = []
        self.kind: Dict[str, str] = {}

    def existing_refs(self, prefix: str) -> Dict[str, str]:
        return dict(self.existing)

    def midpoint(self, symbol: str) -> Optional[float]:
        return self.mid

    def place_limit(self, symbol, side, qty, limit, order_ref) -> str:
        bid = str(len(self.placed) + 1)
        self.placed.append(("limit", symbol, side, qty, limit, order_ref))
        self.kind[bid] = "limit"
        return bid

    def place_adaptive_market(self, symbol, side, qty, order_ref) -> str:
        bid = str(len(self.placed) + 1)
        self.placed.append(("adaptive", symbol, side, qty, None, order_ref))
        self.kind[bid] = "adaptive"
        return bid

    def status(self, broker_id: str) -> BrokerOrderStatus:
        st = self.behaviour[self.kind[broker_id]]
        if broker_id in self.cancelled and st.status not in ("Filled",):
            return BrokerOrderStatus("Cancelled", st.filled, st.remaining, st.avg_fill_price, st.error)
        return st

    def cancel(self, broker_id: str) -> None:
        self.cancelled.append(broker_id)

    def sleep(self, seconds: float) -> None:
        self.clock.t += seconds


def _order(sym="SPY", side="BUY", qty=10, px=100.0) -> ProposedOrder:
    return ProposedOrder(symbol=sym, side=side, quantity=qty, ref_price=px, target_weight=0.1,
                         current_qty=0, target_qty=qty)


def _mgr(tmp: Path, gw, clock, **cfg) -> OrderManager:
    c = ExecutionConfig(order_timeout_sec=10, **cfg)
    return OrderManager(gw, c, ledger_path=tmp / "orders.jsonl", slippage_path=tmp / "slip.jsonl",
                        poll_interval_sec=1.0, clock=clock,
                        limiter=RateLimiter(1000, clock=clock, sleeper=lambda s: None))


def test_shadow_sends_nothing_and_logs(tmp_path: Path) -> None:
    clock = FakeClock()
    m = _mgr(tmp_path, None, clock)
    out = m.execute([_order()], D, send=False)
    assert out[0].state is OrderState.SHADOW
    rows = [json.loads(x) for x in (tmp_path / "orders.jsonl").read_text().splitlines()]
    assert rows[0]["state"] == "SHADOW" and rows[0]["order_ref"] == "ibt-20261109-SPY-BUY"


def test_limit_fills_and_records_slippage(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Filled", 10, 0, 100.05)})
    out = _mgr(tmp_path, gw, clock).execute([_order()], D, send=True)
    assert out[0].state is OrderState.FILLED and out[0].filled_qty == 10
    assert gw.placed[0][0] == "limit" and gw.placed[0][4] == 100.0 and gw.placed[0][5] == "ibt-20261109-SPY-BUY"
    slip = json.loads((tmp_path / "slip.jsonl").read_text().splitlines()[0])
    assert slip["source"] == "ibkr" and round(slip["slip_bps"], 2) == 5.0


def test_duplicate_order_ref_is_not_resent(tmp_path: Path) -> None:
    clock = FakeClock()
    ref = order_ref_for("ibt", D, "SPY", "BUY")
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Filled", 10, 0, 100.0)}, existing={ref: "Submitted"})
    out = _mgr(tmp_path, gw, clock).execute([_order()], D, send=True)
    assert out[0].state is OrderState.DUPLICATE and gw.placed == []


def test_timeout_escalates_to_adaptive_with_remainder(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {
        "limit": BrokerOrderStatus("Submitted", 4, 6, 100.0),
        "adaptive": BrokerOrderStatus("Filled", 6, 0, 101.0),
    })
    out = _mgr(tmp_path, gw, clock).execute([_order()], D, send=True)
    mo = out[0]
    assert mo.state is OrderState.FILLED and mo.filled_qty == 10
    assert gw.cancelled == ["1"]
    assert gw.placed[1][0] == "adaptive" and gw.placed[1][3] == 6 and gw.placed[1][5].endswith("-A")
    assert abs(mo.avg_fill_price - 100.6) < 1e-9
    assert clock.t >= 10  # waited the full passive window


def test_no_escalation_cancels(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Submitted", 0, 10, 0.0)})
    out = _mgr(tmp_path, gw, clock, escalate_to_adaptive=False).execute([_order()], D, send=True)
    assert out[0].state is OrderState.CANCELLED and out[0].reason == "limit_timeout"


def test_broker_error_is_rejected_not_silent(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Inactive", error="IBKR 321: read-only API")})
    out = _mgr(tmp_path, gw, clock).execute([_order()], D, send=True)
    assert out[0].state is OrderState.REJECTED and "read-only" in (out[0].reason or "")


def test_no_midpoint_skips(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {}, mid=None)
    out = _mgr(tmp_path, gw, clock).execute([_order()], D, send=True)
    assert out[0].state is OrderState.SKIPPED and gw.placed == []


def test_limit_offset(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Filled", 10, 0, 99.9)})
    _mgr(tmp_path, gw, clock, limit_offset_bps=10).execute([_order(side="SELL")], D, send=True)
    assert gw.placed[0][4] == 99.9


def test_rate_limiter_waits() -> None:
    clock = FakeClock()
    waits: List[float] = []

    def sleeper(s: float) -> None:
        waits.append(s)
        clock.t += s

    rl = RateLimiter(2, clock=clock, sleeper=sleeper)
    for _ in range(4):
        rl.acquire()
    assert waits and abs(sum(waits) - 1.0) < 1e-9


def test_execution_permission_matrix() -> None:
    s = AppSettings(_env_file=None)
    assert execution_permission(s)[0] is True  # shadow
    s.execution.mode = "paper_orders"
    assert execution_permission(s) == (False, "TRADING__ALLOW_BROKER_ORDERS=false")
    s.trading.allow_broker_orders = True
    assert execution_permission(s)[0] is True
    s.execution.mode = "live_orders"
    assert execution_permission(s)[0] is False  # MODE=PAPER


class _Evt:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, h):
        self.handlers.append(h)
        return self


class _FakeIB:
    def __init__(self) -> None:
        self.errorEvent = _Evt()

    def reqMarketDataType(self, t: int) -> None:
        self.mdt = t

    def sleep(self, s: float) -> None:
        pass


def test_ib_gateway_records_order_errors_but_not_info_codes() -> None:
    from ibtrader.broker.ib_gateway import IBGateway

    ib = _FakeIB()
    gw = IBGateway(ib)
    handler = ib.errorEvent.handlers[0]
    handler(7, 2104, "Market data farm connection is OK")
    handler(-1, 1100, "connectivity lost")
    handler(8, 201, "Order rejected - reason: no permissions")
    st = gw.status("8")
    assert st.error and "201" in st.error
    assert gw.status("7").error == "unknown order id"
    assert ib.mdt == 1


def test_waves_sells_first_and_one_timeout_per_wave(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Submitted", 0, 10, 0.0),
                             "adaptive": BrokerOrderStatus("Filled", 10, 0, 100.0)})
    orders = [_order("SPY", "BUY"), _order("IEF", "SELL"), _order("GLD", "BUY"), _order("TLT", "SELL")]
    out = _mgr(tmp_path, gw, clock).execute(orders, D, send=True)
    assert all(m.state is OrderState.FILLED for m in out)
    sides = [p[2] for p in gw.placed]
    assert sides == ["SELL", "SELL", "SELL", "SELL", "BUY", "BUY", "BUY", "BUY"]  # limits+adaptive per wave
    # Two waves × (passive + adaptive) windows, not 4 orders × 2 windows.
    assert 20 <= clock.t <= 22


def test_slippage_is_measured_against_arrival_midpoint(tmp_path: Path) -> None:
    clock = FakeClock()
    gw = FakeGateway(clock, {"limit": BrokerOrderStatus("Filled", 10, 0, 102.0)}, mid=102.0)
    _mgr(tmp_path, gw, clock).execute([_order(px=100.0)], D, send=True)  # overnight gap +2 %
    slip = json.loads((tmp_path / "slip.jsonl").read_text().splitlines()[0])
    assert slip["decision_px"] == 102.0 and abs(slip["slip_bps"]) < 1e-9
