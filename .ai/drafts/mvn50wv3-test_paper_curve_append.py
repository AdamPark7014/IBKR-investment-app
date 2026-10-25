from __future__ import annotations

import pytest
from pathlib import Path
from ibtrader.ops.paper_curve import append_equity_point, estimate_mark_to_market


def test_append_equity_point_writes_jsonl(tmp_path: Path) -> None:
    """Test that appending equity points writes to JSONL correctly."""
    file = tmp_path / "equity.jsonl"
    append_equity_point(file, equity=100.5, ts="2024-01-01T00:00:00Z")
    with open(file) as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert "100.5" in lines[0] and "2024-01-01T00:00:00Z" in lines[0]

    append_equity_point(file, equity=101.0, ts="2024-01-02T00:00:00Z")
    with open(file) as f:
        lines = f.readlines()
    assert len(lines) == 2
    assert "101.0" in lines[1] and "2024-01-02T00:00:00Z" in lines[1]


def test_estimate_mark_to_market_basic() -> None:
    """Test basic mark-to-market calculation."""
    held = {"AAPL": 10.0}
    last_prices = {"AAPL": 150.0}
    cash = 100.0
    mtm = estimate_mark_to_market(held=held, last_prices=last_prices, cash=cash)
    assert abs(mtm - 1600.0) < 1e-6


def test_estimate_mark_to_market_none_when_unpriced() -> None:
    """Test that MTM returns None when asset is not priced and no cash."""
    held = {"UNKNOWN": 5.0}
    last_prices = {}
    cash = 0.0
    mtm = estimate_mark_to_market(held=held, last_prices=last_prices, cash=cash)
    assert mtm is None