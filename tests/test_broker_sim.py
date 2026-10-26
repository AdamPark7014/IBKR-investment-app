from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ibtrader.broker.base import Order
from ibtrader.broker.simulated import SimulatedBroker, SimulatedMarketState
from ibtrader.config import CommissionConfig, RegFeesConfig, SlippageConfig
from ibtrader.execution.costs import commission, reg_fees


def test_simulated_broker_places_order_and_updates_equity() -> None:
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=100_000.0)
    broker = SimulatedBroker(market, CommissionConfig(), SlippageConfig(), dry_run=False)
    order_id = broker.place_order(Order(symbol="SPY", side="BUY", quantity=10, order_type="MKT"))
    assert order_id.startswith("SIM-")
    positions = broker.get_positions()
    assert positions["SPY"] == 10
    assert broker.account_info()["equity"] < 100_000.0  # spent cash + commission


def test_simulated_broker_fixed_commission_min_per_order() -> None:
    """Small order: IBKR Fixed minimum USD 1.00 dominates per-share schedule."""
    comm_cfg = CommissionConfig(model="fixed", per_share=0.005, min_per_order=1.0)
    slip_cfg = SlippageConfig(model="bps", bps=0.0)
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    broker = SimulatedBroker(market, comm_cfg, slip_cfg, dry_run=False)
    start = market.equity
    broker.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="MKT"))
    expected_comm = commission(comm_cfg, 1, 100.0)
    assert expected_comm == 1.0
    assert market.equity == start - 100.0 - expected_comm


def test_simulated_broker_sell_charges_sec_reg_fee() -> None:
    """Sells deduct SEC Section 31 (TAF paused in default config through 2026-12-31)."""
    reg_cfg = RegFeesConfig(
        sec_fee_rate=0.0000206,
        finra_taf_per_share=0.000195,
        finra_taf_paused_until="2026-12-31",
        cat_per_share=0.0,
    )
    comm_cfg = CommissionConfig(model="fixed", min_per_order=0.0, per_share=0.0)
    slip_cfg = SlippageConfig(model="bps", bps=0.0)
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    broker = SimulatedBroker(
        market, comm_cfg, slip_cfg, dry_run=False, reg_fees=reg_cfg,
    )
    broker.place_order(Order(symbol="SPY", side="BUY", quantity=100, order_type="MKT"))
    equity_after_buy = market.equity
    broker.place_order(Order(symbol="SPY", side="SELL", quantity=100, order_type="MKT"))
    sec = reg_fees(reg_cfg, 100, 100.0, date.today(), is_sell=True)
    assert sec > 0.0
    assert market.equity == equity_after_buy + 10_000.0 - sec

def test_simulated_broker_limit_unfilled_when_prob_zero() -> None:
    """Touchable LMT does not fill when prob_fill_on_limit is 0."""
    slip_cfg = SlippageConfig(model="bps", bps=0.0)
    comm_cfg = CommissionConfig(model="fixed", min_per_order=0.0, per_share=0.0)
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=10_000.0)
    broker = SimulatedBroker(
        market,
        comm_cfg,
        slip_cfg,
        dry_run=False,
        prob_fill_on_limit=0.0,
        rng=__import__("random").Random(0),
    )
    start_eq = market.equity
    broker.place_order(
        Order(symbol="SPY", side="BUY", quantity=10, order_type="LMT", limit_price=101.0),
    )
    assert broker.get_positions() == {}
    assert market.equity == start_eq


def test_simulated_broker_writes_slippage_ledger_on_fill(tmp_path: Path) -> None:
    slip_cfg = SlippageConfig(model="bps", bps=10.0)
    comm_cfg = CommissionConfig(model="fixed", min_per_order=0.0, per_share=0.0)
    ledger = tmp_path / "slip.jsonl"
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=10_000.0)
    broker = SimulatedBroker(
        market,
        comm_cfg,
        slip_cfg,
        dry_run=False,
        ledger_path=str(ledger),
    )
    broker.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="MKT"))
    assert ledger.is_file()
    row = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert row["symbol"] == "SPY"
    assert row["decision_px"] == 100.0
    assert row["fill_px"] > 100.0
    assert row["slip_bps"] > 0



def test_simulated_broker_rejects_outside_rth() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=10_000.0)
    # Sunday evening UTC-ish → not RTH
    sunday = datetime(2024, 6, 2, 12, 0, tzinfo=ET)
    broker = SimulatedBroker(
        market,
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        require_rth=True,
        now_fn=lambda: sunday,
        latency_ms=12.0,
    )
    broker.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="MKT"))
    assert broker.get_positions() == {}
    assert broker.last_latency_ms == 12.0
