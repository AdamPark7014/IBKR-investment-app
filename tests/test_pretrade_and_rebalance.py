"""Target weights → orders → pre-trade gate (audit 2026-11-07, §3.4 and §5)."""

from __future__ import annotations

from datetime import date

from ibtrader.config import PretradeConfig
from ibtrader.execution.rebalance import build_rebalance_orders
from ibtrader.risk.pretrade import PretradeContext, check_orders

PX = {"SPY": 500.0, "TLT": 100.0, "GLD": 200.0}


def test_rebalance_basic_and_exits_first() -> None:
    orders = build_rebalance_orders({"SPY": 0.5, "TLT": 0.3}, {"GLD": 10, "SPY": 10}, PX, 20_000.0)
    by = {o.symbol: o for o in orders}
    assert orders[0].symbol == "GLD" and orders[0].is_exit and orders[0].side == "SELL"
    assert by["SPY"].side == "BUY" and by["SPY"].quantity == 10  # 20 target - 10 held
    assert by["TLT"].quantity == 60


def test_rebalance_skips_small_and_clips_large() -> None:
    small = build_rebalance_orders({"SPY": 0.51}, {"SPY": 20}, PX, 20_000.0, min_notional=1_000)
    assert small == []  # 0 share change after floor
    big = build_rebalance_orders({"TLT": 1.0}, {}, PX, 100_000.0, max_notional=10_000)
    assert big[0].quantity == 100 and big[0].notes  # clipped from 1000
    exit_ = build_rebalance_orders({}, {"TLT": 900}, PX, 100_000.0, min_notional=1e9, max_notional=1)
    assert exit_[0].quantity == 900 and exit_[0].is_exit  # exits are never skipped or clipped


def test_rebalance_ignores_missing_price() -> None:
    assert build_rebalance_orders({"XYZ": 0.5}, {}, PX, 10_000.0) == []


def _ctx(**kw):
    base = dict(nav=100_000.0, positions={}, prices=PX, allowed_symbols=["SPY", "TLT", "GLD"])
    base.update(kw)
    return PretradeContext(**base)


def test_pretrade_happy_path() -> None:
    orders = build_rebalance_orders({"SPY": 0.05, "TLT": 0.05}, {}, PX, 100_000.0)
    dec = check_orders(orders, _ctx(), PretradeConfig())
    assert len(dec.approved) == 2 and not dec.rejected and not dec.global_blocks


def test_pretrade_caps() -> None:
    cfg = PretradeConfig(max_order_notional_usd=10_000, max_weight_per_symbol=0.4)
    big = build_rebalance_orders({"SPY": 0.2}, {}, PX, 100_000.0)  # 20k order
    assert check_orders(big, _ctx(), cfg).rejected[0][1].startswith("max_order_notional")
    heavy = build_rebalance_orders({"TLT": 0.5}, {"TLT": 400}, PX, 100_000.0)  # 40k → 50k
    dec = check_orders(heavy, _ctx(positions={"TLT": 400}), PretradeConfig(max_order_notional_usd=50_000))
    assert dec.rejected[0][1].startswith("max_weight_per_symbol")
    bad = build_rebalance_orders({"SPY": 0.01}, {}, PX, 100_000.0)
    bad[0].limit_price = 600.0
    assert check_orders(bad, _ctx(), cfg).rejected[0][1].startswith("fat_finger")
    nope = build_rebalance_orders({"QQQ": 0.01}, {}, {**PX, "QQQ": 400.0}, 100_000.0)
    assert check_orders(nope, _ctx(), cfg).rejected[0][1] == "symbol_not_allowed"


def test_pretrade_no_shorts_and_gross() -> None:
    short = build_rebalance_orders({"SPY": -0.05}, {}, PX, 100_000.0)
    assert check_orders(short, _ctx(), PretradeConfig()).rejected[0][1] == "short_not_allowed"
    pos = {"SPY": 70, "TLT": 300}  # 35k + 30k = 65 %
    lev = build_rebalance_orders({"SPY": 0.35, "TLT": 0.3, "GLD": 0.4}, pos, PX, 100_000.0)
    dec = check_orders(lev, _ctx(positions=pos), PretradeConfig(max_order_notional_usd=50_000))
    assert any(r.startswith("max_gross_exposure") for _, r in dec.rejected)


def test_global_blocks_still_allow_reductions() -> None:
    pos = {"SPY": 100, "TLT": 10}
    orders = build_rebalance_orders({"SPY": 0.1, "TLT": 0.5}, pos, PX, 100_000.0)
    for kw in ({"killswitch_active": True}, {"data_fresh": False}, {"risk_can_increase": False}):
        dec = check_orders(orders, _ctx(positions=pos, **kw), PretradeConfig(max_order_notional_usd=50_000))
        assert [o.symbol for o in dec.approved] == ["SPY"]  # 100 → 20 shares, a reduction
        assert dec.rejected[0][0].symbol == "TLT" and dec.rejected[0][1].startswith("global_block")


def test_account_mismatch_blocks_everything() -> None:
    pos = {"SPY": 100}
    orders = build_rebalance_orders({}, pos, PX, 100_000.0)
    dec = check_orders(orders, _ctx(positions=pos, account_ok=False), PretradeConfig())
    assert not dec.approved and "account_mismatch" in dec.global_blocks


def test_stale_reference_and_order_count() -> None:
    orders = build_rebalance_orders({"SPY": 0.01}, {}, PX, 100_000.0)
    dec = check_orders(orders, _ctx(reference_date=date(2026, 11, 1), today=date(2026, 11, 9)), PretradeConfig())
    assert any(b.startswith("reference_prices_stale") for b in dec.global_blocks) and not dec.approved
    many = build_rebalance_orders({"SPY": 0.05, "TLT": 0.05, "GLD": 0.05}, {}, PX, 100_000.0)
    dec2 = check_orders(many, _ctx(), PretradeConfig(max_orders_per_run=2))
    assert len(dec2.approved) == 2 and dec2.rejected[0][1].startswith("max_orders_per_run")
