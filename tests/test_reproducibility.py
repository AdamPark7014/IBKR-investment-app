from __future__ import annotations

import json
import os
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod


def test_reproducible_artifacts_with_same_inputs(monkeypatch, tmp_path) -> None:
    # Use fixture provider and tmp reports dir
    monkeypatch.setenv("DATA__PROVIDERS", '["fixture"]')
    monkeypatch.setenv("DATA__FIXTURE_DIR", "./tests/fixtures")
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path))
    runner = CliRunner()
    run_id = "reprotest"
    res1 = runner.invoke(cli_mod.app, ["backtest-sample", "--exp-id", run_id])
    assert res1.exit_code == 0
    art_path = os.path.join(str(tmp_path), f"artifact_{run_id}.json")
    with open(art_path, "r", encoding="utf-8") as f:
        art1 = json.load(f)
    # Run again with same settings/fixtures
    res2 = runner.invoke(cli_mod.app, ["backtest-sample", "--exp-id", run_id])
    assert res2.exit_code == 0
    with open(art_path, "r", encoding="utf-8") as f:
        art2 = json.load(f)
    assert art1["metrics"] == art2["metrics"]
    assert art1["dataset"]["hash"] == art2["dataset"]["hash"]
    assert art1["config_hash"] == art2["config_hash"]

