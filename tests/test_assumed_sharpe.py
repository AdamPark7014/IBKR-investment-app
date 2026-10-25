from __future__ import annotations

import json
from pathlib import Path

from ibtrader.ops.config_freeze import load_assumed_sharpe


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_default_when_missing_file(tmp_path: Path) -> None:
    assert load_assumed_sharpe(tmp_path / "missing.json") == 0.8


def test_default_when_no_field(tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    _write(path, {"hash": "abc", "snapshot": {}})
    assert load_assumed_sharpe(path) == 0.8


def test_top_level_assumed_sharpe(tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    _write(path, {"assumed_sharpe": 1.2, "hash": "x", "snapshot": {}})
    assert load_assumed_sharpe(path) == 1.2


def test_snapshot_assumed_sharpe(tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    _write(path, {"hash": "x", "snapshot": {"assumed_sharpe": 0.55}})
    assert load_assumed_sharpe(path) == 0.55


def test_top_level_wins_over_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    _write(
        path,
        {"assumed_sharpe": 1.0, "hash": "x", "snapshot": {"assumed_sharpe": 0.5}},
    )
    assert load_assumed_sharpe(path) == 1.0


def test_invalid_json_returns_default(tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    assert load_assumed_sharpe(path) == 0.8


def test_custom_default(tmp_path: Path) -> None:
    assert load_assumed_sharpe(tmp_path / "missing.json", default=0.42) == 0.42
