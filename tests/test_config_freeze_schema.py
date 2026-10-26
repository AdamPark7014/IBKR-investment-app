"""The paper freeze covers mode, trading and strategy and is never re-baselined silently."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ibtrader.config import AppSettings
from ibtrader.ops.cli import app as cli_mod_app
from ibtrader.ops.config_freeze import (
    FREEZE_SCHEMA,
    config_hash,
    snapshot_settings,
    verify_freeze,
    write_freeze,
)

LEGACY_SECTIONS = ("universe", "benchmark", "risk", "commission", "slippage", "reg_fees", "engine")


def test_snapshot_includes_mode_trading_and_strategy() -> None:
    snap = snapshot_settings(AppSettings())
    for key in ("mode", "live_trading_confirmed", "trading", "strategy"):
        assert key in snap
    assert snap["mode"] == "PAPER"
    assert snap["trading"]["allow_broker_orders"] is False


def test_changes_are_detected_while_the_file_exists(tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    s = AppSettings()
    payload = write_freeze(path, s)
    assert payload["schema"] == FREEZE_SCHEMA
    assert verify_freeze(path, s)["ok"] is True

    s.strategy.params = {**dict(s.strategy.params), "fast_window": 7}
    v = verify_freeze(path, s)
    assert v["ok"] is False and v["reason"] == "hash_mismatch" and v["changed_sections"] == ["strategy"]

    s2 = AppSettings()
    s2.trading.direction = "long_short"
    v2 = verify_freeze(path, s2)
    assert v2["ok"] is False and v2["changed_sections"] == ["trading"]
    # verify never rewrites the file
    assert json.loads(path.read_text(encoding="utf-8"))["hash"] == payload["hash"]


def test_legacy_schema_is_reported_not_accepted(tmp_path: Path) -> None:
    s = AppSettings()
    snap = snapshot_settings(s)
    legacy = {k: snap[k] for k in LEGACY_SECTIONS}
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps({"hash": config_hash(legacy), "snapshot": legacy}), encoding="utf-8")
    v = verify_freeze(path, s)
    assert v["ok"] is False and v["reason"] == "freeze_schema_outdated" and v["legacy_match"] is True

    s.risk.drawdown_limit_pct = 35.0  # a legacy section changed too → real drift
    v2 = verify_freeze(path, s)
    assert v2["reason"] == "hash_mismatch" and v2["changed_sections"] == ["risk"]


def test_cli_write_refuses_to_rebaseline_a_changed_config(tmp_path: Path, monkeypatch) -> None:
    freeze = tmp_path / "paper_config_freeze.json"
    runner = CliRunner()
    res = runner.invoke(cli_mod_app, ["config-freeze", "--write", "--path", str(freeze)])
    assert res.exit_code == 0, res.stdout
    first = json.loads(freeze.read_text(encoding="utf-8"))["hash"]

    monkeypatch.setenv("TRADING__ALLOW_BROKER_ORDERS", "true")
    res2 = runner.invoke(cli_mod_app, ["config-freeze", "--write", "--path", str(freeze)])
    assert res2.exit_code == 1
    out2 = json.loads(res2.stdout)
    assert out2["written"] is False and out2["reason"] == "hash_mismatch" and "trading" in out2["changed_sections"]
    assert json.loads(freeze.read_text(encoding="utf-8"))["hash"] == first

    res3 = runner.invoke(cli_mod_app, ["config-freeze", "--write", "--force", "--path", str(freeze)])
    assert res3.exit_code == 0
    assert json.loads(freeze.read_text(encoding="utf-8"))["hash"] != first
