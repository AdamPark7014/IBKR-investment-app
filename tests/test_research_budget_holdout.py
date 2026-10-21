"""Research discipline (playbook phase 1): trial budget + frozen hold-out. No network.

Covers ``compute_trial_budget`` (Bailey et al. 2014), the strict-gate reasons
``trial_budget_exceeded`` / ``holdout_overused``, ``apply_holdout`` (trim vs
confirmation + JSONL log), the suite wiring (every track sees trimmed data, the
DSR gets the real ``n_trials``), the registry round-trip with the new fields,
and ``research-run --confirmation`` end to end through ``CliRunner``.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.config import AppSettings
from ibtrader.research import suite as suite_mod
from ibtrader.research.dsr_sma import run_sma_grid_dsr
from ibtrader.research.gates import compute_trial_budget, evaluate_candidate_gates, evaluate_strict_gates
from ibtrader.research.registry import ExperimentRecord, load_experiments, save_experiment
from ibtrader.research.runner import build_experiment_records
from ibtrader.research.suite import (
    apply_holdout,
    count_holdout_openings,
    holdout_openings_path,
    run_research_suite,
)

# --------------------------------------------------------------------------- helpers


def _mk(len_days: int = 180) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0, index=idx).astype(float)
    wiggle = (pd.Series(range(len(idx)), index=idx) % 40).astype(float)
    wiggle = (wiggle - 20.0) * 0.5
    px = base + wiggle
    return pd.DataFrame({"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0}, index=idx)


def _settings(tmp_path: Path, **research: Any) -> AppSettings:
    s = AppSettings(_env_file=None)
    s.data.reports_dir = str(tmp_path / "reports")
    for k, v in research.items():
        setattr(s.research, k, v)
    return s


def _stats(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {"sharpe": 0.8, "max_dd": -0.10, "trade_count": 12}
    base.update(overrides)
    return base


_BH = {"sharpe": 0.2, "max_dd": -0.20}


def _row(candidate_id: str = "sma_10_30", sharpe: float = 0.8) -> Dict[str, Any]:
    """Runner-shaped row carrying the loose verdict (strict re-gates it)."""
    oos = _stats(sharpe=sharpe, bars=120)
    loose = evaluate_candidate_gates(oos, bh_stats=_BH, restricted_bar_frac=0.0)
    return {
        "candidate_id": candidate_id,
        "params": {"fast": 10, "slow": 30},
        "oos": oos,
        "buy_hold_oos": dict(_BH),
        "gate_passed": loose.passed,
        "gate_reasons": list(loose.reasons),
        "gate_checks": dict(loose.checks),
    }


class _Capture:
    """Fake SMA runner + DSR so suite-level tests are instant and observable."""

    def __init__(self) -> None:
        self.data_seen: List[Dict[str, pd.DataFrame]] = []
        self.dsr_n_trials: List[int] = []

    def run_sma(self, settings: AppSettings, data: Any, symbol: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self.data_seen.append(dict(data))
        return [_row("sma_10_30")]

    def run_dsr(self, settings: AppSettings, data: Any, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        self.data_seen.append(dict(data))
        n = int(kwargs.get("n_trials") or 0)
        self.dsr_n_trials.append(n)
        return {
            "dsr": 0.99,
            "observed_sr": 0.8,
            "sr0_benchmark": 0.1,
            "n_trials": n,
            "n_obs": 120,
            "high_conviction": True,
            "selected_candidate_id": "sma_10_30",
            "trial_sharpes": [0.8],
        }


def _patch_suite(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    cap = _Capture()
    monkeypatch.setattr(suite_mod, "run_sma_research", cap.run_sma)
    monkeypatch.setattr(suite_mod, "run_sma_grid_dsr", cap.run_dsr)
    return cap


def _holdout_date(df: pd.DataFrame, bars_hidden: int = 30) -> str:
    return str(pd.Timestamp(df.index[-bars_hidden]).date())


# --------------------------------------------------------------------------- trial budget


def test_trial_budget_single_trial_needs_nothing() -> None:
    b = compute_trial_budget(1, years_available=0.0, target_sharpe=1.0)
    assert b["years_needed"] == 0.0
    assert b["budget_ok"] is True
    assert b["n_trials"] == 1


def test_trial_budget_ten_trials_is_two_ln_ten() -> None:
    b = compute_trial_budget(10, years_available=5.0, target_sharpe=1.0)
    assert math.isclose(b["years_needed"], 2.0 * math.log(10.0))  # ≈ 4.61 years
    assert b["budget_ok"] is True
    short = compute_trial_budget(10, years_available=2.0, target_sharpe=1.0)
    assert short["budget_ok"] is False


def test_trial_budget_hundred_trials_needs_nine_years() -> None:
    b = compute_trial_budget(100, years_available=5.0, target_sharpe=1.0)
    assert math.isclose(b["years_needed"], 2.0 * math.log(100.0))  # ≈ 9.21 years
    assert b["budget_ok"] is False
    assert compute_trial_budget(100, years_available=10.0, target_sharpe=1.0)["budget_ok"] is True


def test_trial_budget_scales_with_target_sharpe() -> None:
    # SR 0.5 quadruples the years needed: 2·ln(10)/0.25 ≈ 18.4
    b = compute_trial_budget(10, years_available=5.0, target_sharpe=0.5)
    assert math.isclose(b["years_needed"], 2.0 * math.log(10.0) / 0.25)
    assert b["budget_ok"] is False
    undefined = compute_trial_budget(10, years_available=50.0, target_sharpe=0.0)
    assert math.isinf(undefined["years_needed"]) and undefined["budget_ok"] is False


# --------------------------------------------------------------------------- strict gates


def test_strict_gate_fails_when_budget_exceeded() -> None:
    budget = compute_trial_budget(100, years_available=1.0)
    res = evaluate_strict_gates(_stats(), bh_stats=_BH, budget=budget)
    assert res.passed is False
    assert any(r.startswith("trial_budget_exceeded") for r in res.reasons), res.reasons
    assert res.checks["budget_ok"] is False
    assert res.checks["n_trials"] == 100
    assert res.checks["budget_enforced"] is True
    assert math.isclose(res.checks["years_needed"], 2.0 * math.log(100.0))
    assert res.checks["years_available"] == 1.0


def test_strict_gate_passes_when_within_budget() -> None:
    budget = compute_trial_budget(10, years_available=5.0)
    res = evaluate_strict_gates(_stats(), bh_stats=_BH, budget=budget)
    assert res.passed is True, res.reasons
    assert res.checks["budget_ok"] is True
    assert not any("trial_budget" in r for r in res.reasons)


def test_strict_gate_budget_not_enforced_keeps_verdict_but_flags() -> None:
    budget = dict(compute_trial_budget(100, years_available=1.0))
    budget["fail_on_budget_exceeded"] = False
    res = evaluate_strict_gates(_stats(), bh_stats=_BH, budget=budget)
    assert res.passed is True, res.reasons
    assert res.checks["budget_ok"] is False
    assert res.checks["budget_enforced"] is False
    assert "trial_budget_exceeded" in res.checks["budget_warning"]


def test_strict_gate_fails_when_holdout_overused() -> None:
    holdout = {
        "holdout_start": "2025-01-01",
        "holdout_applied": False,
        "holdout_opened": True,
        "holdout_overused": True,
        "holdout_opening_no": 2,
    }
    res = evaluate_strict_gates(_stats(), bh_stats=_BH, holdout=holdout)
    assert res.passed is False
    assert "holdout_overused" in res.reasons
    assert res.checks["holdout_opened"] is True
    assert res.checks["holdout_overused"] is True
    assert res.checks["holdout_opening_no"] == 2
    assert res.checks["holdout_start"] == "2025-01-01"
    once = {**holdout, "holdout_overused": False, "holdout_opening_no": 1}
    ok = evaluate_strict_gates(_stats(), bh_stats=_BH, holdout=once)
    assert ok.passed is True, ok.reasons
    assert ok.checks["holdout_applied"] is False


# --------------------------------------------------------------------------- apply_holdout


def test_apply_holdout_trims_every_frame_before_holdout_start(tmp_path: Path) -> None:
    data = {"SPY": _mk(180), "QQQ": _mk(180)}
    cut = _holdout_date(data["SPY"], bars_hidden=30)
    s = _settings(tmp_path, holdout_start=cut)
    trimmed, info = apply_holdout(s, data, "SPY", exp_id="t")
    for sym, df in trimmed.items():
        assert len(df) == 150, sym
        assert df.index.max() < pd.Timestamp(cut), sym
        assert not (df.index >= pd.Timestamp(cut)).any(), sym
    assert info["holdout_applied"] is True
    assert info["holdout_opened"] is False
    assert info["holdout_overused"] is False
    assert info["n_bars_hidden"] == 30
    assert info["n_bars_used"] == 150
    assert info["holdout_start"] == cut
    # Nothing is logged when the hold-out stays closed.
    assert not holdout_openings_path(s.data.reports_dir).exists()
    # No hold-out declared → untouched.
    untouched, info0 = apply_holdout(_settings(tmp_path), data, "SPY")
    assert len(untouched["SPY"]) == 180 and info0["holdout_applied"] is False and info0["holdout_opened"] is False


def test_apply_holdout_outside_data_range_is_a_clear_error(tmp_path: Path) -> None:
    data = {"SPY": _mk(120)}
    before = str((pd.Timestamp(data["SPY"].index[0]) - pd.Timedelta(days=30)).date())
    after = str((pd.Timestamp(data["SPY"].index[-1]) + pd.Timedelta(days=30)).date())
    for bad in (before, after):
        with pytest.raises(ValueError, match="holdout_start"):
            apply_holdout(_settings(tmp_path, holdout_start=bad), data, "SPY")
    with pytest.raises(ValueError, match="holdout_start"):
        apply_holdout(_settings(tmp_path, holdout_start=str(data["SPY"].index[0].date())), data, "SPY")


# --------------------------------------------------------------------------- suite wiring


def test_suite_hides_holdout_bars_from_every_track_and_dsr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cap = _patch_suite(monkeypatch)
    data = {"SPY": _mk(180)}
    cut = _holdout_date(data["SPY"], bars_hidden=40)
    s = _settings(tmp_path, holdout_start=cut)
    out = run_research_suite(s, data, "SPY", profile="smoke", exp_id="trim", reports_dir=s.data.reports_dir)
    assert cap.data_seen, "tracks did not run"
    for seen in cap.data_seen:  # SMA runner + DSR both got the trimmed frame
        assert seen["SPY"].index.max() < pd.Timestamp(cut)
        assert len(seen["SPY"]) == 140
    assert out["holdout_applied"] is True and out["holdout_opened"] is False and out["holdout_overused"] is False
    assert out["holdout_start"] == cut
    assert out["n_bars_hidden"] == 40 and out["n_bars_used"] == 140
    assert pd.Timestamp(out["data_end"]) < pd.Timestamp(cut)
    assert out["n_trials"] == 1 and out["years_needed"] == 0.0 and out["budget_ok"] is True
    assert 0.0 < out["years_available"] < 1.0
    for row in out["candidates"]:
        assert row["holdout_overused"] is False
        assert row["gate_checks"]["holdout_applied"] is True
        assert row["gate_checks"]["budget_ok"] is True
        assert row["gate_checks"]["n_trials"] == 1
        assert "holdout_overused" not in row["gate_reasons"]


def test_suite_passes_real_n_trials_to_dsr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cap = _patch_suite(monkeypatch)
    out = run_research_suite(_settings(tmp_path), {"SPY": _mk(180)}, "SPY", profile="smoke")
    assert cap.dsr_n_trials == [out["n_trials"]] == [out["n_candidates"]]
    assert out["dsr"]["n_trials"] == out["n_trials"]


def test_run_sma_grid_dsr_uses_run_level_n_trials() -> None:
    rows = [_row("sma_5_20", 0.9), _row("sma_10_30", 0.4), _row("sma_20_50", -0.2)]
    grid_only = run_sma_grid_dsr(AppSettings(_env_file=None), {}, "SPY", precomputed=rows)
    run_level = run_sma_grid_dsr(AppSettings(_env_file=None), {}, "SPY", precomputed=rows, n_trials=60)
    assert grid_only["n_trials"] == 3 and grid_only["n_grid_trials"] == 3
    assert run_level["n_trials"] == 60 and run_level["n_grid_trials"] == 3
    # More trials → higher chance-adjusted benchmark → lower DSR for the same winner.
    assert run_level["sr0_benchmark"] > grid_only["sr0_benchmark"]
    assert run_level["dsr"] < grid_only["dsr"]
    # A run-level N smaller than the grid never understates the deflation.
    assert run_sma_grid_dsr(AppSettings(_env_file=None), {}, "SPY", precomputed=rows, n_trials=1)["n_trials"] == 3


def test_suite_confirmation_opens_holdout_and_logs_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cap = _patch_suite(monkeypatch)
    data = {"SPY": _mk(180)}
    cut = _holdout_date(data["SPY"], bars_hidden=30)
    s = _settings(tmp_path, holdout_start=cut, confirmation_mode=True)
    out = run_research_suite(s, data, "SPY", profile="smoke", exp_id="confirm-1", reports_dir=s.data.reports_dir)
    for seen in cap.data_seen:  # nothing hidden this time
        assert len(seen["SPY"]) == 180
    assert out["holdout_opened"] is True and out["holdout_applied"] is False and out["holdout_overused"] is False
    assert out["holdout_opening_no"] == 1
    log = holdout_openings_path(s.data.reports_dir)
    assert Path(out["holdout_openings_log"]) == log and log.exists()
    lines = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["exp_id"] == "confirm-1"
    assert entry["holdout_start"] == cut
    assert entry["opening_no"] == 1
    assert entry["git_commit"]
    assert pd.Timestamp(entry["opened_at_utc"]).tzinfo is not None
    assert count_holdout_openings(log, cut) == 1
    for row in out["candidates"]:
        assert row["gate_checks"]["holdout_opened"] is True
        assert row["gate_passed"] is True, row["gate_reasons"]


def test_suite_second_opening_is_overused_and_fails_every_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_suite(monkeypatch)
    data = {"SPY": _mk(180)}
    cut = _holdout_date(data["SPY"], bars_hidden=30)
    s = _settings(tmp_path, holdout_start=cut, confirmation_mode=True, max_holdout_openings=1)
    first = run_research_suite(s, data, "SPY", profile="smoke", exp_id="c1", reports_dir=s.data.reports_dir)
    assert first["holdout_overused"] is False and first["n_pass"] == 1
    second = run_research_suite(s, data, "SPY", profile="smoke", exp_id="c2", reports_dir=s.data.reports_dir)
    assert second["holdout_opened"] is True
    assert second["holdout_opening_no"] == 2
    assert second["holdout_overused"] is True
    assert second["n_pass"] == 0
    for row in second["candidates"]:
        assert row["holdout_overused"] is True
        assert row["gate_passed"] is False
        assert "holdout_overused" in row["gate_reasons"]
        assert row["gate_checks"]["holdout_overused"] is True
    log = holdout_openings_path(s.data.reports_dir)
    assert count_holdout_openings(log, cut) == 2
    # The registry keeps the abuse flag on every row of the second run.
    recs = build_experiment_records(
        second["candidates"], exp_id="c2", git_commit="abc", dataset_hash="d" * 8, config_hash="c" * 8,
        suite_summary=second,
    )
    assert all(r.holdout_opened and r.extra.get("holdout_overused") is True for r in recs)
    assert all(r.extra.get("holdout_opening_no") == 2 for r in recs)


# --------------------------------------------------------------------------- registry


def test_registry_roundtrip_with_discipline_fields(tmp_path: Path) -> None:
    rec = ExperimentRecord(
        exp_id="e1",
        created_at_utc="2026-10-21T00:00:00+00:00",
        git_commit="abc",
        candidate_id="sma_10_30",
        params={"fast": 10, "slow": 30},
        oos={"sharpe": 0.5},
        buy_hold_oos={"sharpe": 0.2},
        gate_passed=False,
        gate_reasons=["trial_budget_exceeded: n_trials=40 needs 7.38y, have 1.00y"],
        dataset_hash="d" * 64,
        config_hash="c" * 64,
        n_trials=40,
        years_available=1.0,
        years_needed=2.0 * math.log(40.0),
        budget_ok=False,
        holdout_start="2025-01-01",
        holdout_applied=True,
        holdout_opened=False,
    )
    path = tmp_path / "experiments.jsonl"
    save_experiment(path, rec)
    rows = load_experiments(path)
    assert len(rows) == 1
    back = rows[0]
    assert back.n_trials == 40
    assert back.years_available == 1.0
    assert math.isclose(back.years_needed, 2.0 * math.log(40.0))
    assert back.budget_ok is False
    assert back.holdout_start == "2025-01-01"
    assert back.holdout_applied is True and back.holdout_opened is False
    raw = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert {"n_trials", "years_available", "years_needed", "budget_ok", "holdout_start"} <= set(raw)


def test_registry_reads_legacy_rows_without_discipline_fields(tmp_path: Path) -> None:
    path = tmp_path / "experiments.jsonl"
    path.write_text(
        '{"exp_id":"old","created_at_utc":"t","git_commit":"c","candidate_id":"x",'
        '"params":{},"oos":{},"buy_hold_oos":null,"gate_passed":false,"gate_reasons":[],'
        '"dataset_hash":"d","config_hash":"c"}\n',
        encoding="utf-8",
    )
    rows = load_experiments(path)
    assert len(rows) == 1
    old = rows[0]
    assert old.n_trials == 0
    assert old.years_available == 0.0 and old.years_needed == 0.0
    assert old.budget_ok is None  # never evaluated, not "failed"
    assert old.holdout_start is None
    assert old.holdout_applied is False and old.holdout_opened is False
    assert old.extra == {}


def test_build_experiment_records_fills_fields_from_suite_summary() -> None:
    summary = {
        "n_trials": 12,
        "years_available": 3.5,
        "years_needed": 2.0 * math.log(12.0),
        "budget_ok": False,
        "holdout_start": "2025-06-01",
        "holdout_applied": True,
        "holdout_opened": False,
    }
    recs = build_experiment_records(
        [_row("a"), _row("b")], exp_id="e", git_commit="g", dataset_hash="d" * 8, config_hash="c" * 8,
        suite_summary=summary,
    )
    assert len(recs) == 2
    for r in recs:
        assert r.n_trials == 12 and r.years_available == 3.5
        assert math.isclose(r.years_needed, 2.0 * math.log(12.0))
        assert r.budget_ok is False
        assert r.holdout_start == "2025-06-01" and r.holdout_applied is True and r.holdout_opened is False
        assert r.extra == {}
    # Without a summary the legacy defaults apply.
    bare = build_experiment_records([_row("a")], exp_id="e", git_commit="g", dataset_hash="d" * 8, config_hash="c" * 8)
    assert bare[0].n_trials == 0 and bare[0].budget_ok is None and bare[0].holdout_start is None


# --------------------------------------------------------------------------- CLI (real smoke suite, no network)


def _out(res: Any) -> str:
    """stdout + stderr; click < 8.2 mixes stderr into stdout and raises on ``res.stderr``."""
    try:
        err = res.stderr
    except ValueError:
        err = ""
    return res.stdout + (err or "")


def _payload(res: Any) -> Dict[str, Any]:
    assert res.exit_code == 0, _out(res) + str(res.exception)
    m = re.search(r"\{(.|\n)*\}$", res.stdout)
    assert m, res.stdout
    return json.loads(m.group(0))


def _cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, frames: Dict[str, pd.DataFrame]) -> None:
    from ibtrader.research import multi_asset as multi_asset_mod

    monkeypatch.setattr(multi_asset_mod, "DEFAULT_RESEARCH_SYMBOLS", ["SPY"])
    monkeypatch.setattr(cli_mod, "load_universe_v2", lambda settings: {k: v.copy() for k, v in frames.items()})
    monkeypatch.setenv("RISK__MAX_POSITION_PCT", "100.0")
    monkeypatch.setenv("RISK__MAX_TOTAL_EXPOSURE_PCT", "100.0")
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("RESEARCH__HOLDOUT_START", raising=False)
    monkeypatch.delenv("RESEARCH__CONFIRMATION_MODE", raising=False)


def test_research_run_confirmation_cli_opens_holdout_and_reports_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames = {"SPY": _mk(180)}
    cut = _holdout_date(frames["SPY"], bars_hidden=30)
    _cli_env(monkeypatch, tmp_path, frames)
    monkeypatch.setenv("RESEARCH__HOLDOUT_START", cut)

    res = CliRunner().invoke(
        cli_mod.app,
        ["research-run", "--exp-id", "confirm_smoke", "--profile", "smoke", "--confirmation"],
    )
    payload = _payload(res)
    combined = _out(res)
    assert "HOLD-OUT OPENING" in combined
    assert "opening no. 1 of 1" in combined

    assert payload["holdout_start"] == cut
    assert payload["holdout_opened"] is True
    assert payload["holdout_applied"] is False
    assert payload["holdout_overused"] is False
    assert payload["n_trials"] == payload["n_candidates"] == 1
    assert payload["budget_ok"] is True and payload["years_needed"] == 0.0
    assert payload["budget"]["n_trials"] == 1
    assert payload["holdout"]["holdout_opening_no"] == 1
    assert payload["holdout"]["n_bars_hidden"] == 30
    assert payload["dsr"]["n_trials"] == 1
    for c in payload["candidates"]:
        checks = c["gate_detail"]["checks"]
        assert checks["holdout_opened"] is True and checks["budget_ok"] is True

    log = holdout_openings_path(tmp_path / "reports")
    assert log.exists()
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["exp_id"] == "confirm_smoke" and entry["opening_no"] == 1 and entry["holdout_start"] == cut

    rows = load_experiments(payload["registry"])
    assert len(rows) == 1
    assert rows[0].holdout_opened is True and rows[0].holdout_applied is False
    assert rows[0].holdout_start == cut and rows[0].n_trials == 1 and rows[0].budget_ok is True

    with open(payload["artifact"], encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["holdout_opened"] is True and "budget" in on_disk and "holdout" in on_disk


def test_research_run_confirmation_requires_declared_holdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _cli_env(monkeypatch, tmp_path, {"SPY": _mk(180)})
    res = CliRunner().invoke(cli_mod.app, ["research-run", "--profile", "smoke", "--confirmation"])
    assert res.exit_code != 0
    assert "RESEARCH__HOLDOUT_START" in _out(res)
    assert not holdout_openings_path(tmp_path / "reports").exists()


def test_research_run_env_confirmation_without_flag_keeps_holdout_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames = {"SPY": _mk(180)}
    cut = _holdout_date(frames["SPY"], bars_hidden=30)
    _cli_env(monkeypatch, tmp_path, frames)
    monkeypatch.setenv("RESEARCH__HOLDOUT_START", cut)
    monkeypatch.setenv("RESEARCH__CONFIRMATION_MODE", "true")

    payload = _payload(
        CliRunner().invoke(cli_mod.app, ["research-run", "--exp-id", "env_only", "--profile", "smoke"])
    )
    assert payload["holdout_applied"] is True
    assert payload["holdout_opened"] is False
    assert payload["holdout"]["n_bars_used"] == 150 and payload["holdout"]["n_bars_hidden"] == 30
    assert pd.Timestamp(payload["holdout"]["holdout_start"]) == pd.Timestamp(cut)
    assert not holdout_openings_path(tmp_path / "reports").exists()
    rows = load_experiments(payload["registry"])
    assert rows and all(r.holdout_applied and not r.holdout_opened for r in rows)
