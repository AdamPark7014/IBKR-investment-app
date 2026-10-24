from __future__ import annotations
from ibtrader.ops.alerts import evaluate_paper_alerts

def test_always_has_triage_disclaimer() -> None:
    alerts = evaluate_paper_alerts(max_drawdown=None)
    assert any(a.code == 'triage_disclaimer' and a.severity == 'info' for a in alerts)

def test_orders_sent_warn() -> None:
    alerts = evaluate_paper_alerts(max_drawdown=None, orders_sent=1)
    assert any(a.code == 'orders_unexpected' and a.severity == 'warn' for a in alerts)
    assert any(a.message == 'broker orders unexpected in paper triage' for a in alerts)

def test_paper_drift_warn() -> None:
    high = evaluate_paper_alerts(max_drawdown=None, n_drift=5)
    low = evaluate_paper_alerts(max_drawdown=None, n_drift=4)
    assert any(a.code == 'paper_drift' and a.severity == 'warn' for a in high)
    assert not any(a.code == 'paper_drift' for a in low)

def test_dd_vs_sharpe_kill() -> None:
    # assumed_sharpe=0.8 -> threshold = min(0.35, 0.15+0.25/0.8) = min(0.35, 0.4625) = 0.35
    high = evaluate_paper_alerts(max_drawdown=0.36, assumed_sharpe=0.8)
    low = evaluate_paper_alerts(max_drawdown=0.20, assumed_sharpe=0.8)
    assert any(a.code == 'dd_vs_sharpe' and a.severity == 'kill_recommend' for a in high)
    assert not any(a.code == 'dd_vs_sharpe' for a in low)

def test_max_drawdown_none_skips_dd_rule() -> None:
    alerts = evaluate_paper_alerts(max_drawdown=None, assumed_sharpe=0.8)
    assert not any(a.code == 'dd_vs_sharpe' for a in alerts)