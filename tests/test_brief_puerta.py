"""Claude only goes through the puerta (IA-CLAUDE.md)."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from ibtrader.intelligence.brief import puerta_config_error
from ibtrader.ops.cli import app as cli_mod_app


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({}, "falta ANTHROPIC_BASE_URL"),
        ({"ANTHROPIC_BASE_URL": "https://api.anthropic.com", "ANTHROPIC_API_KEY": "pia_x"}, "no a la puerta"),
        ({"ANTHROPIC_BASE_URL": "https://ia.zynoratek.com"}, "falta ANTHROPIC_API_KEY"),
        ({"ANTHROPIC_BASE_URL": "https://ia.zynoratek.com", "ANTHROPIC_API_KEY": "sk-ant-real"}, "no es un token"),
    ],
)
def test_puerta_config_errors(env: dict, fragment: str) -> None:
    problem = puerta_config_error(env)
    assert problem is not None and fragment in problem
    assert "sk-ant-real" not in problem  # the key itself is never echoed


def test_puerta_config_ok() -> None:
    assert puerta_config_error({"ANTHROPIC_BASE_URL": "https://ia.zynoratek.com", "ANTHROPIC_API_KEY": "pia_t"}) is None
    assert puerta_config_error({"ANTHROPIC_BASE_URL": "http://puerta-ia:8080", "ANTHROPIC_API_KEY": "pia_t"}) is None


def test_cli_use_ai_fails_clearly_without_puerta(monkeypatch: Any) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = CliRunner(mix_stderr=False).invoke(cli_mod_app, ["ai-review"])
    assert res.exit_code == 2
    assert "puerta" in (res.stderr or "")
