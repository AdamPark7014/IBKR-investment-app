"""Tope por clase de activo: recorta el grupo que se pasa y manda lo que sobra al efectivo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.system import SystemConfig, run_system


def _prices() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2015-01-01", periods=1500)
    px = pd.DataFrame({s: 100 * np.exp(np.cumsum(rng.normal(0.0008, 0.008, len(idx)))) for s in "ABC"}, index=idx)
    px["BIL"] = 100 * np.exp(np.arange(len(idx)) * 0.00005)
    return px


BOXES = {"A": "a", "B": "b", "C": "c", "BIL": "cash"}
GROUPS = {"A": "acciones", "B": "acciones", "C": "bonos"}


def test_el_tope_recorta_el_grupo_y_el_resto_va_a_efectivo() -> None:
    px = _prices()
    base = run_system(px, SystemConfig(boxes=BOXES))
    capped = run_system(px, SystemConfig(boxes=BOXES, peer_groups=GROUPS, group_caps={"acciones": 0.30}))
    assert base.warmup_end is not None
    w0 = base.target_weights.loc[base.warmup_end:].fillna(0.0)
    w1 = capped.target_weights.loc[base.warmup_end:].fillna(0.0)
    assert (w0[["A", "B"]].sum(axis=1) > 0.30).any()  # sin tope sí se pasa
    assert (w1[["A", "B"]].sum(axis=1) <= 0.30 + 1e-9).all()
    pd.testing.assert_series_equal(w1["C"], w0["C"])  # el otro grupo no se toca
    assert np.allclose(w1.sum(axis=1), w0.sum(axis=1))  # lo recortado está en BIL, no desaparece
    assert (w1.sum(axis=1) <= 1.0 + 1e-9).all()
    hit = w0[["A", "B"]].sum(axis=1) > 0.30
    ratio0 = (w0["A"] / w0["B"])[hit & (w0["B"] > 0)]
    ratio1 = (w1["A"] / w1["B"])[hit & (w0["B"] > 0)]
    assert np.allclose(ratio0, ratio1)  # recorte en proporción


def test_un_tope_holgado_no_cambia_nada() -> None:
    px = _prices()
    base = run_system(px, SystemConfig(boxes=BOXES))
    loose = run_system(px, SystemConfig(boxes=BOXES, peer_groups=GROUPS, group_caps={"acciones": 1.0, "bonos": 1.0}))
    pd.testing.assert_frame_equal(base.target_weights, loose.target_weights)


def test_validaciones() -> None:
    with pytest.raises(ValueError, match="peer_groups"):
        SystemConfig(group_caps={"acciones": 0.5})
    with pytest.raises(ValueError, match="group_caps"):
        SystemConfig(peer_groups=GROUPS, group_caps={"acciones": 1.5})
