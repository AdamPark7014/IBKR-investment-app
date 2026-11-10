from __future__ import annotations

from ibtrader.broker.ib_gateway import IBGateway, market_data_type_for


def test_paper_orders_accept_delayed_quotes() -> None:
    assert market_data_type_for("paper_orders") == 3


def test_live_and_shadow_keep_live_quotes() -> None:
    assert market_data_type_for("live_orders") == 1
    assert market_data_type_for("shadow") == 1


class _FakeIB:
    def __init__(self) -> None:
        self.types: list[int] = []
        self.errorEvent = self

    def __iadd__(self, _handler: object) -> "_FakeIB":
        return self

    def reqMarketDataType(self, t: int) -> None:  # noqa: N802 - ib_async name
        self.types.append(t)


def test_gateway_requests_the_given_type() -> None:
    ib = _FakeIB()
    IBGateway(ib, market_data_type=market_data_type_for("paper_orders"))
    assert ib.types == [3]
