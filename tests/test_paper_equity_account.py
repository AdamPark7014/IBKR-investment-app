"""Paper equity is money (cash + shares × price), never Σ weight × price. Zero broker orders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

import pandas as pd
import pytest

import ibtrader.ops.autopilot as ap
from ibtrader.config import AppSettings
from ibtrader.engine.decision import Decision
from ibtrader.ops.config_freeze import write_freeze
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


def _settings(tmp_path: Path) -> AppSettings:
    s = AppSettings()
    s.data.data_dir = str(tmp_path / "data")
    s.data.reports_dir = str(tmp_path / "reports")
    s.risk.killswitch_file = str(tmp_path / "KILL_SWITCH")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    return s


def _patch_market(monkeypatch: Any, closes: List[float], days: List[str]) -> List[int]:
    """Each autopilot run sees the next (close, day); returns a call counter."""
    calls = [0]

    def _data(_s: Any) -> dict:
        i = calls[0]
        calls[0] += 1
        idx = pd.DatetimeIndex([days[i]])
        return {"SPY": pd.DataFrame({"close": [closes[i]]}, index=idx)}

    monkeypatch.setattr(ap, "load_universe_v2", _data)
    monkeypatch.setattr(
        ap.DecisionEngine,
        "generate",
        lambda self, _d: [
            Decision(symbol="SPY", action="BUY", score=1.0, confidence=1.0, position_size=1.0, reason="t", regime={})
        ],
    )
    monkeypatch.setattr(ap, "build_market_radar", lambda d: {"as_of": str(next(iter(d.values())).index[-1].date()),
                                                              "disclaimer": "Triage only."})
    return calls


def test_weight_cut_is_not_a_drawdown(tmp_path: Path, monkeypatch: Any) -> None:
    """The old autopilot valued paper_positions.json weights: 1.0 → 0.5 at the same price = fake 50 % DD."""
    s = _settings(tmp_path)
    write_freeze(tmp_path / "data" / "paper_config_freeze.json", s)
    data_dir = tmp_path / "data"
    _patch_market(monkeypatch, closes=[288.0, 288.0], days=["2026-10-22", "2026-10-23"])
    (data_dir / "paper_positions.json").write_text(json.dumps({"SPY": 1.0}), encoding="utf-8")
    out1 = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    (data_dir / "paper_positions.json").write_text(json.dumps({"SPY": 0.5}), encoding="utf-8")
    out2 = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    assert out1["orders_sent"] == 0 and out2["orders_sent"] == 0
    # No paper account → no equity at all, no kill alert.
    assert not (data_dir / "paper_equity.jsonl").exists()
    codes = {a["code"] for a in out2["alerts"]}
    assert "dd_vs_sharpe" not in codes and "paper_vs_oos_dd" not in codes
    assert "paper_kill_alerts_inactive" in codes


def test_autopilot_values_the_paper_account(tmp_path: Path, monkeypatch: Any) -> None:
    s = _settings(tmp_path)
    write_freeze(tmp_path / "data" / "paper_config_freeze.json", s)
    data_dir = tmp_path / "data"
    (data_dir / "paper_account.json").write_text(
        json.dumps({"cash": 10_000.0, "shares": {"SPY": 100}}), encoding="utf-8"
    )
    _patch_market(monkeypatch, closes=[500.0, 500.0, 450.0], days=["2026-10-22", "2026-10-22", "2026-10-23"])
    ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    ap.run_autopilot(settings=s, use_ai=False, open_ui=False)  # same market day: replaces, no duplicate
    out = ap.run_autopilot(settings=s, use_ai=False, open_ui=False)
    pts = load_equity_points(data_dir / "paper_equity.jsonl", bases=REAL_BASES)
    assert [p["equity"] for p in pts] == [60_000.0, 55_000.0]  # 10 000 + 100 × price
    eq = out["paper_equity"]
    assert eq["account_present"] is True and eq["n_real_points"] == 2
    assert eq["max_dd"] == pytest.approx(5_000.0 / 60_000.0)
    # Two points are not enough to recommend killing anything.
    assert eq["kill_alerts_active"] is False
    assert out["paper_vs_oos"]["kill_recommend"] is False
