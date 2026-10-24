from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.portfolio_stage import average_abs_positions, portfolio_positions, positions_to_weights
from ibtrader.portfolio.multiplier import diversification_multiplier, instrument_div_multiplier, rolling_idm

SYMBOLS: List[str] = ["SPY", "IEF", "TLT", "GLD", "PDBC", "VNQ"]
VOLS: Dict[str, float] = {"SPY": 0.16, "IEF": 0.06, "TLT": 0.14, "GLD": 0.15, "PDBC": 0.18, "VNQ": 0.20}
BETAS: Dict[str, float] = {"SPY": 0.6, "IEF": -0.3, "TLT": -0.4, "GLD": 0.1, "PDBC": 0.2, "VNQ": 0.5}


def _returns(seed: int = 0, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n)
    common = rng.standard_normal(n)
    data: Dict[str, np.ndarray] = {}
    for sym in SYMBOLS:
        beta = BETAS[sym]
        eps = rng.standard_normal(n)
        data[sym] = (beta * common + math.sqrt(1.0 - beta * beta) * eps) * VOLS[sym] / math.sqrt(252.0)
    return pd.DataFrame(data, index=idx)


def _prices(seed: int = 0, n: int = 500) -> pd.DataFrame:
    return 100.0 * (1.0 + _returns(seed, n)).cumprod()


def _identity_corr(n: int) -> pd.DataFrame:
    names = [f"S{i}" for i in range(n)]
    return pd.DataFrame(np.eye(n), index=names, columns=names)


# ----------------------------------------------------------------------------------------------
# Multiplicador de diversificación / IDM
# ----------------------------------------------------------------------------------------------


def test_idm_single_asset_is_one() -> None:
    corr = _identity_corr(1)
    assert diversification_multiplier(corr, pd.Series({"S0": 1.0})) == 1.0


def test_idm_uncorrelated_equal_weights() -> None:
    corr = _identity_corr(4)
    w = pd.Series(0.25, index=corr.index)
    assert diversification_multiplier(corr, w) == pytest.approx(2.0)


def test_idm_capped_at_dm_max() -> None:
    corr = _identity_corr(10)
    w = pd.Series(0.1, index=corr.index)
    assert diversification_multiplier(corr, w) == 2.5
    assert diversification_multiplier(corr, w, dm_max=4.0) == pytest.approx(math.sqrt(10.0))


def test_idm_perfectly_correlated_is_one() -> None:
    names = ["A", "B", "C"]
    corr = pd.DataFrame(np.ones((3, 3)), index=names, columns=names)
    assert diversification_multiplier(corr, pd.Series(1.0 / 3.0, index=names)) == 1.0


def test_idm_negative_correlations_are_floored() -> None:
    names = ["A", "B"]
    corr = pd.DataFrame([[1.0, -0.5], [-0.5, 1.0]], index=names, columns=names)
    w = pd.Series(0.5, index=names)
    assert diversification_multiplier(corr, w, corr_floor=0.0) == pytest.approx(math.sqrt(2.0))
    assert diversification_multiplier(corr, w, corr_floor=-1.0) == pytest.approx(2.0)


def test_idm_missing_weights_and_nan_corr_are_handled() -> None:
    names = ["A", "B", "C"]
    corr = pd.DataFrame([[1.0, 0.0, np.nan], [0.0, 1.0, 0.0], [np.nan, 0.0, 1.0]], index=names, columns=names)
    w = pd.Series({"A": 0.5, "B": 0.5})  # C sin peso → 0
    assert diversification_multiplier(corr, w) == pytest.approx(math.sqrt(2.0))


def test_instrument_div_multiplier_in_range() -> None:
    rets = _returns()
    w = pd.Series(1.0 / len(SYMBOLS), index=SYMBOLS)
    idm = instrument_div_multiplier(rets, w)
    assert 1.0 < idm <= 2.5
    assert instrument_div_multiplier(rets[["SPY"]], pd.Series({"SPY": 1.0})) == 1.0


def test_rolling_idm_backfill_range_and_point_in_time() -> None:
    rets = _returns()
    w = pd.DataFrame(1.0 / len(SYMBOLS), index=rets.index, columns=SYMBOLS)
    idm = rolling_idm(rets, w, min_periods=100, step=21, ewma_span=50)
    assert idm.name == "idm"
    assert (idm.iloc[:99] == 1.0).all()
    assert idm.iloc[-1] > 1.0
    assert ((idm >= 1.0) & (idm <= 2.5)).all()
    cut = rolling_idm(rets.iloc[:350], w.iloc[:350], min_periods=100, step=21, ewma_span=50)
    pd.testing.assert_series_equal(idm.iloc[:350], cut)


def test_rolling_idm_accepts_static_weights_series() -> None:
    rets = _returns()
    idm = rolling_idm(rets, pd.Series(1.0 / len(SYMBOLS), index=SYMBOLS), min_periods=100, step=21)
    assert idm.iloc[-1] > 1.0


# ----------------------------------------------------------------------------------------------
# Etapa de cartera
# ----------------------------------------------------------------------------------------------


def _subsystem() -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=4)
    return pd.DataFrame(
        {"SPY": [10.0, -5.0, 20.0, 0.0], "IEF": [-30.0, 40.0, 50.0, 10.0], "GLD": [5.0, 5.0, -5.0, 5.0]},
        index=idx,
    )


