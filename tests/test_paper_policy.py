from __future__ import annotations

import math

from ibtrader.engine.paper_policy import (
    apply_stop_veto,
    classify_paper_action,
    size_paper_positions,
)


def test_classify_vetoes_before_signal() -> None:
    action, _ = classify_paper_action(
        score=0.9,
        direction="long_only",
        killswitch=True,
        symbol_allowed=True,
        data_ok=True,
    )
    assert action == "NO_TRADE"
    action, _ = classify_paper_action(
        score=0.9,
        direction="long_only",
        killswitch=False,
        symbol_allowed=False,
        data_ok=True,
    )
    assert action == "NO_TRADE"
    action, _ = classify_paper_action(
        score=math.nan,
        direction="long_only",
        killswitch=False,
        symbol_allowed=True,
        data_ok=True,
    )
    assert action == "NO_TRADE"


def test_classify_respects_direction() -> None:
    buy, _ = classify_paper_action(
        score=0.4, direction="long_only", killswitch=False, symbol_allowed=True, data_ok=True
    )
    assert buy == "BUY"
    blocked, _ = classify_paper_action(
        score=0.4, direction="short_only", killswitch=False, symbol_allowed=True, data_ok=True
    )
    assert blocked == "NO_TRADE"
    watch, _ = classify_paper_action(
        score=-0.4, direction="long_only", killswitch=False, symbol_allowed=True, data_ok=True
    )
    assert watch == "WATCH"
    sell, _ = classify_paper_action(
        score=-0.4, direction="long_short", killswitch=False, symbol_allowed=True, data_ok=True
    )
    assert sell == "SELL"
    flat, _ = classify_paper_action(
        score=0.05, direction="long_short", killswitch=False, symbol_allowed=True, data_ok=True
    )
    assert flat == "WATCH"


def test_size_caps_gross_exposure() -> None:
    sizes = size_paper_positions(
        {"AAA": "BUY", "BBB": "BUY", "CCC": "WATCH"},
        {"AAA": 0.4, "BBB": 0.4, "CCC": 0.4},
        max_position_pct=50.0,
        max_total_exposure_pct=30.0,
    )
    assert sizes["CCC"] == 0.0
    assert abs(sizes["AAA"]) + abs(sizes["BBB"]) == 0.3
    assert sizes["AAA"] > 0 and sizes["BBB"] > 0


def test_stop_veto_blocks_stopped_entries() -> None:
    action, reason = apply_stop_veto("BUY", desired_sign=1, effective_sign=0)
    assert action == "NO_TRADE"
    assert reason is not None
    kept, none_reason = apply_stop_veto("BUY", desired_sign=1, effective_sign=1)
    assert kept == "BUY" and none_reason is None
