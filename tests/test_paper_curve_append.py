from pathlib import Path

from ibtrader.ops.paper_curve import append_equity_point, estimate_mark_to_market, load_equity_points


def test_append_and_mtm(tmp_path: Path) -> None:
    p = tmp_path / "paper_equity.jsonl"
    append_equity_point(p, 100.0, ts="a")
    append_equity_point(p, -1.0)  # skipped
    pts = load_equity_points(p)
    assert len(pts) == 1
    assert pts[0]["equity"] == 100.0
    assert estimate_mark_to_market({"SPY": 2.0}, {"SPY": 50.0}, cash=10.0) == 110.0
    assert estimate_mark_to_market({}, {}, cash=0.0) is None
