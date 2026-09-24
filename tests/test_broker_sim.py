from __future__ import annotations

from ibtrader.broker.base import Order
from ibtrader.broker.simulated import SimulatedBroker, SimulatedMarketState
from ibtrader.config import CommissionConfig, SlippageConfig


def test_simulated_broker_places_order_and_updates_equity() -> None:
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=100_000.0)
    broker = SimulatedBroker(market, CommissionConfig(), SlippageConfig(), dry_run=False)
    order_id = broker.place_order(Order(symbol="SPY", side="BUY", quantity=10, order_type="MKT"))
    assert order_id.startswith("SIM-")
    positions = broker.get_positions()
    assert positions["SPY"] == 10
    assert broker.account_info()["equity"] < 100_000.0  # spent cash + commission

