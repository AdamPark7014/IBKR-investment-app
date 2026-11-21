

def test_cash_etf_can_use_a_higher_order_cap() -> None:
    """Estacionar efectivo en letras va más rápido; los ETF de riesgo siguen con el tope normal."""
    from ibtrader.config import PretradeConfig
    from ibtrader.execution.rebalance import build_rebalance_orders
    from ibtrader.risk.pretrade import PretradeContext, check_orders, order_cap

    cfg = PretradeConfig(max_order_notional_usd=10_000, max_cash_order_notional_usd=100_000)
    assert order_cap(cfg, "bil", ["BIL"]) == 100_000 and order_cap(cfg, "SPY", ["BIL"]) == 10_000
    assert order_cap(PretradeConfig(), "BIL", ["BIL"]) == 10_000  # sin configurar: mismo tope
    prices = {"BIL": 100.0, "SPY": 500.0}
    orders = build_rebalance_orders({"BIL": 0.6, "SPY": 0.3}, {}, prices, 1_000_000.0, max_notional=10_000,
                                    max_notional_by_symbol={"BIL": order_cap(cfg, "BIL", ["BIL"])})
    by = {o.symbol: o for o in orders}
    assert by["BIL"].notional == 100_000 and by["SPY"].notional == 10_000
    ctx = PretradeContext(nav=1_000_000.0, positions={}, prices=prices, cash_symbols=["BIL"])
    dec = check_orders(orders, ctx, cfg)
    assert {o.symbol for o in dec.approved} == {"BIL", "SPY"}
    too_big = build_rebalance_orders({"SPY": 0.3}, {}, prices, 1_000_000.0, max_notional=100_000)
    assert check_orders(too_big, ctx, cfg).rejected[0][1].startswith("max_order_notional")
