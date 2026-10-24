from __future__ import annotations

import json
from pathlib import Path

import pytest

from ibtrader.ops.paper_curve import load_equity_points, max_drawdown, paper_max_drawdown


def test_empty() -> None:
    assert max_drawdown([]) is None
    assert max_drawdown([100.0]) is None
    missing = Path("definitely_missing_paper_equity_xyz.jsonl")
    assert load_equity_points(missing) == []
    assert paper_max_drawdown(missing) is None


def test_rising(tmp_path: Path) -> None:
    assert max_drawdown([100.0, 110.0, 120.0]) == pytest.approx(0.0)
    path = tmp_path / "rising.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for i, eq in enumerate([100.0, 110.0, 120.0]):
            fh.write(json.dumps({"ts": f"2024-01-0{i+1}", "equity": eq}) + "\n")
    assert paper_max_drawdown(path) == pytest.approx(0.0)


def test_classic_dd_100_80_90(tmp_path: Path) -> None:
    assert max_drawdown([100.0, 80.0, 90.0]) == pytest.approx(0.2)
    path = tmp_path / "paper_equity.jsonl"
    rows = [
        {"ts": "2024-01-01", "equity": 100},
        {"ts": "2024-01-02", "equity": 80},
        {"ts": "2024-01-03", "equity": 90},
    ]
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    assert paper_max_drawdown(path) == pytest.approx(0.2)
    points = load_equity_points(path)
    assert len(points) == 3
    assert all(isinstance(pt["equity"], float) for pt in points)
