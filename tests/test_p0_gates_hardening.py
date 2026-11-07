"""P0 (audit 2026-11-07): DSR units and sample size, t-stat gate, N across runs."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from ibtrader.research.dsr import MIN_DSR_OBS, deflated_sharpe_ratio
from ibtrader.research.gates import MIN_T_STAT, evaluate_strict_gates
from ibtrader.research.trials_ledger import dataset_family, ledger_path, prior_trials, record_trials
from ibtrader.validation.walkforward import _daily_return_shape

BH = {"sharpe": 0.5, "max_dd": -0.30}


def _cand(**kw):
    base = {"sharpe": 1.2, "max_dd": -0.10, "trade_count": 20}
    base.update(kw)
    return base


def test_dsr_annual_sharpe_is_converted_with_periods_per_year() -> None:
    sr_annual = 1.0
    n = 1260
    per_period = deflated_sharpe_ratio(sr_annual / math.sqrt(252), n_obs=n, n_trials=1)
    annual = deflated_sharpe_ratio(sr_annual, n_obs=n, n_trials=1, periods_per_year=252)
    assert math.isclose(per_period["dsr"], annual["dsr"], rel_tol=1e-9)
    # The old bug: annual SR with daily T made the standard error ~√252 too small.
    mixed = deflated_sharpe_ratio(sr_annual, n_obs=n, n_trials=1)
    z_mixed = mixed["observed_sr"] / mixed["sr_std_error"]
    z_right = annual["observed_sr"] / annual["sr_std_error"]
    assert z_mixed > 10 * z_right  # ≈ √252 ≈ 15.9 times too confident


def test_dsr_reproduces_the_24_obs_false_positive_and_flags_it() -> None:
    # The smoke run of 2026-10-26: SR 1.03 (annual) on n_obs=24 gave DSR 0.99997.
    out = deflated_sharpe_ratio(1.03, n_obs=24, n_trials=1, periods_per_year=252)
    assert out["insufficient_obs"] is True
    assert out["high_conviction"] is False
    assert out["dsr"] < 0.95  # in matching units the evidence is weak anyway


def test_strict_gate_fails_dsr_below_min_obs_even_with_high_value() -> None:
    diag = {"dsr": {"dsr": 0.9999, "n_obs": 24}}
    res = evaluate_strict_gates(_cand(), BH, diagnostics=diag)
    assert res.passed is False
    assert any(r.startswith("dsr_insufficient_obs") for r in res.reasons)
    ok = evaluate_strict_gates(_cand(), BH, diagnostics={"dsr": {"dsr": 0.99, "n_obs": MIN_DSR_OBS}})
    assert ok.passed is True, ok.reasons


def test_strict_gate_t_stat() -> None:
    weak = evaluate_strict_gates(_cand(t_stat=1.4), BH)
    assert weak.passed is False and weak.checks["t_stat_ok"] is False
    strong = evaluate_strict_gates(_cand(t_stat=MIN_T_STAT + 0.1), BH)
    assert strong.passed is True, strong.reasons
    absent = evaluate_strict_gates(_cand(), BH)
    assert "t_stat" not in absent.checks


def test_walkforward_shape_reports_bars_and_t_stat() -> None:
    rng = np.random.default_rng(7)
    r = pd.Series(rng.normal(0.0005, 0.01, 500))
    out = _daily_return_shape(r)
    assert out["bars"] == 500
    assert math.isclose(out["t_stat"], out["sr_daily"] * math.sqrt(500))
    assert _daily_return_shape(pd.Series([0.0, 0.0, 0.0]))["t_stat"] is None


def test_trials_ledger_accumulates_per_family(tmp_path: Path) -> None:
    p = ledger_path(tmp_path)
    fam = dataset_family(["spy"], pd.Timestamp("2021-10-27"))
    other = dataset_family(["SPY", "TLT"], "2021-10-27")
    assert fam == "SPY|2021-10-27"
    assert prior_trials(p, fam) == 0
    record_trials(p, fam, 12, exp_id="a")
    record_trials(p, fam, 5, exp_id="b")
    record_trials(p, other, 40, exp_id="c")
    assert prior_trials(p, fam) == 17
    assert prior_trials(p, other) == 40
