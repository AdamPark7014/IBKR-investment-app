from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.buffering import apply_buffer, position_buffer
from ibtrader.pipeline.combine import combine_forecasts, equal_weights, forecast_div_multiplier
from ibtrader.pipeline.forecast import estimate_forecast_scalar, scale_and_cap
from ibtrader.pipeline.rules import DEFAULT_RULES, run_rule
from ibtrader.pipeline.sizing import position_to_weight, subsystem_position, vol_scalar
from ibtrader.pipeline.vol import pct_vol_daily, price_vol_daily


def make_random_walk(n: int, seed: int, drift: float, vol: float, start: float = 100.0) -> pd.Series:
    """Geometric random walk with a business-day index; deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    rets = drift + vol * rng.standard_normal(n)
    idx = pd.bdate_range("2000-01-03", periods=n)
    return pd.Series(start * np.exp(np.cumsum(rets)), index=idx, name="close")


def _const(value: float, n: int = 5) -> pd.Series:
    return pd.Series(value, index=pd.bdate_range("2022-01-03", periods=n), dtype=float)


# --------------------------------------------------------------------------------------------
# sizing
# --------------------------------------------------------------------------------------------


def test_vol_scalar_reference_numbers() -> None:
    # capital 100 000, tau 10 %: cash_vol_daily = 10 000 / 16 = 625.
    # price 100, 1 % daily vol: block_value = 1, instr_value_vol = 1 * 1 = 1 -> 625 shares.
    vs = vol_scalar(_const(100.0), _const(0.01), capital=100_000.0, tau=0.10)
    assert vs.notna().all()
    assert float(vs.iloc[0]) == pytest.approx(625.0)
    assert float(vs.iloc[-1]) == pytest.approx(625.0)
    # Same instrument at 2 % daily vol -> half the shares; price 50 at 1 % -> double.
    assert float(vol_scalar(_const(100.0), _const(0.02), 100_000.0, 0.10).iloc[0]) == pytest.approx(312.5)
    assert float(vol_scalar(_const(50.0), _const(0.01), 100_000.0, 0.10).iloc[0]) == pytest.approx(1250.0)


def test_vol_scalar_scaling_laws_and_validation() -> None:
    price = _const(100.0)
    pct = _const(0.01)
    base = float(vol_scalar(price, pct, 100_000.0, 0.10).iloc[0])
    assert float(vol_scalar(price, pct, 200_000.0, 0.10).iloc[0]) == pytest.approx(2.0 * base)
    assert float(vol_scalar(price, pct, 100_000.0, 0.20).iloc[0]) == pytest.approx(2.0 * base)
    assert float(vol_scalar(price, pct, 100_000.0, 0.10, block_value_mult=0.02).iloc[0]) == pytest.approx(base / 2.0)
    # Zero / NaN volatility -> NaN, never inf.
    vs0 = vol_scalar(price, _const(0.0), 100_000.0, 0.10)
    assert vs0.isna().all()
    with pytest.raises(ValueError):
        vol_scalar(price, pct, 0.0, 0.10)
    with pytest.raises(ValueError):
        vol_scalar(price, pct, 100_000.0, 0.0)


def test_subsystem_position_linear_in_forecast() -> None:
    vs = _const(625.0)
    assert float(subsystem_position(vs, _const(10.0)).iloc[0]) == pytest.approx(625.0)
    assert float(subsystem_position(vs, _const(20.0)).iloc[0]) == pytest.approx(1250.0)
    assert float(subsystem_position(vs, _const(-5.0)).iloc[0]) == pytest.approx(-312.5)
    assert float(subsystem_position(vs, _const(0.0)).iloc[0]) == 0.0
    f = pd.Series(np.linspace(-20.0, 20.0, 5), index=vs.index)
    pos = subsystem_position(vs, f)
    # Linear: equal forecast steps of 10 give equal position steps of 625 * 10 / 10.
    assert np.allclose(np.diff(pos.to_numpy()), 625.0)
    assert np.allclose(pos.to_numpy(), 625.0 * f.to_numpy() / 10.0)
    assert np.isnan(subsystem_position(vs, pd.Series(np.nan, index=vs.index)).iloc[0])


def test_position_to_weight() -> None:
    w = position_to_weight(_const(625.0), _const(100.0), capital=100_000.0)
    assert float(w.iloc[0]) == pytest.approx(0.625)
    assert float(position_to_weight(_const(-100.0), _const(50.0), 10_000.0).iloc[0]) == pytest.approx(-0.5)
    with pytest.raises(ValueError):
        position_to_weight(_const(1.0), _const(1.0), 0.0)


# --------------------------------------------------------------------------------------------
# buffering
# --------------------------------------------------------------------------------------------


def test_position_buffer_is_fraction_of_abs_average_position() -> None:
    avg = pd.Series([625.0, -625.0, 0.0, np.nan], index=pd.bdate_range("2022-01-03", periods=4))
    buf = position_buffer(avg)
    assert buf.iloc[0] == pytest.approx(62.5)
    assert buf.iloc[1] == pytest.approx(62.5)
    assert buf.iloc[2] == 0.0
    assert np.isnan(buf.iloc[3])
    assert position_buffer(avg, buffer_frac=0.2).iloc[0] == pytest.approx(125.0)
    with pytest.raises(ValueError):
        position_buffer(avg, buffer_frac=-0.1)


def test_apply_buffer_holds_inside_band() -> None:
    idx = pd.bdate_range("2022-01-03", periods=6)
    target = pd.Series([100.0, 105.0, 98.0, 100.0, 92.0, 100.0], index=idx)
    buffer = pd.Series(10.0, index=idx)
    pos = apply_buffer(target, buffer, trade_to_edge=True)
    # 0 -> edge 90; 105 is 15 away -> edge 95; everything after stays within +/-10 of 95.
    assert pos.tolist() == [90.0, 95.0, 95.0, 95.0, 95.0, 95.0]
    pos_t = apply_buffer(target, buffer, trade_to_edge=False)
    assert pos_t.tolist() == [100.0] * 6
    assert pos.index.equals(idx)
    assert pos.dtype == float


def test_apply_buffer_trades_to_nearest_edge_outside_band() -> None:
    idx = pd.bdate_range("2022-01-03", periods=5)
    target = pd.Series([100.0, 50.0, 50.0, -40.0, np.nan], index=idx)
    buffer = pd.Series([10.0, 10.0, np.nan, 5.0, 5.0], index=idx)
    pos = apply_buffer(target, buffer)
    # 0 < 100 -> 100 - 10 = 90; 90 > 50 -> 50 + 10 = 60; NaN buffer -> straight to target 50;
    # 50 > -40 -> -40 + 5 = -35; NaN target -> hold.
    assert pos.tolist() == [90.0, 60.0, 50.0, -35.0, -35.0]
    # Exactly on the band edge counts as inside (no trade).
    t2 = pd.Series([100.0, 110.0, 80.0], index=idx[:3])
    b2 = pd.Series(10.0, index=idx[:3])
    assert apply_buffer(t2, b2).tolist() == [90.0, 100.0, 90.0]
    # Buffer aligned to the target index (extra / missing dates are tolerated).
    b_short = pd.Series(10.0, index=idx[1:])
    pos_al = apply_buffer(target, b_short)
    assert pos_al.iloc[0] == 100.0  # missing buffer on day 1 -> no band -> target


def test_apply_buffer_reproducible_fewer_trades_and_within_band() -> None:
    rng = np.random.default_rng(99)
    idx = pd.bdate_range("2015-01-01", periods=1500)
    target = pd.Series(500.0 + np.cumsum(rng.standard_normal(1500)) * 20.0, index=idx)
    buffer = pd.Series(50.0, index=idx)
    pos_a = apply_buffer(target, buffer)
    pos_b = apply_buffer(target, buffer)
    pd.testing.assert_series_equal(pos_a, pos_b)
    trades_raw = int((target.diff().abs() > 1e-12).sum())
    trades_buf = int((pos_a.diff().abs() > 1e-12).sum())
    assert trades_buf < trades_raw
    assert trades_buf < 0.6 * trades_raw
    # After each update the position is always inside the band around the target.
    assert (((target - pos_a).abs() <= buffer + 1e-9)).all()
    # Without a buffer the position is just the target.
    pd.testing.assert_series_equal(apply_buffer(target, pd.Series(0.0, index=idx)), target, check_names=False)


def test_apply_buffer_no_lookahead() -> None:
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2015-01-01", periods=400)
    target = pd.Series(np.cumsum(rng.standard_normal(400)) * 10.0, index=idx)
    buffer = pd.Series(np.abs(rng.standard_normal(400)) * 5.0, index=idx)
    full = apply_buffer(target, buffer)
    trunc = apply_buffer(target.iloc[:250], buffer.iloc[:250])
    pd.testing.assert_series_equal(full.iloc[:250], trunc)


# --------------------------------------------------------------------------------------------
# chain smoke test (how pipeline.system is expected to wire the steps)
# --------------------------------------------------------------------------------------------


def test_pipeline_chain_produces_finite_buffered_positions() -> None:
    capital, tau = 100_000.0, 0.10
    prices = {s: make_random_walk(1500, 200 + i, 0.0003, 0.012) for i, s in enumerate(("SPY", "QQQ", "IWM"))}
    price_vols = {s: price_vol_daily(p) for s, p in prices.items()}
    pct_vols = {s: pct_vol_daily(p) for s, p in prices.items()}

    raw = {rule: {s: run_rule(rule, prices[s], price_vols[s]) for s in prices} for rule in DEFAULT_RULES}
    scalars = {rule: estimate_forecast_scalar(raw[rule]) for rule in DEFAULT_RULES}
    weights = equal_weights(DEFAULT_RULES)

    for sym in prices:
        scaled = pd.DataFrame({rule: scale_and_cap(raw[rule][sym], scalars[rule]) for rule in DEFAULT_RULES})
        fdm = forecast_div_multiplier(scaled, weights)
        combined = combine_forecasts(scaled, weights, fdm)
        assert float(combined.abs().max()) <= 20.0
        vs = vol_scalar(prices[sym], pct_vols[sym], capital, tau)
        pos = subsystem_position(vs, combined)
        buf = position_buffer(vs.abs())
        held = apply_buffer(pos, buf)
        tail = held.iloc[-500:]
        assert np.isfinite(tail.to_numpy()).all()
        w = position_to_weight(held, prices[sym], capital)
        # A single ETF at 10 % vol target and 1.2 % daily vol holds well under 3x capital.
        assert float(w.abs().max()) < 3.0
        assert int((held.diff().abs() > 1e-9).sum()) < int((pos.diff().abs() > 1e-9).sum())
