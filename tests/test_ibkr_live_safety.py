from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ibtrader.broker.base import Order
from ibtrader.broker.ibkr import IBKRBroker
from ibtrader.config import AppSettings, IBConfig, TradingConfig


def _live_settings(
    *,
    expected_account: str | None = None,
    confirmed: str = "yes",
    allow_broker_orders: bool = False,
) -> AppSettings:
    return AppSettings.model_construct(
        mode="LIVE",
        live_trading_confirmed=confirmed,
        ib=IBConfig(expected_account=expected_account, live_port=4001, paper_port=4002),
        trading=TradingConfig(allow_broker_orders=allow_broker_orders),
    )


def test_live_safety_ok_fails_without_expected_account() -> None:
    settings = _live_settings(expected_account=None)
    ok, msg = settings.live_safety_ok()
    assert ok is False
    assert "IB_EXPECTED_ACCOUNT" in msg


def test_live_safety_ok_fails_with_blank_expected_account() -> None:
    settings = _live_settings(expected_account="   ")
    ok, msg = settings.live_safety_ok()
    assert ok is False
    assert "IB_EXPECTED_ACCOUNT" in msg


def test_live_safety_ok_passes_with_account_and_confirmed() -> None:
    settings = _live_settings(expected_account="U1234567", confirmed="yes")
    ok, msg = settings.live_safety_ok()
    assert ok is True
    assert msg


def test_place_order_rejects_when_broker_orders_disabled() -> None:
    settings = AppSettings(trading=TradingConfig(allow_broker_orders=False))
    broker = IBKRBroker(settings)
    broker._connected = True
    broker.ib = MagicMock()
    broker.ib.isConnected.return_value = True

    with pytest.raises(RuntimeError, match="Broker orders disabled"):
        broker.place_order(Order(symbol="SPY", side="BUY", quantity=1, order_type="MKT"))


def test_connect_readonly_when_broker_orders_disabled() -> None:
    settings = AppSettings(trading=TradingConfig(allow_broker_orders=False))
    broker = IBKRBroker(settings)
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    broker.ib = mock_ib

    broker.connect()

    mock_ib.connect.assert_called_once()
    _, kwargs = mock_ib.connect.call_args
    assert kwargs.get("readonly") is True


def test_connect_not_readonly_when_broker_orders_enabled() -> None:
    settings = AppSettings(trading=TradingConfig(allow_broker_orders=True))
    broker = IBKRBroker(settings)
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    broker.ib = mock_ib

    broker.connect()

    _, kwargs = mock_ib.connect.call_args
    assert kwargs.get("readonly") is False


def test_place_order_live_runs_ensure_live_safety_when_enabled() -> None:
    settings = _live_settings(
        expected_account="U1234567",
        confirmed="yes",
        allow_broker_orders=True,
    )
    broker = IBKRBroker(settings)
    broker._connected = True
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_trade = MagicMock()
    mock_trade.order.orderId = 42
    mock_ib.placeOrder.return_value = mock_trade
    broker.ib = mock_ib

    with patch.object(broker, "_ensure_live_safety") as ensure:
        order_id = broker.place_order(
            Order(symbol="SPY", side="BUY", quantity=1, order_type="MKT")
        )
        ensure.assert_called_once()
        assert order_id == "42"


def test_ensure_live_safety_fails_without_expected_account() -> None:
    settings = _live_settings(
        expected_account=None,
        confirmed="yes",
        allow_broker_orders=True,
    )
    broker = IBKRBroker(settings)
    broker._connected = True
    broker.ib = MagicMock()
    broker.ib.isConnected.return_value = True

    with pytest.raises(RuntimeError, match="IB_EXPECTED_ACCOUNT"):
        broker._ensure_live_safety()
