from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ibtrader.ops.stack import PaperStack, cmd_paper_stack


def test_upsert_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "paper_stack.sqlite"
    ts = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    stack = PaperStack(db)
    stack.upsert_desired("AAPL", 10.0, ts)
    stack.upsert_held("AAPL", 7.0, ts)
    stack.upsert_desired("MSFT", 5.0, ts)

    snap = stack.snapshot()
    assert snap["desired"]["AAPL"] == 10.0
    assert snap["desired"]["MSFT"] == 5.0
    assert snap["held"]["AAPL"] == 7.0

    again = PaperStack(db).snapshot()
    assert again["desired"]["AAPL"] == 10.0
    assert again["desired"]["MSFT"] == 5.0
    assert again["held"]["AAPL"] == 7.0


def test_drift_and_sync(tmp_path: Path) -> None:
    db = tmp_path / "paper_stack.sqlite"
    stack = PaperStack(db)
    stack.sync_from_json(
        desired={"AAA": 3.0, "BBB": 1.0},
        held={"AAA": 1.0, "CCC": 2.0},
    )
    snap = stack.snapshot()
    assert set(snap["desired"]) == {"AAA", "BBB"}
    assert set(snap["held"]) == {"AAA", "CCC"}
    by_sym = {row["symbol"]: row for row in snap["drift"]}
    assert [row["symbol"] for row in snap["drift"]] == ["AAA", "BBB", "CCC"]
    assert by_sym["AAA"]["desired"] == 3.0
    assert by_sym["AAA"]["held"] == 1.0
    assert by_sym["AAA"]["delta"] == 2.0
    assert by_sym["BBB"]["desired"] == 1.0
    assert by_sym["BBB"]["held"] == 0.0
    assert by_sym["BBB"]["delta"] == 1.0
    assert by_sym["CCC"]["desired"] == 0.0
    assert by_sym["CCC"]["held"] == 2.0
    assert by_sym["CCC"]["delta"] == -2.0


def test_cmd_paper_stack_orders_sent_zero(tmp_path: Path) -> None:
    out = cmd_paper_stack(tmp_path / "ps.sqlite")
    assert out["orders_sent"] == 0
    assert "desired" in out
    assert "held" in out
    assert "drift" in out
