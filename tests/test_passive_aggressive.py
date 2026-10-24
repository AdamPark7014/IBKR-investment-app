from __future__ import annotations

from ibtrader.execution.passive_aggressive import decide_urgency


def test_passive_within_window() -> None:
    d = decide_urgency(age_seconds=10.0, max_passive_seconds=60.0, touchable=True)
    assert d.mode == "passive"


def test_aggressive_aged() -> None:
    d = decide_urgency(age_seconds=90.0, max_passive_seconds=60.0, touchable=True)
    assert d.mode == "aggressive"


def test_aggressive_not_touchable() -> None:
    d = decide_urgency(age_seconds=1.0, touchable=False)
    assert d.mode == "aggressive"
