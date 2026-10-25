from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ibtrader.ops.cli import app as cli_mod_app

runner = CliRunner()


def test_config_freeze_smoke() -> None:
    with runner.isolated_filesystem(temp_dir=Path.cwd()):
        tmp_path = Path(tempfile.mkdtemp())
        freeze_file = tmp_path / "frozen.json"

        result = runner.invoke(cli_mod_app, ["config-freeze", "--write", f"--path={freeze_file}"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["ok"] is True
        assert output["expected"] == "frozen"
        assert output["actual"] == "frozen"
        assert output["orders_sent"] == 0
        assert freeze_file.exists()

        result_verify = runner.invoke(cli_mod_app, ["config-freeze", "--verify", f"--path={freeze_file}"])
        assert result_verify.exit_code == 0
        output_verify = json.loads(result_verify.stdout)
        assert output_verify["ok"] is True
        assert output_verify["expected"] == "frozen"
        assert output_verify["actual"] == "frozen"
        assert output_verify["orders_sent"] == 0


def test_config_freeze_verify_missing_path() -> None:
    result = runner.invoke(cli_mod_app, ["config-freeze", "--verify"])
    assert result.exit_code != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert output.get("reason") == "missing_freeze"
    assert output["orders_sent"] == 0