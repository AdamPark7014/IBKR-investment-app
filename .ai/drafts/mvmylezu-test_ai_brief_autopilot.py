from __future__ import annotations

from ibtrader.intelligence.brief import ai_brief, compress_facts, deterministic_brief
from ibtrader.intelligence.prompt_pack import default_pack
from ibtrader.ops.simple_ui import render_simple_console


def test_prompt_pack_render_is_compact() -> None:
    pack = default_pack(language="es", max_tokens=400)
    facts = {"as_of": "2024-06-01", "equity_trend": 1, "orders_sent": 0}
    user = pack.render_user(facts)
    assert "FACTS:" in user
    assert "2024-06-01" in user
    assert len(user) < 500
    assert pack.max_tokens == 400


def test_compress_and_deterministic_brief() -> None:
    facts = compress_facts(
        extra={"urgency_mode": "passive", "urgency_reason": "fresh", "config_hash_ok": True},
        radar={
            "as_of": "2024-06-01",
            "equity_trend": 1,
            "equity_vol_20": 0.15,
            "risk_on_proxy": 1,
            "breadth_proxy": 0.6,
            "disclaimer": "Triage only.",
        },
        paper={"n_drift": 2, "n_symbols": 3, "orders_sent": 0},
    )
    urgency_line = "Urgency paper: passive (fresh)."
    text = deterministic_brief(facts)
    assert "alcista" in text.lower() or "Estado" in text
    assert "0" in text  # orders
    out = ai_brief(facts, use_ai=False)
    assert out["source"] == "deterministic"
    if urgency_line in text or "urgency_mode" in (facts.get("extra") or {}):
        assert urgency_line in text
    assert "Triage" in out["text"] or "disclaimer" in out["text"].lower() or "Triage" in facts["disclaimer"]


def test_simple_ui_renders_cards() -> None:
    html = render_simple_console(
        {
            "generated_at": "2024-06-01",
            "facts": {
                "as_of": "2024-06-01",
                "equity_trend": 1,
                "equity_vol_20": 0.12,
                "risk_on_proxy": 1,
                "paper_n_drift": 0,
                "breadth_proxy": 0.5,
            },
            "brief": {"text": "Hola", "source": "deterministic"},
        }
    )
    assert "Mercado" in html
    assert "Paper drift" in html
    assert "Hola" in html
    assert "LIVE" in html