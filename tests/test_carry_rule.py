"""Carry: lo que paga un ETF por tenerlo, por encima del efectivo y por unidad de riesgo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.rules import carry_forecast, trailing_yield
from ibtrader.pipeline.system import SystemConfig, run_system
from ibtrader.strategy.pipeline_strategy import PipelineStrategy


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2015-01-01", periods=n)


def test_trailing_yield_suma_doce_meses_y_espera_la_ventana() -> None:
    idx = _idx(300)
    div = pd.Series(0.0, index=idx)
    div.iloc[[10, 100, 200]] = 1.0
    y = trailing_yield(div, pd.Series(100.0, index=idx), window=252)
    assert y.iloc[:251].isna().all()
    assert np.isclose(y.iloc[251], 0.03)
    assert np.isclose(y.iloc[270], 0.02)  # el reparto del día 10 ya salió de la ventana


def test_carry_resta_el_efectivo_y_divide_por_el_riesgo() -> None:
    idx = _idx(260)
    div = {"A": pd.Series(4.0 / 252, index=idx), "B": pd.Series(0.0, index=idx),
           "CASH": pd.Series(2.0 / 252, index=idx)}
    px = {s: pd.Series(100.0, index=idx) for s in div}
    vol = {s: pd.Series(0.01, index=idx) for s in div}
    raw = carry_forecast(div, px, vol, cash_symbol="CASH")
    assert list(raw.columns) == ["A", "B"]
    assert np.isclose(raw["A"].iloc[-1], (0.04 - 0.02) / 0.16)
    assert raw["B"].iloc[-1] < 0  # no paga nada: peor que el efectivo


def test_carry_es_punto_en_el_tiempo() -> None:
    rng = np.random.default_rng(0)
    idx = _idx(400)
    div = {s: pd.Series(rng.random(400) * (rng.random(400) > 0.95), index=idx) for s in "AB"}
    px = {s: pd.Series(100 + rng.normal(0, 1, 400).cumsum(), index=idx) for s in "AB"}
    vol = {s: pd.Series(0.01, index=idx) for s in "AB"}
    full = carry_forecast(div, px, vol)
    cut = carry_forecast({s: v.iloc[:300] for s, v in div.items()}, {s: v.iloc[:300] for s, v in px.items()},
                         {s: v.iloc[:300] for s, v in vol.items()})
    pd.testing.assert_frame_equal(full.iloc[:300], cut)


def test_el_sistema_exige_el_pronostico_externo() -> None:
    idx = _idx(50)
    px = pd.DataFrame({"A": np.linspace(100, 110, 50), "B": np.linspace(100, 90, 50)}, index=idx)
    with pytest.raises(ValueError, match="extra_raw"):
        run_system(px, SystemConfig(rules=("ewmac16_64", "carry_12m")))


def test_la_estrategia_calcula_el_carry_con_los_repartos() -> None:
    rng = np.random.default_rng(2)
    idx = _idx(1500)
    data = {}
    for sym, (drift, pay) in {"A": (0.0003, 0.05), "B": (0.0003, 0.0), "BIL": (0.00005, 0.01)}.items():
        vol = 0.0001 if sym == "BIL" else 0.01
        close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, len(idx))))
        div = np.zeros(len(idx))
        div[::63] = pay * 100 / 4
        data[sym] = pd.DataFrame({"close": close, "close_raw": close, "div_cash": div}, index=idx)
    strat = PipelineStrategy(SystemConfig(rules=("ewmac16_64", "carry_12m"),
                                          boxes={"A": "a", "B": "b", "BIL": "cash"}))
    sig = strat.generate_signals(data)
    out = strat.last_output
    assert out is not None and out.warmup_end is not None
    carry = out.raw_forecasts["carry_12m"].dropna()
    assert (carry["A"] > 0).all() and (carry["B"] < 0).all()
    assert all((s >= -1e-12).all() for s in sig.values())
    del data["A"]["div_cash"]
    with pytest.raises(ValueError, match="div_cash"):
        strat.generate_signals(data)
