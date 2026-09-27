from __future__ import annotations

import math

import numpy as np

from ibtrader.research.cpcv import cpcv_sharpe_distribution
from ibtrader.research.dsr import (
    _norm_cdf,
    _norm_ppf,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    sharpe_std_error,
)


def test_norm_ppf_cdf_roundtrip() -> None:
    for p in (0.05, 0.5, 0.95):
        x = _norm_ppf(p)
        assert abs(_norm_cdf(x) - p) < 1e-3


def test_expected_max_sharpe_rises_with_trials() -> None:
    s2 = expected_max_sharpe(2, 0.25)
    s20 = expected_max_sharpe(20, 0.25)
    assert s20 > s2 > 0


def test_dsr_high_when_one_clear_winner() -> None:
    # Selected SR far above chance-adjusted max given tiny trial variance
    out = deflated_sharpe_ratio(
        2.0,
        n_obs=500,
        n_trials=3,
        trial_sharpes=[2.0, -0.5, -0.4],
        skew=0.0,
        kurtosis=3.0,
    )
    assert out["dsr"] > 0.9
    assert out["high_conviction"] is True


def test_dsr_low_when_barely_best_of_many() -> None:
    # Wide trial cloud; selected SR near the chance-adjusted max → DSR ~ 0.5
    trials = list(np.linspace(-1.0, 0.3, 50))
    out = deflated_sharpe_ratio(
        0.3,
        n_obs=60,
        n_trials=len(trials),
        trial_sharpes=trials,
        skew=0.0,
        kurtosis=3.0,
    )
    assert out["dsr"] < 0.5
    assert math.isfinite(out["sr0_benchmark"])
    assert out["high_conviction"] is False


def test_sharpe_std_error_positive() -> None:
    assert sharpe_std_error(1.0, 252) > 0


def test_cpcv_distribution_on_synthetic_folds() -> None:
    rng = np.random.default_rng(0)
    folds = [rng.normal(0.001, 0.01, size=40).tolist() for _ in range(6)]
    out = cpcv_sharpe_distribution(folds, n_test_folds=3)
    assert out["n_combos"] > 0
    assert math.isfinite(out["median_sharpe"])
    assert 0.0 <= out["frac_positive"] <= 1.0
