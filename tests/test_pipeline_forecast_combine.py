from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibtrader.pipeline.combine import combine_forecasts, equal_weights, forecast_div_multiplier
from ibtrader.pipeline.forecast import estimate_forecast_scalar, scale_and_cap
from ibtrader.pipeline.rules import ewmac, tsmom_multi
from ibtrader.pipeline.vol import price_vol_daily


def make_random_walk(n: int, seed: int, drift: float, vol: float, start: float = 100.0) -> pd.Series:
    """Geometric random walk with a business-day index; deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    rets = drift + vol * rng.standard_normal(n)
    idx = pd.bdate_range("2000-01-03", periods=n)
    return pd.Series(start * np.exp(np.cumsum(rets)), index=idx, name="close")


def _noise_frame(n: int, k: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2005-01-03", periods=n)
    return pd.DataFrame(rng.standard_normal((n, k)), index=idx, columns=[f"r{i}" for i in range(k)])


# --------------------------------------------------------------------------------------------
# forecast scalar / cap
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rule", ["ewmac16_64", "tsmom_1_3_12"])
def test_forecast_scalar_pooled_brings_abs_forecast_near_ten(rule: str) -> None:
    raws = {}
    for seed in range(8):
        px = make_random_walk(3000, 100 + seed, 0.0, 0.01)
        vol = price_vol_daily(px)
        raws[f"S{seed}"] = ewmac(px, vol, 16, 64) if rule == "ewmac16_64" else tsmom_multi(px, vol)
    scalar = estimate_forecast_scalar(raws)
    # Default is point-in-time: NaN during the warm-up, never back-filled with a future estimate.
    assert bool(scalar.iloc[:100].isna().all())
    valid = scalar.dropna()
    assert valid.index.min() > scalar.index[400]
    assert bool(scalar.loc[valid.index.min():].notna().all())
    assert (valid > 0).all()
    scaled = pd.DataFrame({sym: scale_and_cap(raw, scalar) for sym, raw in raws.items()})
    pooled_abs = float(scaled.abs().iloc[-1500:].stack().mean())
    assert 7.5 < pooled_abs < 12.5, pooled_abs
    assert float(scaled.abs().max().max()) <= 20.0


def test_forecast_scalar_known_values_and_backfill() -> None:
    idx = pd.bdate_range("2015-01-01", periods=300)
    raws = {
        "A": pd.Series(1.0, index=idx),
        "B": pd.Series(-3.0, index=idx),
        "C": pd.Series(5.0, index=idx),
    }
    # Cross-sectional median of |raw| is 3 -> scalar 10/3, constant in time.
    sc = estimate_forecast_scalar(raws, min_periods=100, backfill=True)
    assert sc.index.equals(idx)
    assert sc.notna().all()
    assert sc.iloc[0] == pytest.approx(10.0 / 3.0)
    assert sc.iloc[-1] == pytest.approx(10.0 / 3.0)

    sc_nb = estimate_forecast_scalar(raws, min_periods=100, backfill=False)
    assert sc_nb.iloc[:99].isna().all()
    assert sc_nb.iloc[99:].notna().all()
    assert sc_nb.iloc[99] == pytest.approx(10.0 / 3.0)

    # Backfill uses the first valid value (expanding mean at min_periods), not later ones.
    rng = np.random.default_rng(7)
    noisy = {"A": pd.Series(np.abs(rng.standard_normal(300)) + 0.5, index=idx)}
    sc_noisy = estimate_forecast_scalar(noisy, min_periods=100, backfill=True)
    sc_noisy_nb = estimate_forecast_scalar(noisy, min_periods=100)  # default: no backfill
    assert sc_noisy.iloc[0] == pytest.approx(float(sc_noisy_nb.iloc[99]))
    pd.testing.assert_series_equal(sc_noisy.iloc[99:], sc_noisy_nb.iloc[99:])

    # Not enough history and no backfill -> all NaN; target_abs scales linearly.
    short = {"A": pd.Series(2.0, index=idx[:50])}
    assert estimate_forecast_scalar(short, min_periods=100, backfill=False).isna().all()
    sc_t = estimate_forecast_scalar(raws, target_abs=20.0, min_periods=100)
    assert sc_t.iloc[-1] == pytest.approx(20.0 / 3.0)
    with pytest.raises(ValueError):
        estimate_forecast_scalar({})


def test_forecast_scalar_no_lookahead_and_union_index() -> None:
    a = make_random_walk(800, 21, 0.0, 0.01)
    b = make_random_walk(600, 22, 0.0, 0.01)
    raws = {"A": ewmac(a, price_vol_daily(a), 16, 64), "B": ewmac(b, price_vol_daily(b), 16, 64)}
    full = estimate_forecast_scalar(raws, min_periods=200, backfill=False)
    assert full.index.equals(a.index.union(b.index))
    cut = {k: v.iloc[:500] for k, v in raws.items()}
    trunc = estimate_forecast_scalar(cut, min_periods=200, backfill=False)
    pd.testing.assert_series_equal(full.loc[trunc.index], trunc)


def test_scale_and_cap_clips_and_aligns_series_scalar() -> None:
    idx = pd.bdate_range("2020-01-01", periods=4)
    raw = pd.Series([1.0, -30.0, 5.0, 50.0], index=idx)
    out = scale_and_cap(raw, 2.0)
    assert out.tolist() == [2.0, -20.0, 10.0, 20.0]
    out5 = scale_and_cap(raw, 2.0, cap=5.0)
    assert out5.tolist() == [2.0, -5.0, 5.0, 5.0]
    # Series scalar known only on some dates: carried forward, never backward.
    scalar = pd.Series([3.0, 1.0], index=[idx[1], idx[3]])
    out_s = scale_and_cap(raw, scalar)
    assert np.isnan(out_s.iloc[0])
    assert out_s.iloc[1] == -20.0
    assert out_s.iloc[2] == 15.0
    assert out_s.iloc[3] == 20.0
    with pytest.raises(ValueError):
        scale_and_cap(raw, 1.0, cap=0.0)


# --------------------------------------------------------------------------------------------
# FDM / combination
# --------------------------------------------------------------------------------------------


def test_equal_weights() -> None:
    assert equal_weights([]) == {}
    w = equal_weights(["a", "b", "c", "d"])
    assert set(w) == {"a", "b", "c", "d"}
    assert sum(w.values()) == pytest.approx(1.0)
    assert all(v == pytest.approx(0.25) for v in w.values())


def test_fdm_single_rule_is_one() -> None:
    f = _noise_frame(600, 3, 1)
    fdm = forecast_div_multiplier(f, {"r0": 1.0})
    assert fdm.index.equals(f.index)
    assert (fdm == 1.0).all()


def test_fdm_independent_rules_above_one_and_capped() -> None:
    f2 = _noise_frame(3000, 2, 2)
    fdm2 = forecast_div_multiplier(f2, equal_weights(list(f2.columns)))
    assert fdm2.notna().all()
    assert (fdm2 >= 1.0).all()
    assert (fdm2 <= 2.5).all()
    # Two uncorrelated rules at equal weight: 1 / sqrt(0.5) ~ 1.41.
    assert 1.3 < float(fdm2.iloc[-1]) < 1.55

    f4 = _noise_frame(3000, 4, 3)
    fdm4 = forecast_div_multiplier(f4, equal_weights(list(f4.columns)))
    assert 1.8 < float(fdm4.iloc[-1]) < 2.2
    capped = forecast_div_multiplier(f4, equal_weights(list(f4.columns)), dm_max=1.5)
    assert (capped <= 1.5).all()
    assert (capped >= 1.0).all()
    assert float(capped.iloc[-1]) == pytest.approx(1.5)


def test_fdm_identical_or_negatively_correlated_rules() -> None:
    base = _noise_frame(1500, 1, 4)["r0"]
    same = pd.DataFrame({"a": base, "b": base, "c": base})
    fdm = forecast_div_multiplier(same, equal_weights(["a", "b", "c"]))
    assert np.allclose(fdm.to_numpy(), 1.0)
    # Negative correlations are floored at corr_floor=0, so FDM equals the uncorrelated case.
    opp = pd.DataFrame({"a": base, "b": -base})
    fdm_opp = forecast_div_multiplier(opp, equal_weights(["a", "b"]))
    assert float(fdm_opp.iloc[-1]) == pytest.approx(np.sqrt(2.0), rel=1e-6)
    # Raising the floor lowers the FDM.
    fdm_floor = forecast_div_multiplier(opp, equal_weights(["a", "b"]), corr_floor=0.5)
    assert float(fdm_floor.iloc[-1]) == pytest.approx(1.0 / np.sqrt(0.75), rel=1e-6)


def test_fdm_warmup_is_one_no_nan_and_no_lookahead() -> None:
    f = _noise_frame(900, 3, 5)
    w = equal_weights(list(f.columns))
    fdm = forecast_div_multiplier(f, w, min_periods=250, step=21)
    assert fdm.notna().all()
    assert (fdm.iloc[:249] == 1.0).all()
    assert float(fdm.iloc[249]) > 1.0
    # Only weighted columns count; weights are renormalised.
    fdm_sub = forecast_div_multiplier(f, {"r0": 3.0, "r1": 3.0})
    fdm_two = forecast_div_multiplier(f[["r0", "r1"]], equal_weights(["r0", "r1"]))
    pd.testing.assert_series_equal(fdm_sub, fdm_two)
    # Truncating the history does not change earlier values.
    trunc = forecast_div_multiplier(f.iloc[:600], w, min_periods=250, step=21)
    pd.testing.assert_series_equal(fdm.iloc[:600], trunc)
    with pytest.raises(ValueError):
        forecast_div_multiplier(f, {"zzz": 1.0})
    with pytest.raises(ValueError):
        forecast_div_multiplier(f, w, dm_max=0.5)


def test_combine_respects_cap_and_renormalises_weights() -> None:
    idx = pd.bdate_range("2021-01-01", periods=5)
    f = pd.DataFrame(
        {
            "a": [15.0, 10.0, np.nan, -30.0, 4.0],
            "b": [15.0, np.nan, np.nan, -30.0, 8.0],
            "ignored": [100.0, 100.0, 100.0, 100.0, 100.0],
        },
        index=idx,
    )
    weights = {"a": 2.0, "b": 2.0}  # sums to 4 -> renormalised to 0.5 / 0.5
    out = combine_forecasts(f, weights, fdm=1.5)
    assert out.index.equals(idx)
    assert out.iloc[0] == 20.0  # 1.5 * 15 = 22.5 -> capped
    assert out.iloc[1] == pytest.approx(15.0)  # b in warm-up: weight goes fully to a
    assert np.isnan(out.iloc[2])  # no rule available
    assert out.iloc[3] == -20.0
    assert out.iloc[4] == pytest.approx(1.5 * 6.0)
    assert (combine_forecasts(f, weights, fdm=1.0).iloc[[0, 3]] == [15.0, -30.0]).tolist() == [True, False]
    assert combine_forecasts(f, weights, fdm=1.0).iloc[3] == -20.0
    assert combine_forecasts(f, weights, fdm=1.0, cap=5.0).iloc[0] == 5.0
    # Series FDM aligned forward in time.
    fdm_s = pd.Series([1.0, 2.0], index=[idx[0], idx[4]])
    out_s = combine_forecasts(f, weights, fdm=fdm_s)
    assert out_s.iloc[0] == 15.0
    assert out_s.iloc[1] == pytest.approx(10.0)
    assert out_s.iloc[4] == pytest.approx(12.0)
    with pytest.raises(ValueError):
        combine_forecasts(f, {"a": 0.0, "b": 0.0}, fdm=1.0)
    with pytest.raises(ValueError):
        combine_forecasts(f, {"nope": 1.0}, fdm=1.0)


def test_combine_matches_manual_weighted_sum_on_random_rules() -> None:
    f = _noise_frame(400, 3, 6) * 8.0
    w = {"r0": 0.5, "r1": 0.3, "r2": 0.2}
    fdm = forecast_div_multiplier(f, w, min_periods=50)
    out = combine_forecasts(f, w, fdm)
    manual = ((f["r0"] * 0.5 + f["r1"] * 0.3 + f["r2"] * 0.2) * fdm).clip(-20.0, 20.0)
    pd.testing.assert_series_equal(out, manual, check_names=False)
    assert float(out.abs().max()) <= 20.0
