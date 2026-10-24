from __future__ import annotations

import math
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import pytest

from ibtrader.data.universe import load_universe_spec
from ibtrader.portfolio.boxes import box_inverse_vol_weights, rolling_box_weights
from ibtrader.portfolio.hrp import hrp_weights, quasi_diagonal_order, rolling_hrp_weights

BOXES: Dict[str, str] = {
    "SPY": "us_equity",
    "IEF": "treasuries_intermediate",
    "TLT": "treasuries_long",
    "GLD": "gold",
    "PDBC": "commodities",
    "VNQ": "reit",
}
VOLS: Dict[str, float] = {"SPY": 0.16, "IEF": 0.06, "TLT": 0.14, "GLD": 0.15, "PDBC": 0.18, "VNQ": 0.20}
BETAS: Dict[str, float] = {"SPY": 0.6, "IEF": -0.3, "TLT": -0.4, "GLD": 0.1, "PDBC": 0.2, "VNQ": 0.5}
UNIVERSE_JSON = Path(__file__).resolve().parents[1] / "config" / "universe-10etf.json"


def _returns(seed: int = 0, n: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    common = rng.standard_normal(n)
    data: Dict[str, np.ndarray] = {}
    for sym, vol in VOLS.items():
        beta = BETAS[sym]
        eps = rng.standard_normal(n)
        data[sym] = (beta * common + math.sqrt(1.0 - beta * beta) * eps) * vol / math.sqrt(252.0)
    return pd.DataFrame(data, index=idx)


# ----------------------------------------------------------------------------------------------
# Pesos por cajas
# ----------------------------------------------------------------------------------------------


def test_box_weights_sum_to_one_and_cover_all_valid_symbols() -> None:
    w = box_inverse_vol_weights(pd.Series(VOLS), BOXES)
    assert set(w.index) == set(VOLS)
    assert w.sum() == pytest.approx(1.0)
    assert (w > 0).all()


def test_box_weights_equal_risk_per_box() -> None:
    vol = pd.Series({"A": 0.10, "B": 0.20, "C": 0.05, "D": 0.30, "E": 0.12})
    boxes = {"A": "x", "B": "x", "C": "y", "D": "y", "E": "z"}
    w = box_inverse_vol_weights(vol, boxes)
    risk = {box: sum(float(w[s] * vol[s]) for s, b in boxes.items() if b == box) for box in ("x", "y", "z")}
    total = sum(risk.values())
    for box in risk:
        assert risk[box] / total == pytest.approx(1.0 / 3.0)


def test_box_weights_inverse_vol_within_box() -> None:
    vol = pd.Series({"A": 0.10, "B": 0.20, "C": 0.05, "D": 0.30})
    boxes = {"A": "x", "B": "x", "C": "y", "D": "y"}
    w = box_inverse_vol_weights(vol, boxes)
    assert w["A"] / w["B"] == pytest.approx(vol["B"] / vol["A"])
    assert w["C"] / w["D"] == pytest.approx(vol["D"] / vol["C"])


def test_box_weights_exclude_nan_zero_and_unboxed_symbols() -> None:
    vol = pd.Series({"SPY": 0.16, "IEF": float("nan"), "TLT": 0.0, "GLD": 0.15, "XXX": 0.10})
    w = box_inverse_vol_weights(vol, BOXES)
    assert list(w.index) == ["SPY", "GLD"]
    assert w.sum() == pytest.approx(1.0)


def test_box_weights_empty_when_nothing_valid() -> None:
    w = box_inverse_vol_weights(pd.Series({"SPY": float("nan")}), BOXES)
    assert w.empty


def test_box_budgets_renormalized_over_present_boxes() -> None:
    vol = pd.Series({"A": 0.10, "B": 0.20, "C": 0.05})
    boxes = {"A": "x", "B": "x", "C": "y"}
    w = box_inverse_vol_weights(vol, boxes, box_budgets={"x": 0.6, "y": 0.2, "z": 0.2})
    risk_x = float(w["A"] * vol["A"] + w["B"] * vol["B"])
    risk_y = float(w["C"] * vol["C"])
    assert risk_x / (risk_x + risk_y) == pytest.approx(0.75)
    assert w.sum() == pytest.approx(1.0)


def test_rolling_box_weights_nan_before_min_periods_then_sum_one() -> None:
    rets = _returns()
    w = rolling_box_weights(rets, BOXES, lookback=252, min_periods=126, step=21)
    assert list(w.columns) == list(rets.columns)
    assert w.iloc[:126].isna().all().all()
    sums = w.iloc[126:].sum(axis=1)
    assert np.allclose(sums.to_numpy(), 1.0)
    assert (w.iloc[126:] > 0).all().all()


def test_rolling_box_weights_hold_between_recalcs() -> None:
    rets = _returns()
    w = rolling_box_weights(rets, BOXES, lookback=252, min_periods=126, step=21)
    pd.testing.assert_series_equal(w.iloc[126], w.iloc[140], check_names=False)
    assert not np.allclose(w.iloc[126].to_numpy(), w.iloc[147].to_numpy())


def test_rolling_box_weights_point_in_time() -> None:
    rets = _returns()
    full = rolling_box_weights(rets, BOXES, lookback=252, min_periods=126, step=21)
    cut = rolling_box_weights(rets.iloc[:500], BOXES, lookback=252, min_periods=126, step=21)
    pd.testing.assert_frame_equal(full.iloc[:500], cut)


def test_rolling_box_weights_symbol_listed_late_gets_zero_then_weight() -> None:
    rets = _returns()
    rets.loc[rets.index[:400], "PDBC"] = np.nan
    w = rolling_box_weights(rets, BOXES, lookback=252, min_periods=126, step=21)
    assert w.loc[rets.index[300], "PDBC"] == 0.0
    assert w.loc[rets.index[799], "PDBC"] > 0.0
    assert np.allclose(w.iloc[126:].sum(axis=1).to_numpy(), 1.0)


def test_box_weights_from_universe_json_one_box_each() -> None:
    spec = load_universe_spec(UNIVERSE_JSON)
    boxes = {e.symbol: e.box for e in spec.entries}
    assert len(spec.boxes()) == 10
    rng = np.random.default_rng(1)
    vol = pd.Series(rng.uniform(0.03, 0.25, size=len(spec.symbols)), index=spec.symbols)
    w = box_inverse_vol_weights(vol, boxes)
    assert w.sum() == pytest.approx(1.0)
    risk = (w * vol.reindex(w.index)).to_numpy()
    assert np.allclose(risk / risk.sum(), 0.1)


# ----------------------------------------------------------------------------------------------
# HRP
# ----------------------------------------------------------------------------------------------


def test_hrp_weights_sum_to_one_and_positive() -> None:
    w = hrp_weights(_returns())
    assert set(w.index) == set(VOLS)
    assert w.sum() == pytest.approx(1.0)
    assert (w > 0).all()


def test_hrp_single_asset_is_one() -> None:
    w = hrp_weights(_returns()[["SPY"]])
    assert list(w.index) == ["SPY"]
    assert w["SPY"] == 1.0


def test_hrp_permutation_invariant() -> None:
    rets = _returns(seed=3)
    base = hrp_weights(rets)
    rng = np.random.default_rng(7)
    for _ in range(5):
        cols = list(rets.columns)
        rng.shuffle(cols)
        w = hrp_weights(rets[cols])
        pd.testing.assert_series_equal(w.reindex(base.index), base, check_exact=False, atol=1e-12)
    pd.testing.assert_series_equal(hrp_weights(rets[cols[::-1]]).reindex(base.index), base, atol=1e-12)


def test_hrp_two_uncorrelated_assets_is_inverse_variance() -> None:
    rets = _returns(seed=5)[["IEF", "VNQ"]]
    w = hrp_weights(rets)
    var = rets.var()
    assert w["IEF"] == pytest.approx(var["VNQ"] / (var["IEF"] + var["VNQ"]))
    assert w["IEF"] > w["VNQ"]


def test_hrp_prefers_low_variance_asset() -> None:
    w = hrp_weights(_returns(seed=11))
    assert w["IEF"] > w["VNQ"]


def test_hrp_degenerate_covariance_does_not_raise() -> None:
    rets = _returns(seed=2)
    rets["FLAT"] = 0.0
    rets["HOLE"] = np.nan
    w = hrp_weights(rets)
    assert set(w.index) == set(rets.columns)
    assert w.sum() == pytest.approx(1.0)
    assert (w >= 0).all()
    assert w["FLAT"] == 0.0 and w["HOLE"] == 0.0


def test_hrp_quasi_diagonal_order_groups_correlated_assets() -> None:
    rets = _returns(seed=4)
    order = quasi_diagonal_order(rets.corr())
    assert sorted(order) == sorted(rets.columns)
    assert abs(order.index("IEF") - order.index("TLT")) == 1


def test_rolling_hrp_nan_before_min_periods_sum_one_and_point_in_time() -> None:
    rets = _returns(n=600)
    w = rolling_hrp_weights(rets, lookback=252, min_periods=126, step=21)
    assert w.iloc[:126].isna().all().all()
    assert np.allclose(w.iloc[126:].sum(axis=1).to_numpy(), 1.0)
    assert (w.iloc[126:] > 0).all().all()
    cut = rolling_hrp_weights(rets.iloc[:400], lookback=252, min_periods=126, step=21)
    pd.testing.assert_frame_equal(w.iloc[:400], cut)
