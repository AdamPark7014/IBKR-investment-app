"""Ventanas de estrés y spreads por universo del estudio retador."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ibtrader.config import AppSettings
from ibtrader.data.universe import load_universe_spec
from ibtrader.research.challenger import settings_with_universe_spreads, stress_report


def test_stress_report_omite_ventanas_incompletas_y_mide_la_caida() -> None:
    idx = pd.bdate_range("2019-01-01", "2021-12-31")
    r = pd.Series(0.0, index=idx)
    r.loc["2020-03-09"] = -0.10
    r.loc["2020-03-12"] = -0.10
    rep = stress_report(r)
    assert set(rep) == {"covid_2020"}
    assert np.isclose(rep["covid_2020"]["retorno_total"], 0.9 * 0.9 - 1.0)
    assert np.isclose(rep["covid_2020"]["caida_max"], 0.9 * 0.9 - 1.0)
    assert np.isclose(rep["covid_2020"]["peor_mes"], 0.9 * 0.9 - 1.0)


def test_stress_report_vacio() -> None:
    assert stress_report(pd.Series(dtype=float)) == {}


def test_spreads_del_universo_no_mutan_los_ajustes() -> None:
    settings = AppSettings()
    antes = dict(settings.slippage.spread_bps_by_symbol)
    uni = load_universe_spec("config/universe-26etf.json")
    out = settings_with_universe_spreads(settings, uni)
    assert settings.slippage.spread_bps_by_symbol == antes
    for e in uni.entries:
        if e.spread_bps is not None:
            assert out.slippage.spread_bps_by_symbol[e.symbol] == e.spread_bps
