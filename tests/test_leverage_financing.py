"""Interés de margen en el backtest y estudio de apalancamiento sobre configuraciones ya probadas."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.data.universe import UniverseEntry, UniverseSpec
from ibtrader.research.leverage_study import run_leverage_study


def _data(n: int = 700) -> dict:
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2021-01-04", periods=n)
    out = {}
    for s, v in {"SPY": 0.16, "IEF": 0.07, "GLD": 0.15}.items():
        c = 100 * np.exp(np.cumsum(rng.normal(0.0003, v / np.sqrt(252), n)))
        out[s] = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 5e6}, index=idx)
    return out


def test_leverage_pays_margin_and_unlevered_pays_nothing() -> None:
    s = AppSettings(_env_file=None)
    uni = UniverseSpec("t", [UniverseEntry("SPY", "equity", "eq"), UniverseEntry("IEF", "fixed_income", "bd"),
                             UniverseEntry("GLD", "commodity", "au")])
    cfg = (("static", ("long_const",), "box_risk_parity", None),)
    rep = run_leverage_study(_data(), s, uni, leverages=(1.0, 1.5), margin_rate_annual=0.06, configs=cfg)
    r1, r15 = rep["filas"]
    assert r1["interes_margen_anual_pct"] == 0.0
    assert r15["interes_margen_anual_pct"] > 0.5  # ~0.5 de NAV prestado al 6 % ≈ 3 % anual
    assert r15["vol"] > r1["vol"] * 1.3
    assert r1["desde"] == r15["desde"]
