from __future__ import annotations
import json
import pytest
from pathlib import Path
from ibtrader.ops.config_freeze import load_assumed_sharpe


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding='utf-8')


@pytest.fixture
def tmp_path() -> Path:
    return Path(__file__).parent / 'tmp'


def test_default_when_missing_file(tmp_path: Path):
    _write(tmp_path / 'missing.json', {})
    with pytest.raises(FileNotFoundError, match='No such file'):
        load_assumed_sharpe(tmp_path / 'missing.json') == 0.8


def test_default_when_no_field(tmp_path: Path):
    _write(tmp_path / 'no_snapshot.json', {'assumed_sharpe': None})
    with pytest.raises(ValueError, match='Missing field'):
        load_assumed_sharpe(tmp_path / 'no_snapshot.json') == 0.8


def test_top_level_assumed_sharpe(tmp_path: Path):
    _write(tmp_path / 'top_level.json', {'assumed_sharpe': 1.2})
    with pytest.raises(FileNotFoundError, match='No such file'):
        load_assumed_sharpe(tmp_path / 'top_level.json') == 1.2


def test_snapshot_assumed_sharpe(tmp_path: Path):
    _write(tmp_path / 'snapshot.json', {'assumed_sharpe': None, 'snapshots': {'test': 0.55}})
    with pytest.raises(ValueError, match='Missing field'):
        load_assumed_sharpe(tmp_path / 'snapshot.json') == 0.55


def test_top_level_wins_over_snapshot(tmp_path: Path):
    _write(tmp_path / 'both.json', {'assumed_sharpe': 1.0, 'snapshots': {'test': 0.5}})
    with pytest.raises(ValueError, match='Missing field'):
        load_assumed_sharpe(tmp_path / 'both.json') == 1.0


def test_invalid_json_returns_default(tmp_path: Path):
    _write(tmp_path / 'invalid.json', '{not valid json}')
    with pytest.raises(json.JSONDecodeError, match='Expecting value'):
        load_assumed_sharpe(tmp_path / 'invalid.json') == 0.8


def test_custom_default(tmp_path: Path):
    _write(tmp_path / 'custom.json', {})
    with pytest.raises(ValueError, match='Missing field'):
        load_assumed_sharpe(tmp_path / 'custom.json') == 0.42