from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ibtrader.ops.cli import app as cli_mod_app


def test_config_freeze_cli_smoke(tmp_path: Path) -> None:
    freeze = tmp_path / "paper_config_freeze.json"
    runner = CliRunner()

    res_write = runner.invoke(
        cli_mod_app,
        ["config-freeze", "--write", "--path", str(freeze)],
    )
    assert res_write.exit_code == 0, res_write.stdout + str(res_write.exception)
    w = json.loads(res_write.stdout)
    assert w["ok"] is True
    assert w["expected"] == w["actual"]
    assert w["orders_sent"] == 0
    assert freeze.is_file()

    res_verify = runner.invoke(
        cli_mod_app,
        ["config-freeze", "--verify", "--path", str(freeze)],
    )
    assert res_verify.exit_code == 0, res_verify.stdout + str(res_verify.exception)
    v = json.loads(res_verify.stdout)
    assert v["ok"] is True
    assert v["expected"] == v["actual"]
    assert v["expected"] == w["expected"]
    assert v["orders_sent"] == 0

    missing = tmp_path / "missing_freeze.json"
    res_miss = runner.invoke(
        cli_mod_app,
        ["config-freeze", "--path", str(missing)],
    )
    assert res_miss.exit_code == 0, res_miss.stdout + str(res_miss.exception)
    m = json.loads(res_miss.stdout)
    assert m["ok"] is False
    assert m["reason"] == "missing_freeze"
    assert m["orders_sent"] == 0
