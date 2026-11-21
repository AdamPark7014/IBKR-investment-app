"""Momentum relativo: señal de corte transversal dentro de cada clase de activo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.rules import relative_momentum
from ibtrader.pipeline.system import SystemConfig, run_system


def test_resta_la_media_del_grupo_y_suma_cero() -> None:
    idx = pd.bdate_range("2024-01-01", periods=3)
    mom = pd.DataFrame({"A": [1.0, 2.0, 3.0], "B": [3.0, 2.0, np.nan], "C": [5.0, 5.0, 5.0], "D": [1.0, 1.0, 1.0]},
                       index=idx)
    out = relative_momentum(mom, {"A": "g1", "B": "g1", "C": "g2"})
    assert out.loc[idx[0], "A"] == -1.0 and out.loc[idx[0], "B"] == 1.0
    assert out.loc[idx[1], ["A", "B"]].abs().sum() == 0.0
    assert out.loc[idx[2], ["A", "B"]].isna().all()  # un solo par con dato: nada con qué comparar
    assert out["C"].isna().all()  # grupo de un solo símbolo
    assert out["D"].isna().all()  # símbolo sin grupo


def test_es_punto_en_el_tiempo() -> None:
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=50)
    mom = pd.DataFrame(rng.normal(size=(50, 3)), index=idx, columns=list("ABC"))
    groups = {"A": "g", "B": "g", "C": "g"}
    full = relative_momentum(mom, groups)
    cut = relative_momentum(mom.iloc[:30], groups)
    pd.testing.assert_frame_equal(full.iloc[:30], cut)


def test_la_regla_exige_grupos_de_pares() -> None:
    with pytest.raises(ValueError, match="peer_groups"):
        SystemConfig(rules=("ewmac16_64", "relmom_1_3_12"))


def test_el_sistema_corre_con_momentum_relativo() -> None:
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2015-01-01", periods=1500)
    drift = {"A": 0.0006, "B": 0.0001, "C": 0.0004, "D": 0.0}
    px = pd.DataFrame({s: 100 * np.exp(np.cumsum(rng.normal(d, 0.01, len(idx)))) for s, d in drift.items()}, index=idx)
    px["BIL"] = 100 * np.exp(np.arange(len(idx)) * 0.00005)
    cfg = SystemConfig(
        rules=("ewmac16_64", "relmom_1_3_12"), peer_groups={"A": "x", "B": "x", "C": "y", "D": "y"},
        boxes={"A": "a", "B": "b", "C": "c", "D": "d", "BIL": "cash"},
    )
    out = run_system(px, cfg)
    assert out.warmup_end is not None
    w = out.target_weights.loc[out.warmup_end:]
    assert (w.fillna(0.0) >= -1e-12).all().all()
    assert (w.fillna(0.0).sum(axis=1) <= 1.0 + 1e-9).all()
    assert out.raw_forecasts["relmom_1_3_12"][["A", "B"]].dropna().sum(axis=1).abs().max() < 1e-9
