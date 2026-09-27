"""Unit tests for V3 OOS research gates (no network)."""

from __future__ import annotations

import math

from ibtrader.research.gates import OOSGateResult, evaluate_candidate_gates


def _pass_stats(**overrides):
    base = {
        "sharpe": 0.5,
        "max_dd": -0.10,
        "trade_count": 12,
    }
    base.update(overrides)
    return base


def test_gates_pass_when_all_conditions_met():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(),
        bh_stats={"max_dd": -0.12, "sharpe": 0.3},
        restricted_bar_frac=0.0,
    )
    assert isinstance(res, OOSGateResult)
    assert res.passed is True
    assert res.reasons == []
    assert res.checks["oos_sharpe_ok"] is True
    assert res.checks["trade_count_ok"] is True
    assert res.checks["dd_ok"] is True
    assert res.checks["lock_ok"] is True


def test_gates_reject_negative_oos_sharpe():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(sharpe=-0.1),
        bh_stats={"max_dd": -0.20},
        restricted_bar_frac=0.0,
    )
    assert res.passed is False
    assert res.checks["oos_sharpe_ok"] is False
    assert any("oos_sharpe" in r for r in res.reasons)


def test_gates_reject_nan_sharpe():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(sharpe=float("nan")),
        bh_stats={"max_dd": -0.20},
    )
    assert res.passed is False
    assert res.checks["oos_sharpe_ok"] is False


def test_gates_reject_insufficient_trades():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(trade_count=4),
        bh_stats={"max_dd": -0.20},
    )
    assert res.passed is False
    assert res.checks["trade_count_ok"] is False
    assert any("trade_count" in r for r in res.reasons)


def test_gates_trade_count_boundary_five_passes():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(trade_count=5),
        bh_stats={"max_dd": -0.20},
    )
    assert res.checks["trade_count_ok"] is True
    assert res.passed is True


def test_gates_reject_dd_worse_than_bh_by_more_than_5pp():
    # B&H -10%, candidate -16% → 6pp worse → reject
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(max_dd=-0.16),
        bh_stats={"max_dd": -0.10},
    )
    assert res.passed is False
    assert res.checks["dd_ok"] is False
    assert any("max_dd" in r for r in res.reasons)


def test_gates_dd_within_5pp_passes():
    # B&H -10%, candidate -14% → 4pp worse → ok
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(max_dd=-0.14),
        bh_stats={"max_dd": -0.10},
    )
    assert res.checks["dd_ok"] is True
    assert res.passed is True


def test_gates_accepts_max_drawdown_alias():
    res = evaluate_candidate_gates(
        stitched_oos_stats={
            "sharpe": 0.2,
            "max_drawdown": -0.08,
            "trade_count": 8,
        },
        bh_stats={"max_drawdown": -0.10},
    )
    assert res.passed is True
    assert math.isclose(res.checks["candidate_max_dd"], -0.08)


def test_gates_reject_restricted_bar_frac_above_half():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(),
        bh_stats={"max_dd": -0.20},
        restricted_bar_frac=0.51,
    )
    assert res.passed is False
    assert res.checks["lock_ok"] is False
    assert any("restricted_bar_frac" in r for r in res.reasons)


def test_gates_restricted_bar_frac_half_passes():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(),
        bh_stats={"max_dd": -0.20},
        restricted_bar_frac=0.5,
    )
    assert res.checks["lock_ok"] is True
    assert res.passed is True


def test_gates_missing_bh_skips_dd_check():
    res = evaluate_candidate_gates(
        stitched_oos_stats=_pass_stats(max_dd=-0.50),
        bh_stats=None,
    )
    assert res.checks["dd_ok"] is True
    assert res.passed is True