def test_portfolio_positions_formula_and_long_only() -> None:
    sub = _subsystem()
    w = pd.Series({"SPY": 0.5, "IEF": 0.3, "GLD": 0.2})
    px = pd.DataFrame(1.0, index=sub.index, columns=sub.columns)
    both = portfolio_positions(sub, w, 1.5, px, capital=1e9, long_only=False)
    expected = sub * w * 1.5
    pd.testing.assert_frame_equal(both, expected)
    longs = portfolio_positions(sub, w, 1.5, px, capital=1e9, long_only=True)
    pd.testing.assert_frame_equal(longs, expected.clip(lower=0.0))
    assert (longs >= 0).all().all()
    assert longs.loc[sub.index[0], "IEF"] == 0.0


def test_portfolio_positions_respects_max_leverage_exactly() -> None:
    idx = pd.bdate_range("2024-01-01", periods=3)
    sub = pd.DataFrame({"A": [100.0, 100.0, 1.0], "B": [100.0, 100.0, 1.0], "C": [100.0, 100.0, 1.0]}, index=idx)
    px = pd.DataFrame(100.0, index=idx, columns=sub.columns)
    w = pd.Series(1.0 / 3.0, index=sub.columns)
    capital = 10_000.0
    pos = portfolio_positions(sub, w, 2.5, px, capital=capital, max_leverage=1.0)
    gross = (pos * px).abs().sum(axis=1) / capital
    assert gross.iloc[0] == pytest.approx(1.0, abs=1e-12)
    assert gross.iloc[1] == pytest.approx(1.0, abs=1e-12)
    assert gross.iloc[2] == pytest.approx(0.025, abs=1e-12)
    # proporcional: las tres posiciones del día recortado siguen siendo iguales entre sí
    assert pos.iloc[0].nunique() == 1
    assert pos.attrs["days_capped"] == 2
    looser = portfolio_positions(sub, w, 2.5, px, capital=capital, max_leverage=1.5)
    assert ((looser * px).abs().sum(axis=1) / capital).iloc[0] == pytest.approx(1.5, abs=1e-12)


def test_portfolio_positions_aligns_weights_and_idm_by_date_with_ffill() -> None:
    sub = _subsystem()
    w = pd.DataFrame({"SPY": [0.5, 0.2], "IEF": [0.5, 0.8], "GLD": [0.0, 0.0]}, index=[sub.index[0], sub.index[2]])
    idm = pd.Series([1.2], index=[sub.index[1]])
    px = pd.DataFrame(1.0, index=sub.index, columns=sub.columns)
    pos = portfolio_positions(sub, w, idm, px, capital=1e9, long_only=False)
    assert pos.loc[sub.index[0], "SPY"] == pytest.approx(10.0 * 0.5 * 1.0)  # IDM aún no existe → 1.0
    assert pos.loc[sub.index[1], "SPY"] == pytest.approx(-5.0 * 0.5 * 1.2)  # pesos del día 0 (ffill)
    assert pos.loc[sub.index[3], "IEF"] == pytest.approx(10.0 * 0.8 * 1.2)  # pesos del día 2, IDM del día 1
    assert (pos["GLD"] == 0.0).all()


def test_portfolio_positions_rejects_bad_capital_or_leverage() -> None:
    sub = _subsystem()
    px = pd.DataFrame(1.0, index=sub.index, columns=sub.columns)
    w = pd.Series(1.0 / 3.0, index=sub.columns)
    with pytest.raises(ValueError):
        portfolio_positions(sub, w, 1.0, px, capital=0.0)
    with pytest.raises(ValueError):
        portfolio_positions(sub, w, 1.0, px, capital=1e5, max_leverage=0.0)


def test_positions_to_weights_is_inverse_of_weight_to_position() -> None:
    px = _prices(seed=9, n=50)
    rng = np.random.default_rng(3)
    capital = 250_000.0
    target_w = pd.DataFrame(rng.uniform(0.0, 0.3, size=px.shape), index=px.index, columns=px.columns)
    positions = target_w * capital / px  # de peso a acciones
    back = positions_to_weights(positions, px, capital)
    pd.testing.assert_frame_equal(back, target_w)
    forward = back * capital / px
    pd.testing.assert_frame_equal(forward, positions)


def test_average_abs_positions_alignment() -> None:
    idx = pd.bdate_range("2024-01-01", periods=4)
    vs = pd.DataFrame({"SPY": [100.0, -100.0, 50.0, 50.0], "IEF": [200.0, 200.0, -200.0, 200.0]}, index=idx)
    w = pd.DataFrame({"SPY": [0.5], "IEF": [0.5]}, index=[idx[1]])
    idm = pd.Series([1.5, 2.0], index=[idx[0], idx[3]])
    avg = average_abs_positions(vs, w, idm)
    assert avg.loc[idx[0], "SPY"] == 0.0  # sin pesos todavía → 0
    assert avg.loc[idx[1], "SPY"] == pytest.approx(100.0 * 0.5 * 1.5)
    assert avg.loc[idx[2], "IEF"] == pytest.approx(200.0 * 0.5 * 1.5)
    assert avg.loc[idx[3], "IEF"] == pytest.approx(200.0 * 0.5 * 2.0)
    assert (avg >= 0).all().all()
