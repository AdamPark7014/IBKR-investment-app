"""Unit tests for V3 experiment registry JSONL (no network)."""

from __future__ import annotations

from pathlib import Path

from ibtrader.research.registry import (
    DEFAULT_REGISTRY_FILE,
    ExperimentRecord,
    default_registry_path,
    load_experiments,
    save_experiment,
)


def _record(candidate_id: str = "sma_10_30", **kwargs) -> ExperimentRecord:
    base = dict(
        exp_id="exp-test",
        created_at_utc="2026-09-27T00:00:00+00:00",
        git_commit="0577f2f",
        candidate_id=candidate_id,
        params={"fast": 10, "slow": 30},
        oos={"sharpe": 0.1, "max_dd": -0.12, "trade_count": 7},
        buy_hold_oos={"sharpe": 0.2, "max_dd": -0.10},
        gate_passed=False,
        gate_reasons=["oos_sharpe<0 or undefined"],
        notes="unit",
    )
    base.update(kwargs)
    return ExperimentRecord(**base)


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "research" / "experiments.jsonl"
    r1 = _record("sma_5_20", gate_passed=True, gate_reasons=[])
    r2 = _record("sma_10_30")

    save_experiment(path, r1)
    save_experiment(path, r2)

    rows = load_experiments(path)
    assert len(rows) == 2
    assert rows[0].candidate_id == "sma_5_20"
    assert rows[0].gate_passed is True
    assert rows[1].candidate_id == "sma_10_30"
    assert rows[1].params["fast"] == 10
    assert rows[1].oos["trade_count"] == 7


def test_load_missing_file_returns_empty(tmp_path: Path):
    assert load_experiments(tmp_path / "missing.jsonl") == []


def test_append_is_jsonl(tmp_path: Path):
    path = tmp_path / "experiments.jsonl"
    save_experiment(path, _record("a"))
    save_experiment(path, _record("b"))
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    assert lines[0].startswith("{") and lines[0].endswith("}")


def test_default_registry_path_under_reports_research():
    assert default_registry_path() == DEFAULT_REGISTRY_FILE
    assert DEFAULT_REGISTRY_FILE.parts[-2:] == ("research", "experiments.jsonl")
    custom = default_registry_path("/tmp/myreports")
    assert custom == Path("/tmp/myreports") / "research" / "experiments.jsonl"


def test_load_tolerates_extra_and_missing_optional_fields(tmp_path: Path):
    path = tmp_path / "experiments.jsonl"
    # Minimal legacy-ish row (no dataset_hash / extra)
    path.write_text(
        '{"exp_id":"e1","created_at_utc":"t","git_commit":"c","candidate_id":"x",'
        '"params":{},"oos":{},"buy_hold_oos":null,"gate_passed":false,'
        '"gate_reasons":[],"unexpected_field":1}\n',
        encoding="utf-8",
    )
    rows = load_experiments(path)
    assert len(rows) == 1
    assert rows[0].candidate_id == "x"
    assert rows[0].dataset_hash == ""
    assert rows[0].extra == {}
