import json
import os
from pathlib import Path

import pytest

from ibtrader.ops.config_freeze import load_assumed_sharpe


@pytest.fixture()
def default_path(tmp_path: Path) -> Path:
    return tmp_path / "assumed.sharpe.freeze"


def write_freeze(path: Path, value: dict) -> None:
    with path.open("w") as f:
        json.dump(value, f)


def test_default_when_missing_file(default_path: Path) -> None:
    assert load_assumed_sharpe(str(default_path)) == 0.8


def test_default_when_no_field(tmp_path: Path) -> None:
    path = tmp_path / "assumed.sharpe.freeze"
    write_freeze(path, {"hash": "abc", "snapshot": {}})
    assert load_assumed_sharpe(str(path)) == 0.8


def test_top_level_assumed_sharpe(tmp_path: Path) -> None:
    path = tmp_path / "assumed.sharpe.freeze"
    write_freeze(path, {"assumed_sharpe": 1.2, "hash": "x", "snapshot": {}})
    assert load_assumed_sharpe(str(path)) == 1.2


def test_snapshot_assumed_sharpe(tmp_path: Path) -> None:
    path = tmp_path / "assumed.sharpe.freeze"
    write_freeze(path, {"hash": "x", "snapshot": {"assumed_sharpe": 0.55}})
    assert load_assumed_sharpe(str(path)) == 0.55


def test_top_level_wins_over_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "assumed.sharpe.freeze"
    write_freeze(path, {"hash": "x", "snapshot": {"assumed_sharpe": 0.5}, "assumed_sharpe": 1.0})
    assert load_assumed_sharpe(str(path)) == 1.0


def test_invalid_json_returns_default(tmp_path: Path) -> None:
    path = tmp_path / "assumed.sharpe.freeze"
    with path.open("w") as f:
        f.write("not valid json {{{")
    assert load_assumed_sharpe(str(path)) == 0.8


def test_custom_default(tmp_path: Path) -> None:
    path = tmp_path / "assumed.sharpe.freeze"
    custom_loader = lambda p: load_assumed_sharpe(p, default=0.42)
    assert custom_loader(str(path)) == 0.42