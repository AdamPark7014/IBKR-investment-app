from __future__ import annotations

from ibtrader.ops.simple_ui import render_simple_console


def test_simple_ui_new_cards_when_payload_has_keys() -> None:
    payload = {
        "facts": {
            "as_of": "2024-06-01",
            "equity_trend": 1,
            "equity_vol_20": 0.12,
            "risk_on_proxy": 1,
            "paper_n_drift": 0,
            "breadth_proxy": 0.5,
        },
        "brief": {"text": "Hola", "source": "deterministic"},
        "urgency": {"mode": "passive", "reason": "fresh"},
        "paper_stack": {"n_drift": 3},
        "paper_vs_oos": {"dd_ok": True},
    }
    html = render_simple_console(payload)

    assert "Urgency" in html
    assert "Stack drift" in html
    assert "vs OOS" in html

    assert "Mercado" in html
    assert "Paper drift" in html
    assert "Alerts" in html

    assert "passive" in html
    assert "3" in html
    assert "OK" in html

    assert "--bg:#0f1419" in html or "var(--bg)" in html


def test_simple_ui_vs_oos_breach_and_missing() -> None:
    payload_breach = {
        "facts": {"as_of": "2024-06-01", "equity_trend": 1},
        "brief": {"text": "Test", "source": "test"},
        "paper_vs_oos": {"dd_ok": False},
    }
    html_breach = render_simple_console(payload_breach)
    assert "BREACH" in html_breach
    assert "vs OOS" in html_breach

    payload_missing = {
        "facts": {"as_of": "2024-06-01", "equity_trend": 1},
        "brief": {"text": "Test", "source": "test"},
    }
    html_missing = render_simple_console(payload_missing)
    assert "Urgency" in html_missing
    assert "Stack drift" in html_missing
    assert "vs OOS" in html_missing
    assert "—" in html_missing


def test_simple_ui_urgency_from_facts_extra() -> None:
    payload = {
        "facts": {
            "as_of": "2024-06-01",
            "equity_trend": 1,
            "extra": {"urgency_mode": "aggressive"},
        },
        "brief": {"text": "Hola", "source": "deterministic"},
    }
    html = render_simple_console(payload)
    assert "Urgency" in html
    assert "aggressive" in html
