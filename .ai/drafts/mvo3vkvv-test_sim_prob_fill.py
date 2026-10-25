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


def test_aged_lmt_fills_aggressive_even_if_limit_far(tmp_path: Path) -> None:
    """Test that aged LMT orders fill aggressively even if limit is far from market and prob_fill_on_limit=0."""
    ledger = tmp_path / "slip.jsonl"
    
    # Setup broker with aged order config
    market_aged = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    b_aged = SimulatedBroker(
        market_aged,
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        order_age_seconds=120.0,
        max_passive_seconds=60.0,
        prob_fill_on_limit=0.0,
        ledger_path=str(ledger),
        rng=random.Random(1),
    )
    
    # Place LMT far below market (not touchable)
    b_aged.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=90.0))
    
    # Assert position is filled aggressively despite far limit and prob_fill=0
    assert b_aged.get_positions().get("SPY", 0) == 1
    
    # Control: with default order_age_seconds (0.0), same conditions should NOT fill
    market_control = SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0)
    b_control = SimulatedBroker(
        market_control,
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        order_age_seconds=0.0,  # Default behavior
        max_passive_seconds=60.0,
        prob_fill_on_limit=0.0,
        ledger_path=str(ledger),
        rng=random.Random(2),  # Different seed to ensure no coincidence
    )
    
    b_control.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=90.0))
    assert b_control.get_positions().get("SPY", 0) == 0