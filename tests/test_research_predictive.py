"""IC por regla: cero en un paseo aleatorio, positivo cuando hay tendencia persistente."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.research.predictive import information_coefficients, per_symbol_ic


def _walks(drift_persistence: float, seed: int, n: int = 3000, k: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=n)
    cols = {}
    for j in range(k):
        mu = np.zeros(n)
        shock = rng.normal(0, 0.0004, n)
        for i in range(1, n):
            mu[i] = drift_persistence * mu[i - 1] + shock[i]
        cols[f"S{j}"] = 100 * np.exp(np.cumsum(mu + rng.normal(0, 0.01, n)))
    return pd.DataFrame(cols, index=idx)


def test_random_walk_has_no_information() -> None:
    rep = information_coefficients(_walks(0.0, 1), rules=("ewmac16_64",), horizons=(21,))
    row = rep["filas"][0]
    assert abs(row["ic"]) < 0.05 and abs(row["t"]) < 3.0


def test_persistent_drift_is_detected() -> None:
    px = _walks(0.995, 2)
    row = information_coefficients(px, rules=("ewmac16_64",), horizons=(21,))["filas"][0]
    assert row["ic"] > 0.05
    assert len(per_symbol_ic(px, "ewmac16_64")) == px.shape[1]
