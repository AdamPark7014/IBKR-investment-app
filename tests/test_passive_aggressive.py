from __future__ import annotations

from ibtrader.execution.passive_aggressive import UrgencyDecision, decide_urgency


def test_aggressive_not_touchable() -> None:
    d = decide_urgency(age_seconds=1.0, max_passive_seconds=60.0, touchable=False)
    assert isinstance(d, UrgencyDecision)
    assert d.mode == "aggressive"
    assert d.reason == "not touchable"


def test_aggressive_aged_past_passive() -> None:
    d = decide_urgency(age_seconds=60.0, max_passive_seconds=60.0, touchable=True)
    assert d.mode == "aggressive"
    assert d.reason == "aged past passive window"


def test_passive_within_window() -> None:
    d = decide_urgency(age_seconds=30.0)
    assert d.mode == "passive"
    assert d.reason == "within passive window"
