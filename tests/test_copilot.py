"""Copiloto de Claude: opina en sombra, se mide sin mirar al futuro e investiga por la compuerta."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from ibtrader.intelligence import copilot as cp


class FakeClient:
    def __init__(self, text: str) -> None:
        self.kw: Dict[str, Any] = {}
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
        )

        def create(**kw: Any) -> Any:
            self.kw = kw
            return resp

        self.messages = SimpleNamespace(create=create)


OPINION = json.dumps({
    "summary": "El sistema mantiene acciones y bonos.", "risks": ["subida de tipos"],
    "views": [
        {"symbol": "SPY", "stance": "aumentar", "conviction": 3, "reason": "tendencia fuerte"},
        {"symbol": "TLT", "stance": "reducir", "conviction": 3, "reason": "tendencia débil"},
        {"symbol": "XYZ", "stance": "aumentar", "conviction": 3, "reason": "inventado"},
    ],
})


def test_opinion_uses_haiku_by_default_and_drops_unknown_symbols(tmp_path: Path) -> None:
    facts = cp.build_facts("2026-11-09", {"SPY": 0.5, "TLT": 0.5}, {"SPY": 0.4}, {"SPY": [100.0] * 70}, -0.02)
    assert facts["etf"]["SPY"]["ret_21d"] == 0.0 and facts["etf"]["TLT"]["ret_1d"] is None
    c = FakeClient(OPINION)
    op = cp.daily_opinion(facts, data_dir=tmp_path, client=c)
    assert op is not None and c.kw["model"] == "claude-haiku-5-5"
    assert [v.symbol for v in op.views] == ["SPY", "TLT"]
    assert c.kw["extra_headers"] == {"x-proceso": "ibtrader-copiloto"}


def test_tilt_keeps_gross_and_never_levers() -> None:
    views = [{"symbol": "SPY", "stance": "aumentar", "conviction": 3},
             {"symbol": "TLT", "stance": "reducir", "conviction": 3}]
    t = cp.copilot_tilt({"SPY": 0.5, "TLT": 0.5}, views)
    assert sum(t.values()) == pytest.approx(1.0)
    assert t["SPY"] == pytest.approx(0.6) and t["TLT"] == pytest.approx(0.4)
    assert cp.copilot_tilt({"SPY": 1.0}, [{"symbol": "SPY", "stance": "mantener", "conviction": 3}]) == {"SPY": 1.0}


def test_score_uses_only_prices_after_each_opinion(tmp_path: Path) -> None:
    path = tmp_path / "op.jsonl"
    op = cp.Opinion.model_validate_json(OPINION)
    w = {"SPY": 0.5, "TLT": 0.5}
    # SPY sube 10 %, TLT cae 10 % tras la primera opinión: la inclinación a SPY gana 2 %.
    cp.record_opinion(path, "2026-11-09", w, {"SPY": 100.0, "TLT": 100.0}, op)
    cp.record_opinion(path, "2026-11-10", w, {"SPY": 110.0, "TLT": 90.0}, op)
    cp.record_opinion(path, "2026-11-11", w, {"SPY": 110.0, "TLT": 90.0}, op)
    sc = cp.score_opinions(path)
    assert sc["opiniones"] == 3 and sc["sesiones_medidas"] == 2
    assert sc["exceso_total"] == pytest.approx(0.02)
    assert sc["estado"] == "insuficiente"


def test_hypotheses_filtered_to_existing_rules(tmp_path: Path) -> None:
    text = json.dumps({"hypotheses": [
        {"name": "Lenta + const", "weighting": "hrp", "rationale": "menos rotación",
         "rules": [{"rule": "ewmac64_256", "weight": 3}, {"rule": "long_const", "weight": 1},
                   {"rule": "regla_inventada", "weight": 5}]},
        {"name": "solo inventadas", "weighting": "equal", "rationale": "x",
         "rules": [{"rule": "magia", "weight": 1}]},
    ]})
    hyps = cp.propose_hypotheses({"verdict": "FAIL"}, ["ewmac64_256", "long_const"], data_dir=tmp_path,
                                 client=FakeClient(text))
    assert len(hyps) == 1
    h = hyps[0]
    assert h.name == "copiloto_lenta___const" and h.rules == ["ewmac64_256", "long_const"]
    assert h.rule_weights == pytest.approx({"ewmac64_256": 0.75, "long_const": 0.25})
    f = tmp_path / "h.json"
    f.write_text(json.dumps({"hypotheses": [h.model_dump()]}))
    assert cp.load_hypotheses(f)[0] == h


def test_no_puerta_means_no_opinion_and_no_crash(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cp.daily_opinion({"etf": {}}, data_dir=tmp_path) is None
