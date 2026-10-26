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


def _sim(prob: float, age: float, **kw: object) -> SimulatedBroker:
    return SimulatedBroker(
        SimulatedMarketState(last_prices={"SPY": 100.0}, equity=50_000.0),
        CommissionConfig(model="fixed", per_share=0.0, min_per_order=0.0),
        SlippageConfig(model="bps", bps=0.0),
        dry_run=False,
        prob_fill_on_limit=prob,
        order_age_seconds=age,
        max_passive_seconds=60.0,
        **kw,  # type: ignore[arg-type]
    )


def test_aged_lmt_never_fills_through_its_limit() -> None:
    # Aged past max_passive_seconds → aggressive, but a BUY LMT at 90 with the market at 100 must not
    # fill (before: it filled at ~100, 11 % above its own limit).
    aged = _sim(prob=0.0, age=120.0, rng=random.Random(1))
    aged.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=90.0))
    assert aged.get_positions().get("SPY", 0) == 0
    sell = _sim(prob=0.0, age=120.0, rng=random.Random(1))
    sell.place_order(Order(symbol="SPY", side="SELL", quantity=1, order_type="LMT", limit_price=110.0))
    assert sell.get_positions().get("SPY", 0) == 0


def test_aged_marketable_lmt_fills_for_sure_within_limit() -> None:
    # Marketable limit (101 ≥ modelled fill 100) and aged: certain fill even with prob_fill=0, at ≤ limit.
    aged = _sim(prob=0.0, age=120.0, rng=random.Random(1))
    before = aged.market_state.equity
    aged.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=101.0))
    assert aged.get_positions().get("SPY", 0) == 1
    assert before - aged.market_state.equity <= 101.0 + 1e-9
    # Young order, same marketable limit, prob_fill=0 → passive draw misses.
    young = _sim(prob=0.0, age=0.0, rng=random.Random(1))
    young.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=101.0))
    assert young.get_positions().get("SPY", 0) == 0


def test_default_rng_is_seeded_and_reproducible() -> None:
    def fills(seed: int | None) -> list[int]:
        kw = {} if seed is None else {"seed": seed}
        b = _sim(prob=0.5, age=0.0, **kw)
        out = []
        for _ in range(30):
            before = b.get_positions().get("SPY", 0)
            b.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="LMT", limit_price=100.0))
            out.append(b.get_positions().get("SPY", 0) - before)
        return out

    assert fills(None) == fills(None)  # default seed 0: same draws every run
    assert fills(None) == fills(0)
    assert 0 < sum(fills(None)) < 30
