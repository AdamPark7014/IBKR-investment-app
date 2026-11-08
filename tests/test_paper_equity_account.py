"""Paper equity is money (cash + shares × price), never Σ weight × price. Zero broker orders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ibtrader.ops.paper_curve import (
    BASIS_CASH_SHARES,
    MIN_POINTS_FOR_KILL,
    REAL_BASES,
    account_equity,
    append_daily_equity_point,
    append_equity_point,
    load_equity_points,
    load_paper_account,
)
from ibtrader.ops.paper_vs_oos import compare_paper_vs_oos


def test_account_equity_is_cash_plus_shares_times_price() -> None:
    acct = {"cash": 40_000.0, "shares": {"SPY": 100.0, "IEF": 0.0}}
    eq, missing = account_equity(acct, {"SPY": 600.0})
    assert eq == pytest.approx(100_000.0) and missing == []
    eq2, missing2 = account_equity({"cash": 1.0, "shares": {"SPY": 1.0, "GLD": 2.0}}, {"SPY": 600.0})
    assert eq2 is None and missing2 == ["GLD"]  # a partial valuation would look like a loss


def test_load_paper_account_requires_cash(tmp_path: Path) -> None:
    p = tmp_path / "paper_account.json"
    assert load_paper_account(p) is None
    p.write_text(json.dumps({"SPY": 1.0}), encoding="utf-8")  # weights file shape: not an account
    assert load_paper_account(p) is None
    p.write_text(json.dumps({"cash": 1000, "shares": {"SPY": 2}}), encoding="utf-8")
    assert load_paper_account(p) == {"cash": 1000.0, "shares": {"SPY": 2.0}}


def test_daily_points_replace_same_day_and_filter_bases(tmp_path: Path) -> None:
    p = tmp_path / "paper_equity.jsonl"
    append_equity_point(p, 50.0, ts="2026-10-01")  # legacy, no basis
    assert append_daily_equity_point(p, 100.0, day="2026-10-02", basis=BASIS_CASH_SHARES)
    assert append_daily_equity_point(p, 101.0, day="2026-10-02", basis=BASIS_CASH_SHARES)  # re-run same day
    assert append_daily_equity_point(p, 99.0, day="2026-10-03", basis=BASIS_CASH_SHARES)
    pts = load_equity_points(p)
    assert [pt["equity"] for pt in pts] == [50.0, 101.0, 99.0]
    real = load_equity_points(p, bases=REAL_BASES)
    assert [pt["equity"] for pt in real] == [101.0, 99.0]


def test_kill_check_needs_enough_real_points() -> None:
    few = compare_paper_vs_oos(paper_max_dd=0.5, paper_n_points=3, min_points=MIN_POINTS_FOR_KILL)
    assert few["kill_recommend"] is False and few["kill_check_active"] is False
    many = compare_paper_vs_oos(paper_max_dd=0.5, paper_n_points=MIN_POINTS_FOR_KILL, min_points=MIN_POINTS_FOR_KILL)
    assert many["kill_recommend"] is True and many["kill_check_active"] is True
