from __future__ import annotations

import numpy as np

from ibtrader.research.pbo import (
    _average_ranks,
    pbo_from_fold_sharpe_rows,
    probability_of_backtest_overfitting,
)


def test_average_ranks_ties() -> None:
    r = _average_ranks(np.array([1.0, 3.0, 3.0, 2.0]))
    assert r[0] == 1.0
    assert r[3] == 2.0
    assert r[1] == r[2] == 3.5


def test_pbo_high_when_is_best_always_worst_oos() -> None:
    # 2 trials × 2 periods, perfectly anti-correlated:
    # whichever period is IS, its winner is strictly worst on the OOS period → PBO=1.
    mat = np.array(
        [
            [10.0, -1.0],
            [-1.0, 10.0],
        ]
    )
    out = probability_of_backtest_overfitting(mat)
    assert out["n_combos"] == 2
    assert out["pbo"] == 1.0
    assert out["high_overfit_risk"] is True


def test_pbo_low_when_one_trial_dominates() -> None:
    mat = np.array(
        [
            [5.0, 5.0, 5.0, 5.0],
            [0.0, 0.0, 0.0, 0.0],
            [-1.0, -1.0, -1.0, -1.0],
        ]
    )
    out = probability_of_backtest_overfitting(mat)
    assert out["pbo"] == 0.0
    assert out["high_overfit_risk"] is False


def test_pbo_from_fold_rows_pads() -> None:
    rows = [[0.1, 0.2, 0.3, 0.4], [0.0, 0.0, 0.0]]
    out = pbo_from_fold_sharpe_rows(rows)
    assert "pbo" in out
    assert out["n_trials"] == 2
