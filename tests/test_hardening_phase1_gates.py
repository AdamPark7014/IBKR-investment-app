"""Hardening phase 1 — strict gates are the verdict, registry rows carry provenance.

No network: synthetic OHLCV frames + monkeypatched loader (same recipe as
``tests/test_research_cli.py``).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd
import pytest
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.research.gates import evaluate_candidate_gates, evaluate_strict_gates
from ibtrader.research.registry import load_experiments
from ibtrader.research.runner import build_experiment_records
from ibtrader.research.suite import _apply_strict_gates

# --------------------------------------------------------------------------- helpers


def _stats(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {"sharpe": 0.5, "max_dd": -0.10, "trade_count": 12}
    base.update(overrides)
    return base


def _row(
    candidate_id: str = "sma_10_30",
    sharpe: float = 0.5,
    bh_sharpe: float = 0.0,
    max_dd: float = -0.10,
    bh_max_dd: float = -0.20,
    assumed: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    """A runner-shaped row carrying the *loose* gate verdict for its stats."""
    oos = _stats(sharpe=sharpe, max_dd=max_dd)
    bh = {"sharpe": bh_sharpe, "max_dd": bh_max_dd}
    loose = evaluate_candidate_gates(oos, bh_stats=bh, restricted_bar_frac=0.0)
    checks = dict(loose.checks)
    if assumed:
        checks["restricted_bar_frac_assumed"] = True
        checks["restricted_bar_frac_note"] = "engine lockout bars not wired"
    row: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "params": {"fast": 10, "slow": 30},
        "oos": oos,
        "buy_hold_oos": bh,
        "gate_passed": loose.passed,
        "gate_reasons": list(loose.reasons),
        "gate_checks": checks,
    }
    row.update(extra)
    return row


# --------------------------------------------------------------------------- strict gates


def test_strict_fails_without_bh_sharpe():
    res = evaluate_strict_gates(_stats(), bh_stats={"max_dd": -0.20})
    assert res.passed is False
    assert "bh_sharpe_missing" in res.reasons
    assert res.checks["bh_sharpe"] is None
    assert res.checks["beats_bh_ok"] is False


def test_strict_fails_without_bh_at_all():
    res = evaluate_strict_gates(_stats(), bh_stats=None)
    assert res.passed is False
    assert "bh_sharpe_missing" in res.reasons


def test_strict_fails_when_bh_sharpe_is_nan():
    res = evaluate_strict_gates(_stats(), bh_stats={"max_dd": -0.20, "sharpe": float("nan")})
    assert res.passed is False
    assert "bh_sharpe_missing" in res.reasons


def test_beats_bh_branch_sharpe_strictly_higher():
    res = evaluate_strict_gates(_stats(sharpe=0.5), bh_stats={"max_dd": -0.05, "sharpe": 0.3})
    assert res.checks["bh_sharpe"] == 0.3
    assert res.checks["beats_bh"] is True
    assert res.checks["beats_bh_via_dd"] is False
    assert res.checks["beats_bh_ok"] is True
    assert res.passed is True, res.reasons


def test_beats_bh_branch_near_sharpe_with_shallower_dd():
    # 0.30 trails B&H 0.35 by 0.05 (≤ 0.10) and DD -0.10 vs -0.20 is 10pp shallower.
    res = evaluate_strict_gates(
        _stats(sharpe=0.30, max_dd=-0.10),
        bh_stats={"max_dd": -0.20, "sharpe": 0.35},
    )
    assert res.checks["beats_bh"] is False
    assert res.checks["beats_bh_via_dd"] is True
    assert res.checks["beats_bh_ok"] is True
    assert res.passed is True, res.reasons


def test_beats_bh_dd_margin_boundary_exactly_5pp_passes():
    res = evaluate_strict_gates(
        _stats(sharpe=0.30, max_dd=-0.15),
        bh_stats={"max_dd": -0.20, "sharpe": 0.35},
    )
    assert res.checks["beats_bh_ok"] is True
    assert res.passed is True, res.reasons


def test_beats_bh_fails_near_sharpe_without_dd_edge():
    # Within tolerance on Sharpe but DD only 2pp shallower → not a risk-adjusted win.
    res = evaluate_strict_gates(
        _stats(sharpe=0.30, max_dd=-0.18),
        bh_stats={"max_dd": -0.20, "sharpe": 0.35},
    )
    assert res.checks["beats_bh"] is False
    assert res.checks["beats_bh_via_dd"] is False
    assert res.checks["beats_bh_ok"] is False
    assert res.passed is False
    assert any(r.startswith("does_not_beat_bh") for r in res.reasons)


def test_beats_bh_fails_beyond_sharpe_tolerance_even_with_better_dd():
    # 0.30 trails B&H 0.45 by 0.15 (> 0.10): shallower DD does not rescue it.
    res = evaluate_strict_gates(
        _stats(sharpe=0.30, max_dd=-0.02),
        bh_stats={"max_dd": -0.30, "sharpe": 0.45},
    )
    assert res.checks["beats_bh_ok"] is False
    assert res.passed is False
    assert any(r.startswith("does_not_beat_bh") for r in res.reasons)


def test_beats_bh_enforced_without_diagnostics():
    # Sharpe clears 0.25, trades/DD/lock fine, but B&H Sharpe is higher → FAIL.
    res = evaluate_strict_gates(
        _stats(sharpe=0.40, max_dd=-0.19),
        bh_stats={"max_dd": -0.20, "sharpe": 0.60},
        diagnostics=None,
    )
    assert res.checks["oos_sharpe_ok"] is True
    assert res.checks["dd_ok"] is True
    assert res.passed is False
    assert any(r.startswith("does_not_beat_bh") for r in res.reasons)


# --------------------------------------------------------------------------- suite re-gating


def test_apply_strict_gates_fails_when_restricted_bar_frac_assumed():
    row = _row(sharpe=0.8, bh_sharpe=0.1, assumed=True)
    assert row["gate_passed"] is True  # loose verdict
    _apply_strict_gates([row], diagnostics=None)
    assert row["gate_passed"] is False
    assert "restricted_bar_frac_assumed" in row["gate_reasons"]
    assert row["gate_passed_loose"] is True
    assert row["gate_reasons_loose"] == []
    # Loose checks are kept and strict ones merged in.
    assert row["gate_checks"]["restricted_bar_frac_assumed"] is True
    assert row["gate_checks"]["beats_bh_ok"] is True
    assert row["gate_checks"]["gate_mode"] == "strict"


def test_apply_strict_gates_sharpe_0_1_passes_loose_fails_strict():
    row = _row(sharpe=0.1, bh_sharpe=0.0)
    assert row["gate_passed"] is True  # loose: Sharpe ≥ 0 is enough
    _apply_strict_gates([row], diagnostics=None)
    assert row["gate_passed_loose"] is True
    assert row["gate_passed"] is False
    assert any("0.25" in r for r in row["gate_reasons"])
    assert row["gate_checks"]["min_oos_sharpe"] == 0.25


def test_apply_strict_gates_keeps_a_genuine_winner():
    row = _row(sharpe=0.8, bh_sharpe=0.2)
    _apply_strict_gates([row], diagnostics=None)
    assert row["gate_passed"] is True, row["gate_reasons"]
    assert row["gate_passed_loose"] is True
    assert row["gate_checks"]["strict_diagnostics_applied"] is False


def test_apply_strict_gates_uses_diagnostics_only_for_sma_family():
    sma = _row("sma_10_30", sharpe=0.8, bh_sharpe=0.2)
    regime = _row("sma_regime_10_30", sharpe=0.8, bh_sharpe=0.2)
    tsmom = _row("tsmom_63", sharpe=0.8, bh_sharpe=0.2, params={"lookback": 63, "family": "tsmom"})
    diagnostics = {"pbo": {"high_overfit_risk": True, "pbo": 0.7}, "dsr": None, "cpcv": None}
    _apply_strict_gates([sma, regime, tsmom], diagnostics)
    for r in (sma, regime):
        assert r["gate_passed"] is False
        assert "pbo.high_overfit_risk" in r["gate_reasons"]
        assert r["gate_checks"]["strict_diagnostics_applied"] is True
    assert tsmom["gate_passed"] is True, tsmom["gate_reasons"]
    assert "pbo.high_overfit_risk" not in tsmom["gate_reasons"]
    assert tsmom["gate_checks"]["strict_diagnostics_applied"] is False


def test_apply_strict_gates_diagnostics_not_applied_to_other_symbol():
    spy = _row("sma_xasset_SPY_10_30", sharpe=0.8, bh_sharpe=0.2, symbol="SPY")
    qqq = _row("sma_xasset_QQQ_10_30", sharpe=0.8, bh_sharpe=0.2, symbol="QQQ")
    _apply_strict_gates([spy, qqq], {"cpcv": {"fragile_cpcv": True}}, symbol="SPY")
    assert spy["gate_passed"] is False
    assert "cpcv.fragile_cpcv" in spy["gate_reasons"]
    assert qqq["gate_passed"] is True, qqq["gate_reasons"]


# --------------------------------------------------------------------------- registry provenance


def test_build_experiment_records_requires_hashes():
    rows = [_row()]
    with pytest.raises(ValueError, match="dataset_hash"):
        build_experiment_records(rows, exp_id="e1", git_commit="abc")
    with pytest.raises(ValueError):
        build_experiment_records(rows, exp_id="e1", git_commit="abc", dataset_hash="d" * 8)
    with pytest.raises(ValueError):
        build_experiment_records(rows, exp_id="e1", git_commit="abc", config_hash="c" * 8)
    recs = build_experiment_records(
        rows, exp_id="e1", git_commit="abc", dataset_hash="d" * 8, config_hash="c" * 8
    )
    assert len(recs) == 1
    assert recs[0].dataset_hash == "d" * 8
    assert recs[0].config_hash == "c" * 8


def _mk(len_days: int = 180) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0, index=idx).astype(float)
    wiggle = (pd.Series(range(len(idx)), index=idx) % 40).astype(float)
    wiggle = (wiggle - 20.0) * 0.5
    px = base + wiggle
    return pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0},
        index=idx,
    )


def test_research_run_smoke_registry_rows_carry_hashes(monkeypatch, tmp_path):
    from ibtrader.research import multi_asset as multi_asset_mod

    monkeypatch.setattr(multi_asset_mod, "DEFAULT_RESEARCH_SYMBOLS", ["SPY"])

    def fake_loader(settings):
        return {sym: _mk(len_days=180) for sym in settings.universe.symbols}

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    monkeypatch.setenv("RISK__MAX_POSITION_PCT", "100.0")
    monkeypatch.setenv("RISK__MAX_TOTAL_EXPOSURE_PCT", "100.0")
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path / "reports"))

    res = CliRunner().invoke(
        cli_mod.app,
        ["research-run", "--exp-id", "hardening_p1_smoke", "--profile", "smoke"],
    )
    assert res.exit_code == 0, res.stdout + (res.stderr or "") + str(res.exception)
    m = re.search(r"\{(.|\n)*\}$", res.stdout)
    assert m, res.stdout
    payload = json.loads(m.group(0))

    assert payload["gate_mode"] == "strict"
    assert "n_pass_loose" in payload
    assert payload["n_pass"] <= payload["n_pass_loose"]
    for c in payload["candidates"]:
        assert "gate_passed_loose" in c
        assert c["gate_detail"]["checks"].get("gate_mode") == "strict"
        assert "beats_bh_ok" in c["gate_detail"]["checks"]

    rows = load_experiments(payload["registry"])
    assert len(rows) == payload["n_candidates"] == 1
    for r in rows:
        assert r.exp_id == "hardening_p1_smoke"
        assert re.fullmatch(r"[0-9a-f]{64}", r.dataset_hash), r.dataset_hash
        assert re.fullmatch(r"[0-9a-f]{64}", r.config_hash), r.config_hash
