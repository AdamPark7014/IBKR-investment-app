from __future__ import annotations

import random
from pathlib import Path

from ibtrader.broker.base import Order
from ibtrader.broker.simulated import SimulatedBroker, SimulatedMarketState
from ibtrader.config import CommissionConfig, SlippageConfig
from ibtrader.ops.slippage_ledger import summarize


def test_lmt_prob_fill_deterministic(tmp_path: Path) -> None:
    ledger = tmp_path / "slip.jsonl"
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    # Always fill
    b_fill = SimulatedBroker(
        market,
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        prob_fill_on_limit=1.0,
        ledger_path=str(ledger),
        rng=random.Random(1),
    )
    b_fill.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=100.0))
    assert b_fill.get_positions().get("SPY", 0) == 1
    assert summarize(ledger, 30)["n"] == 1

    market2 = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    b_miss = SimulatedBroker(
        market2,
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        prob_fill_on_limit=0.0,
        ledger_path=str(ledger),
        rng=random.Random(1),
    )
    before = market2.equity
    b_miss.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=100.0))
    assert b_miss.get_positions().get("SPY", 0) == 0
    assert market2.equity == before


def test_lmt_partial_fill_frac(tmp_path: Path) -> None:
    ledger = tmp_path / "slip.jsonl"
    market = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    broker = SimulatedBroker(
        market,
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        prob_fill_on_limit=1.0,
        partial_fill_frac=0.5,
        ledger_path=str(ledger),
        rng=random.Random(1),
    )
    broker.place_order(Order(symbol="SPY", side="BUY", quantity=10, order_type="LMT", limit_price=100.0))
    assert abs(broker.get_positions().get("SPY", 0)) == 5
