"""``--use-ai`` only goes through the puerta (IA-CLAUDE.md) and never sends ``temperature``."""

from __future__ import annotations

import dataclasses
import sys
import types
from typing import Any

import pytest
from typer.testing import CliRunner

from ibtrader.intelligence.brief import ai_brief, puerta_config_error
from ibtrader.intelligence.prompt_pack import PromptPack
from ibtrader.ops.cli import app as cli_mod_app


def test_prompt_pack_has_no_temperature() -> None:
    assert "temperature" not in {f.name for f in dataclasses.fields(PromptPack)}
    assert PromptPack().model == "claude-haiku-5-5" and PromptPack().effort == "low"


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({}, "ANTHROPIC_BASE_URL is not set"),
        ({"ANTHROPIC_BASE_URL": "https://api.anthropic.com", "ANTHROPIC_API_KEY": "pia_x"}, "not at the puerta"),
        ({"ANTHROPIC_BASE_URL": "https://ia.zynoratek.com"}, "ANTHROPIC_API_KEY is not set"),
        ({"ANTHROPIC_BASE_URL": "https://ia.zynoratek.com", "ANTHROPIC_API_KEY": "sk-ant-real"}, "not a puerta token"),
    ],
)
def test_puerta_config_errors(env: dict, fragment: str) -> None:
    problem = puerta_config_error(env)
    assert problem is not None and fragment in problem
    assert "sk-ant-real" not in problem  # the key itself is never echoed


def test_puerta_config_ok() -> None:
    assert puerta_config_error({"ANTHROPIC_BASE_URL": "https://ia.zynoratek.com", "ANTHROPIC_API_KEY": "pia_t"}) is None
    assert puerta_config_error({"ANTHROPIC_BASE_URL": "http://puerta-ia:8080", "ANTHROPIC_API_KEY": "pia_t"}) is None


def test_ai_brief_without_puerta_stays_deterministic(monkeypatch: Any) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-allowed")
    out = ai_brief({"as_of": "2026-10-23"}, use_ai=True)
    assert out["source"] == "deterministic"
    assert out["note"].startswith("puerta_not_configured")


def test_ai_brief_sends_no_temperature_and_checks_stop_reason(monkeypatch: Any) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ia.zynoratek.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "pia_ibtrader_test")
    seen: dict = {}

    class _Block:
        type = "text"
        text = "Resumen."

    class _Resp:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        def create(self, **kwargs: Any) -> Any:
            seen.update(kwargs)
            return _Resp()

    class _Client:
        messages = _Messages()

    # The SDK is an optional extra (``.[ai]``): a stand-in module keeps this test offline everywhere.
    fake_sdk = types.ModuleType("anthropic")
    fake_sdk.Anthropic = lambda *a, **k: _Client()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    out = ai_brief({"as_of": "2026-10-23"}, use_ai=True)
    assert out["source"] == "ai" and out["text"] == "Resumen."
    assert "temperature" not in seen and "top_p" not in seen and "top_k" not in seen
    assert seen["model"] == "claude-haiku-5-5"
    assert seen["extra_headers"] == {"x-proceso": "ibtrader-brief"}
    assert seen["extra_body"] == {"output_config": {"effort": "low"}}

    _Resp.stop_reason = "max_tokens"
    cut = ai_brief({"as_of": "2026-10-23"}, use_ai=True)
    assert cut["source"] == "ai_fallback" and cut["note"] == "stop_reason=max_tokens"


def test_cli_use_ai_fails_clearly_without_puerta(monkeypatch: Any) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = CliRunner(mix_stderr=False).invoke(cli_mod_app, ["autopilot", "--use-ai"])
    assert res.exit_code == 2
    assert "puerta" in (res.stderr or "")
