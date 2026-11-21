"""Retador contra titular: prueba pareada, presupuestos de riesgo por grupo y estudio completo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.config import AppSettings
from ibtrader.data.universe import UniverseEntry, UniverseSpec
from ibtrader.pipeline.system import SystemConfig, run_system
from ibtrader.research.challenger import (
    Contender,
    box_budgets_from_groups,
    paired_comparison,
    run_challenger_study,
)

UNI = UniverseSpec("t", [
    UniverseEntry("SPY", "equity", "eq_us"), UniverseEntry("VEA", "equity", "eq_dev"),
    UniverseEntry("IEF", "fixed_income", "bd"), UniverseEntry("GLD", "commodity", "au"),
    UniverseEntry("BIL", "cash", "cash"),
])


def _series(n: int, seed: int, mean: float, vol: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mean, vol, n), index=pd.bdate_range("2010-01-04", periods=n))


def test_paired_identical_strategies_are_indistinguishable() -> None:
    a = _series(2000, 1, 0.0003)
    cash = pd.Series(0.0, index=a.index)
    rep = paired_comparison(a, a.copy(), cash, n_boot=300)
    assert rep["veredicto"] == "indistinguible"
    assert rep["dif_sharpe"] == pytest.approx(0.0)


def test_paired_detects_a_real_edge_and_bonferroni_widens_the_interval() -> None:
    a = _series(3000, 2, 0.0002)
    noise = _series(3000, 3, 0.0, vol=0.001)
    better = a + 0.0004 + noise  # misma apuesta más 10 % anual: la pareada lo ve aunque el Sharpe suelto dude
    cash = pd.Series(0.0, index=a.index)
    one = paired_comparison(a, better, cash, n_boot=500)
    many = paired_comparison(a, better, cash, n_boot=500, n_comparisons=20)
    assert one["veredicto"] == "promover"
    assert paired_comparison(better, a, cash, n_boot=500)["veredicto"] == "peor"
    assert many["ic_dif_sharpe"][0] <= one["ic_dif_sharpe"][0]
    assert many["nivel_confianza"] > one["nivel_confianza"]


def test_paired_noise_is_not_promoted() -> None:
    a = _series(2500, 4, 0.0003)
    b = _series(2500, 5, 0.0003)  # misma media, otra suerte
    rep = paired_comparison(a, b, pd.Series(0.0, index=a.index), n_boot=500)
    assert rep["veredicto"] == "indistinguible"


def test_short_window_gives_no_verdict() -> None:
    a = _series(100, 6, 0.0)
    assert paired_comparison(a, a, pd.Series(0.0, index=a.index))["veredicto"] == "sin_datos"


def test_group_budgets_split_inside_the_group_and_skip_cash() -> None:
    b = box_budgets_from_groups(UNI, ["SPY", "VEA", "IEF", "GLD", "BIL"],
                                {"acciones": 0.5, "bonos": 0.25, "reales": 0.25})
    assert b == {"eq_us": 0.25, "eq_dev": 0.25, "bd": 0.25, "au": 0.25}
    with pytest.raises(ValueError):
        box_budgets_from_groups(UniverseSpec("x", [UniverseEntry("BTC", "crypto", "c")]), ["BTC"], {"acciones": 1})


def _data(n: int = 900) -> dict:
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2019-01-02", periods=n)
    out = {}
    for s, v in {"SPY": 0.16, "VEA": 0.17, "IEF": 0.07, "GLD": 0.15, "BIL": 0.003}.items():
        c = 100 * np.exp(np.cumsum(rng.normal(0.0003, v / np.sqrt(252), n)))
        out[s] = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 5e6}, index=idx)
    return out


def test_box_budgets_move_risk_weights_and_default_is_unchanged() -> None:
    px = pd.DataFrame({s: d["close"] for s, d in _data().items()})
    boxes = {e.symbol: e.box for e in UNI.entries}
    kw = dict(boxes=boxes, scalar_min_periods=60, fdm_min_periods=60, idm_min_periods=60, box_min_periods=40, step=5)
    base = run_system(px, SystemConfig(rules=("long_const",), **kw))
    same = run_system(px, SystemConfig(rules=("long_const",), box_budgets=None, **kw))
    tilt = run_system(px, SystemConfig(rules=("long_const",), box_budgets={"eq_us": 0.4, "eq_dev": 0.4, "bd": 0.1,
                                                                             "au": 0.1}, **kw))
    pd.testing.assert_frame_equal(base.target_weights, same.target_weights)
    w0, w1 = base.instrument_weights.iloc[-1], tilt.instrument_weights.iloc[-1]
    assert w0["SPY"] == pytest.approx(0.25) and w1["SPY"] == pytest.approx(0.4)
    assert w1["IEF"] == pytest.approx(0.1)
    with pytest.raises(ValueError):
        SystemConfig(instrument_weighting="hrp", box_budgets={"eq_us": 1.0})
    with pytest.raises(ValueError):
        SystemConfig(box_budgets={"eq_us": -1.0})


def test_study_runs_end_to_end_on_a_common_window() -> None:
    s = AppSettings(_env_file=None)
    fast = dict(scalar_min_periods=60, fdm_min_periods=60, idm_min_periods=60, box_min_periods=40, step=5)
    inc = Contender("titular", rules=("long_const",), extra=fast)
    cha = (Contender("perfil", rules=("long_const",), kind="perfil", extra=fast,
                     group_budgets={"acciones": 0.6, "bonos": 0.2, "reales": 0.2}),)
    rep = run_challenger_study(_data(), s, UNI, incumbent=inc, challengers=cha, n_boot=200)
    ids = [r["id"] for r in rep["filas"]]
    assert ids == ["titular", "perfil", "referencia_60_40"]
    perfil = rep["filas"][1]
    assert perfil["contra_titular"]["veredicto"] in {"promover", "indistinguible", "peor"}
    assert perfil["contra_titular"]["n_obs"] == rep["n_sesiones"]
    assert perfil["peso_medio_por_grupo"]["acciones"] > rep["filas"][0]["peso_medio_por_grupo"]["acciones"]


def test_core_mix_keeps_the_core_and_scales_the_trend_book() -> None:
    px = pd.DataFrame({s: d["close"] for s, d in _data().items()})
    boxes = {e.symbol: e.box for e in UNI.entries}
    kw = dict(boxes=boxes, scalar_min_periods=60, fdm_min_periods=60, idm_min_periods=60, box_min_periods=40, step=5)
    base = run_system(px, SystemConfig(**kw))
    mix = run_system(px, SystemConfig(core_weights={"SPY": 0.6, "IEF": 0.4}, core_frac=0.25, **kw))
    b, m = base.target_weights.iloc[-1], mix.target_weights.iloc[-1]
    assert m["SPY"] == pytest.approx(0.75 * b["SPY"] + 0.15)
    assert m["IEF"] == pytest.approx(0.75 * b["IEF"] + 0.10)
    assert m["GLD"] == pytest.approx(0.75 * b["GLD"])
    assert m["BIL"] == pytest.approx(0.75 * b["BIL"])
    assert mix.target_weights.sum(axis=1).max() <= 1.0 + 1e-9
    # Antes del primer peso de tendencia no hay núcleo: la ventana evaluada es la misma.
    first = base.target_weights.notna().any(axis=1).idxmax()
    assert mix.target_weights.loc[:first].iloc[:-1].isna().all().all()
    # El núcleo no añade días de operación: SPY solo cambia cuando cambia su parte de tendencia.
    chg_b = base.target_weights["SPY"].diff().abs() > 1e-12
    chg_m = mix.target_weights["SPY"].diff().abs() > 1e-12
    assert (chg_m & ~chg_b).sum() <= 1  # solo el día de entrada del núcleo


def test_core_mix_validation() -> None:
    with pytest.raises(ValueError):
        SystemConfig(core_frac=0.3)
    with pytest.raises(ValueError):
        SystemConfig(core_frac=0.3, core_weights={"SPY": 0.5})
    with pytest.raises(ValueError):
        SystemConfig(core_frac=0.3, core_weights={"SPY": 1.0}, long_only=False)
    px = pd.DataFrame({s: d["close"] for s, d in _data().items()})
    with pytest.raises(ValueError):
        run_system(px, SystemConfig(core_frac=0.3, core_weights={"QQQ": 1.0}))
