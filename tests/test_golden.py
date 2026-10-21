"""Golden files (Lean-style ``ExpectedStatistics``): any drift in engine, costs or strategies fails here.

Each ``tests/golden/<strategy>.json`` freezes the stats and the SHA-256 of the
order list produced by running that strategy over ``tests/fixtures`` with the
library-default settings. This test recomputes every snapshot and compares:
hashes, integers and the universe exactly; floats within rel 1e-9.

If a change is intended (engine fix, new cost model, strategy tweak) regenerate
the files on purpose and commit them in their own explicit commit:

    ibtrader golden-regen --yes

No network, no cache, no ``.env`` (see ``ibtrader.ops.cli.golden_settings``).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.ops.cli import (
    GOLDEN_REGEN_COMMAND,
    GOLDEN_STRATEGIES,
    compare_golden,
    compute_golden_snapshot,
    orders_hash,
)

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

REQUIRED_KEYS = {
    "strategy",
    "generated_at_utc",
    "git_commit",
    "config_hash",
    "dataset_hash",
    "universe",
    "stats",
    "orders_hash",
    "n_orders",
}
REQUIRED_STATS = {"sharpe", "cagr", "max_dd", "trade_count", "total_commission", "turnover", "final_equity"}


def _golden_paths() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*.json"))


def _out(res) -> str:  # type: ignore[no-untyped-def]
    """stdout + stderr; click < 8.2 mixes stderr into stdout and raises on ``res.stderr``."""
    try:
        err = res.stderr
    except ValueError:
        err = ""
    return res.stdout + (err or "")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_golden_dir_covers_every_strategy() -> None:
    stems = {p.stem for p in _golden_paths()}
    missing = set(GOLDEN_STRATEGIES) - stems
    assert not missing, f"missing golden files for {sorted(missing)}; generate with: {GOLDEN_REGEN_COMMAND}"
    unknown = stems - set(GOLDEN_STRATEGIES)
    assert not unknown, f"unexpected golden files {sorted(unknown)} (not in GOLDEN_STRATEGIES)"


@pytest.mark.parametrize("path", _golden_paths(), ids=lambda p: p.stem)
def test_golden_file_schema(path: Path) -> None:
    g = _load(path)
    assert REQUIRED_KEYS <= set(g), f"{path.name} lacks {sorted(REQUIRED_KEYS - set(g))}"
    assert REQUIRED_STATS <= set(g["stats"]), f"{path.name} stats lack {sorted(REQUIRED_STATS - set(g['stats']))}"
    assert g["strategy"] == path.stem
    assert len(g["orders_hash"]) == 64 and len(g["config_hash"]) == 64 and len(g["dataset_hash"]) == 64
    assert g["n_orders"] == g["stats"]["trade_count"]


@pytest.mark.parametrize("path", _golden_paths(), ids=lambda p: p.stem)
def test_golden_matches_fresh_run(path: Path) -> None:
    expected = _load(path)
    actual = compute_golden_snapshot(expected["strategy"], fixture_dir=str(FIXTURE_DIR))
    diffs = compare_golden(expected, actual)
    assert not diffs, (
        f"golden drift in tests/golden/{path.name} (strategy={expected['strategy']}):\n  - "
        + "\n  - ".join(diffs)
        + "\nIf this change is intended, regenerate on purpose and commit tests/golden/*.json explicitly:\n"
        f"    {GOLDEN_REGEN_COMMAND}"
    )


def test_snapshot_is_deterministic() -> None:
    a = compute_golden_snapshot("sma_crossover", fixture_dir=str(FIXTURE_DIR))
    b = compute_golden_snapshot("sma_crossover", fixture_dir=str(FIXTURE_DIR))
    assert compare_golden(a, b) == []
    assert a["orders_hash"] == b["orders_hash"]
    assert a["dataset_hash"] == b["dataset_hash"]
    assert a["config_hash"] == b["config_hash"]


def test_orders_hash_sensitive_to_order_price_and_qty() -> None:
    base = [("2024-02-12", "SPY", 826, 121.00930837416782, "signal"), ("2024-03-01", "SPY", -826, 130.5, "signal")]
    h = orders_hash(base)
    assert len(h) == 64
    assert orders_hash(list(reversed(base))) != h
    assert orders_hash([(base[0][0], "SPY", 825, base[0][3], "signal"), base[1]]) != h
    # Price differences beyond 6 dp are ignored; at 6 dp they count.
    assert orders_hash([(base[0][0], "SPY", 826, 121.0093083741 + 1e-10, "signal"), base[1]]) == h
    assert orders_hash([(base[0][0], "SPY", 826, 121.009309, "signal"), base[1]]) != h
    # The reason column is provenance, not part of the hash.
    assert orders_hash([(base[0][0], "SPY", 826, base[0][3], "stop_loss"), base[1]]) == h


def test_compare_golden_names_the_metric_that_moved() -> None:
    actual = compute_golden_snapshot("tsmom", fixture_dir=str(FIXTURE_DIR))
    tampered = copy.deepcopy(actual)
    tampered["stats"]["cagr"] = (actual["stats"]["cagr"] or 0.0) * 1.01 + 0.01
    tampered["orders_hash"] = "0" * 64
    diffs = compare_golden(tampered, actual)
    assert any(d.startswith("stats.cagr") for d in diffs), diffs
    assert any(d.startswith("orders_hash") for d in diffs), diffs
    assert not any(d.startswith("stats.sharpe") for d in diffs), diffs
    # Within tolerance → silent.
    tiny = copy.deepcopy(actual)
    tiny["stats"]["final_equity"] = actual["stats"]["final_equity"] * (1.0 + 1e-12)
    assert compare_golden(tiny, actual) == []


def test_golden_regen_requires_yes(tmp_path: Path) -> None:
    out = tmp_path / "golden"
    res = CliRunner().invoke(cli_mod.app, ["golden-regen", "--out-dir", str(out), "--fixture-dir", str(FIXTURE_DIR)])
    assert res.exit_code == 2, _out(res)
    assert "--yes" in _out(res)
    assert not out.exists() or not list(out.glob("*.json"))


def test_golden_regen_writes_every_strategy(tmp_path: Path) -> None:
    out = tmp_path / "golden"
    res = CliRunner().invoke(
        cli_mod.app,
        ["golden-regen", "--yes", "--out-dir", str(out), "--fixture-dir", str(FIXTURE_DIR)],
    )
    assert res.exit_code == 0, _out(res) + str(res.exception)
    files = sorted(p.stem for p in out.glob("*.json"))
    assert files == sorted(GOLDEN_STRATEGIES)
    for strategy in GOLDEN_STRATEGIES:
        written = _load(out / f"{strategy}.json")
        fresh = compute_golden_snapshot(strategy, fixture_dir=str(FIXTURE_DIR))
        assert compare_golden(written, fresh) == [], strategy
        assert written["regenerate"] == GOLDEN_REGEN_COMMAND
