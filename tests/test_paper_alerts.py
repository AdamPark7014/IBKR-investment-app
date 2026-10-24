from __future__ import annotations

from ibtrader.ops.alerts import evaluate_paper_alerts


def test_alerts_info_always() -> None:
    a = evaluate_paper_alerts(max_drawdown=None, n_drift=0, orders_sent=0)
    assert any(x.severity == "info" for x in a)


def test_alerts_drift_warn() -> None:
    a = evaluate_paper_alerts(max_drawdown=None, n_drift=5, orders_sent=0)
    assert any(x.code == "paper_drift" for x in a)


def test_alerts_dd_kill() -> None:
    a = evaluate_paper_alerts(max_drawdown=0.40, assumed_sharpe=0.8, n_drift=0, orders_sent=0)
    assert any(x.severity == "kill_recommend" for x in a)


def test_orders_warn() -> None:
    a = evaluate_paper_alerts(max_drawdown=None, n_drift=0, orders_sent=1)
    assert any(x.code == "orders_unexpected" for x in a)
