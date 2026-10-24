from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.rules import (
    DEFAULT_RULES,
    EWMAC_SPEEDS,
    FIXED_FORECAST_SCALARS,
    ewmac,
    run_rule,
    run_rules,
    tsmom_multi,
)
from ibtrader.pipeline.vol import pct_vol_daily, price_vol_daily


def make_random_walk(n: int, seed: int, drift: float, vol: float, start: float = 100.0) -> pd.Series:
    """Geometric random walk with a business-day index; deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    rets = drift + vol * rng.standard_normal(n)
    idx = pd.bdate_range("2000-01-03", periods=n)
    return pd.Series(start * np.exp(np.cumsum(rets)), index=idx, name="close")


# --------------------------------------------------------------------------------------------
# vol
# --------------------------------------------------------------------------------------------


def test_price_vol_positive_in_price_units() -> None:
    px = make_random_walk(1500, 1, 0.0, 0.01)
    vol = price_vol_daily(px)
    valid = vol.dropna()
    assert len(valid) > 1000
    assert (valid > 0).all()
    # 1 % daily vol on a ~100 price -> ~1 price unit; should be of that order, not a fraction.
    ratio = (valid / px.loc[valid.index]).iloc[-500:].mean()
    assert 0.005 < ratio < 0.02
    assert 0.5 < valid.iloc[-500:].mean() / (0.01 * px.iloc[-500:].mean()) < 2.0


def test_price_vol_nan_during_warmup_only() -> None:
    px = make_random_walk(300, 2, 0.0, 0.01)
    vol = price_vol_daily(px, min_periods=10)
    # diff() loses the first bar; ewm std needs min_periods diffs -> first valid at position 10.
    assert vol.iloc[:10].isna().all()
    assert vol.iloc[10:].notna().all()
    assert vol.index.equals(px.index)


def test_price_vol_no_lookahead() -> None:
    px = make_random_walk(1200, 3, 0.0002, 0.012)
    full = price_vol_daily(px)
    for cut in (400, 777, 1100):
        trunc = price_vol_daily(px.iloc[:cut])
        pd.testing.assert_series_equal(full.iloc[:cut], trunc, check_names=False)


def test_price_vol_floor_quantile_kicks_in_after_vol_collapse() -> None:
    # 2000 noisy days then 60 almost-flat days (< 5 % of the history): the pure EWMA vol decays
    # quickly, but the floor (5 % quantile of the vol history up to t) keeps it near the bottom of
    # the noisy-regime range. A quiet regime longer than the quantile share would, correctly, pull
    # the floor down with it.
    hot = make_random_walk(2000, 4, 0.0, 0.02)
    rng = np.random.default_rng(44)
    quiet_rets = 0.0001 * rng.standard_normal(60)
    quiet = pd.Series(
        float(hot.iloc[-1]) * np.exp(np.cumsum(quiet_rets)),
        index=pd.bdate_range(hot.index[-1] + pd.offsets.BDay(1), periods=60),
    )
    px = pd.concat([hot, quiet])

    # mix_long=0 isolates the floor: the 30 % long-run mean would by itself keep the vol up.
    floored = price_vol_daily(px, mix_long=0.0, floor_quantile=0.05)
    unfloored = price_vol_daily(px, mix_long=0.0, floor_quantile=0.0)  # running minimum == no-op floor
    hot_level = float(unfloored.iloc[:2000].mean())
    assert (floored.dropna() >= unfloored.dropna() - 1e-12).all()
    assert unfloored.iloc[-1] < 0.4 * hot_level  # EWMA alone decays
    assert floored.iloc[-1] > 2.0 * unfloored.iloc[-1]
    assert floored.iloc[-1] > 0.5 * hot_level
    # The floor is exactly the expanding 5 % quantile of the (unfloored) vol up to t.
    expected_floor = unfloored.expanding(min_periods=10).quantile(0.05)
    assert floored.iloc[-1] == pytest.approx(float(expected_floor.iloc[-1]))
    assert (floored.iloc[-20:] > unfloored.iloc[-20:]).all()
    # During the hot regime the floor only touches the bottom tail of the distribution.
    assert float((floored.iloc[:2000] > unfloored.iloc[:2000] + 1e-12).mean()) < 0.2
    # With the default 30 % long-run mix the vol does not collapse even before the floor.
    mixed = price_vol_daily(px, floor_quantile=0.0)
    assert mixed.iloc[-1] > 0.3 * mixed.iloc[:2000].mean()


def test_pct_vol_daily_is_fraction_of_price() -> None:
    px = make_random_walk(1500, 5, 0.0, 0.01)
    pct = pct_vol_daily(px)
    pv = price_vol_daily(px)
    pd.testing.assert_series_equal(pct, pv / px, check_names=False)
    tail = pct.iloc[-500:]
    assert 0.005 < tail.mean() < 0.02
    assert (tail > 0).all()


def test_price_vol_rejects_bad_params() -> None:
    px = make_random_walk(50, 6, 0.0, 0.01)
    with pytest.raises(ValueError):
        price_vol_daily(px, span=0)
    with pytest.raises(ValueError):
        price_vol_daily(px, mix_long=1.5)
    with pytest.raises(ValueError):
        price_vol_daily(px, floor_quantile=-0.1)


# --------------------------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------------------------


def _trend(n: int, slope: float, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=n)
    noise = 0.05 * rng.standard_normal(n)
    return pd.Series(100.0 + slope * np.arange(n) + noise, index=idx)


def test_ewmac_sign_follows_trend() -> None:
    up = _trend(600, 0.5, 7)
    down = _trend(600, -0.5, 8)
    f_up = ewmac(up, price_vol_daily(up), 16, 64).dropna()
    f_down = ewmac(down, price_vol_daily(down), 16, 64).dropna()
    assert (f_up.iloc[-300:] > 0).all()
    assert (f_down.iloc[-300:] < 0).all()
    # Scale-free: doubling the price level doubles both numerator and vol.
    f_up2 = ewmac(up * 2.0, price_vol_daily(up * 2.0), 16, 64).dropna()
    pd.testing.assert_series_equal(f_up, f_up2, check_names=False, rtol=1e-9)


def test_ewmac_near_zero_on_flat_series() -> None:
    flat = _trend(800, 0.0, 9)
    raw = ewmac(flat, price_vol_daily(flat), 16, 64).dropna()
    assert abs(float(raw.iloc[-500:].mean())) < 0.25
    assert float(raw.abs().iloc[-500:].mean()) < 1.0
    # Exactly constant price: vol is 0, the forecast must be NaN rather than +/- inf.
    const = pd.Series(100.0, index=flat.index)
    raw_const = ewmac(const, price_vol_daily(const), 16, 64)
    assert not np.isinf(raw_const.to_numpy()).any()
    with pytest.raises(ValueError):
        ewmac(flat, price_vol_daily(flat), 64, 16)


def test_tsmom_multi_uses_available_lookbacks_only() -> None:
    px = make_random_walk(100, 10, 0.001, 0.01)
    vol = price_vol_daily(px)
    out = tsmom_multi(px, vol, lookbacks=(21, 63, 252))
    comp = {lb: (px - px.shift(lb)) / (vol * np.sqrt(lb)) for lb in (21, 63, 252)}
    # t < 21: nothing available.
    assert out.iloc[:21].isna().all()
    # 21 <= t < 63: only the 1-month horizon.
    assert out.iloc[40] == pytest.approx(float(comp[21].iloc[40]))
    # 63 <= t < 252: mean of the 1- and 3-month horizons.
    expected_80 = 0.5 * (float(comp[21].iloc[80]) + float(comp[63].iloc[80]))
    assert out.iloc[80] == pytest.approx(expected_80)
    assert out.iloc[21:].notna().all()
    # Full history: all three horizons.
    long_px = make_random_walk(600, 11, 0.0, 0.01)
    long_vol = price_vol_daily(long_px)
    long_out = tsmom_multi(long_px, long_vol)
    comp_long = [(long_px - long_px.shift(lb)) / (long_vol * np.sqrt(lb)) for lb in (21, 63, 252)]
    expected_last = float(sum(c.iloc[-1] for c in comp_long) / 3.0)
    assert long_out.iloc[-1] == pytest.approx(expected_last)


def test_tsmom_multi_no_lookahead_and_validation() -> None:
    px = make_random_walk(700, 12, 0.0, 0.01)
    vol = price_vol_daily(px)
    full = tsmom_multi(px, vol)
    trunc = tsmom_multi(px.iloc[:500], vol.iloc[:500])
    pd.testing.assert_series_equal(full.iloc[:500], trunc, check_names=False)
    with pytest.raises(ValueError):
        tsmom_multi(px, vol, lookbacks=())


def test_run_rule_dispatches_by_name() -> None:
    px = make_random_walk(700, 13, 0.0, 0.01)
    vol = price_vol_daily(px)
    pd.testing.assert_series_equal(run_rule("ewmac16_64", px, vol), ewmac(px, vol, 16, 64))
    pd.testing.assert_series_equal(run_rule("tsmom_1_3_12", px, vol), tsmom_multi(px, vol))
    # Any ewmacF_S is accepted, not only the catalogued speeds.
    pd.testing.assert_series_equal(run_rule("ewmac3_12", px, vol), ewmac(px, vol, 3, 12))
    with pytest.raises(ValueError):
        run_rule("carry", px, vol)


def test_run_rules_shape_and_constants() -> None:
    prices = {s: make_random_walk(400, i, 0.0, 0.01) for i, s in enumerate(("SPY", "QQQ", "IWM"))}
    vols = {s: price_vol_daily(p) for s, p in prices.items()}
    out = run_rules(prices, vols, DEFAULT_RULES)
    assert tuple(out.keys()) == DEFAULT_RULES
    for rule, per_symbol in out.items():
        assert set(per_symbol) == {"SPY", "QQQ", "IWM"}
        for sym, series in per_symbol.items():
            assert series.index.equals(prices[sym].index), (rule, sym)
    with pytest.raises(KeyError):
        run_rules(prices, {"SPY": vols["SPY"]}, DEFAULT_RULES)
    # Catalogue sanity: slow = 4 x fast, every default rule has a fixed scalar.
    assert all(slow == 4 * fast for fast, slow in EWMAC_SPEEDS.values())
    assert set(DEFAULT_RULES) <= set(FIXED_FORECAST_SCALARS)
    assert FIXED_FORECAST_SCALARS["ewmac16_64"] == 3.75
    assert FIXED_FORECAST_SCALARS["tsmom_1_3_12"] > 0
