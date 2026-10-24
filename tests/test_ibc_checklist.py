from __future__ import annotations

import json

from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.ops.ibc_checklist import build_ibc_checklist


def test_build_ibc_checklist_shape() -> None:
    payload = build_ibc_checklist()
    assert payload["phase"] == "paper-ops"
    assert len(payload["items"]) >= 5
    assert "disclaimer" in payload
    assert any(i["id"] == "gateway_paper_port" for i in payload["items"])


def test_ibc_checklist_cli_smoke() -> None:
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["ibc-checklist"])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    data = json.loads(res.stdout)
    assert data["phase"] == "paper-ops"
