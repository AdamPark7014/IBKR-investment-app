from datetime import datetime, timezone
from pathlib import Path

from ibtrader.ops.urgency_age import load_open_order_age_seconds


def test_missing_file(tmp_path: Path) -> None:
    assert load_open_order_age_seconds(tmp_path / "nope.json") == 0.0


def test_age_seconds_key(tmp_path: Path) -> None:
    p = tmp_path / "o.json"
    p.write_text('{"age_seconds": 42.5}', encoding="utf-8")
    assert load_open_order_age_seconds(p) == 42.5


def test_opened_at_iso(tmp_path: Path) -> None:
    p = tmp_path / "o.json"
    p.write_text(
        '{"orders":[{"opened_at":"2026-10-24T12:00:00Z"}]}',
        encoding="utf-8",
    )
    now = datetime(2026, 10, 24, 12, 1, 30, tzinfo=timezone.utc)
    assert load_open_order_age_seconds(p, now=now) == 90.0
