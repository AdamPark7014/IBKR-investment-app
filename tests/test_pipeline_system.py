"""Phase-2 stage graph: ``pipeline.system.run_system`` and ``strategy.pipeline_strategy``.

Deterministic synthetic universe (6 random walks with boxes, ~1 500 business days,
``numpy.random.default_rng``), no network, no cache.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import pytest

from ibtrader.backtest.engine import backtest
from ibtrader.config import AppSettings
from ibtrader.pipeline.system import SystemConfig, SystemOutput, run_system
from ibtrader.strategy.pipeline_strategy import PipelineStrategy

# symbol: (box, annual drift, annual vol)
SYNTH: Dict[str, Tuple[str, float, float]] = {
    "SPY": ("us_equity", 0.08, 0.16),
    "IEF": ("treasuries_intermediate", 0.03, 0.06),
    "TLT": ("treasuries_long", 0.03, 0.14),
    "GLD": ("gold", 0.05, 0.15),
    "PDBC": ("commodities", 0.02, 0.18),
    "VNQ": ("reit", 0.06, 0.20),
}
BOXES: Dict[str, str] = {sym: spec[0] for sym, spec in SYNTH.items()}
EWMAC_ONLY: Tuple[str, ...] = ("ewmac16_64", "ewmac32_128", "ewmac64_256")


def make_synthetic(n_days: int = 1500, seed: int = 7, end: Optional[pd.Timestamp] = None) -> Dict[str, pd.DataFrame]:
    """Six OHLCV random walks (open = previous close, constant volume) ending today (UTC)."""
    rng = np.random.default_rng(seed)
    last = end if end is not None else pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=last, periods=n_days)
    data: Dict[str, pd.DataFrame] = {}
    for sym, (_box, mu, sigma) in SYNTH.items():
        rets = rng.normal(mu / 252.0, sigma / np.sqrt(252.0), size=n_days)
        close = pd.Series(100.0 * np.cumprod(1.0 + rets), index=idx)
        open_ = close.shift(1).fillna(close.iloc[0])
        high = np.maximum(open_, close) * 1.001
        low = np.minimum(open_, close) * 0.999
        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": 1_000_000.0},
            index=idx,
        )
        df.index.name = "date"
        data[sym] = df
    return data


def closes(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({sym: df["close"] for sym, df in data.items()}).sort_index()


@pytest.fixture(scope="module")
def synthetic() -> Dict[str, pd.DataFrame]:
    return make_synthetic()


@pytest.fixture(scope="module")
def base_output(synthetic: Dict[str, pd.DataFrame]) -> SystemOutput:
    return run_system(closes(synthetic), SystemConfig(boxes=BOXES))


def _valid_rows(out: SystemOutput) -> pd.DataFrame:
    assert out.warmup_end is not None
    return out.target_weights.loc[out.warmup_end :].dropna(how="all")


# --------------------------------------------------------------------------- run_system


def test_run_system_returns_every_stage_aligned(synthetic: Dict[str, pd.DataFrame], base_output: SystemOutput) -> None:
    out = base_output
    px = closes(synthetic)
    symbols = list(px.columns)
    frames = {
        "prices": out.prices,
        "vol_price": out.vol_price,
        "pct_vol": out.pct_vol,
        "fdm": out.fdm,
        "combined_forecast": out.combined_forecast,
        "vol_scalar": out.vol_scalar,
        "subsystem_positions": out.subsystem_positions,
        "instrument_weights": out.instrument_weights,
        "positions": out.positions,
        "buffered_positions": out.buffered_positions,
        "target_weights": out.target_weights,
        "mtm_weights": out.mtm_weights,
        "subsystem_returns": out.subsystem_returns,
    }
    for name, frame in frames.items():
        assert isinstance(frame, pd.DataFrame), name
        assert frame.index.equals(px.index), f"{name}: index not aligned with prices"
        assert list(frame.columns) == symbols, f"{name}: columns {list(frame.columns)}"
    assert set(out.raw_forecasts) == set(out.config.rules) if out.config else True
    assert set(out.scaled_forecasts) == set(out.raw_forecasts)
    assert set(out.forecast_scalars) == set(out.raw_forecasts)
    for rule, frame in out.raw_forecasts.items():
        assert frame.index.equals(px.index), rule
        assert out.scaled_forecasts[rule].index.equals(px.index), rule
        assert out.forecast_scalars[rule].index.equals(px.index), rule
        # scaled forecasts honour the cap
        assert float(out.scaled_forecasts[rule].abs().max().max()) <= 20.0 + 1e-9, rule
    assert isinstance(out.idm, pd.Series) and out.idm.index.equals(px.index)
    assert float(out.combined_forecast.abs().max().max()) <= 20.0 + 1e-9


def test_warmup_end_is_defined_and_inside_sample(base_output: SystemOutput) -> None:
    out = base_output
    assert out.warmup_end is not None
    assert out.prices.index[0] < out.warmup_end <= out.prices.index[-1]
    # From warmup_end on, every stage has a value for at least two symbols.
    after = out.target_weights.loc[out.warmup_end :]
    assert int(after.notna().sum(axis=1).iloc[0]) >= 2
    assert bool(out.idm.loc[out.warmup_end :].notna().all())
    # And at least a few months of out-of-sample bars remain.
    assert len(after) >= 120


def test_target_weights_within_leverage_bounds(base_output: SystemOutput) -> None:
    out = base_output
    cfg = out.config
    assert cfg is not None
    w = _valid_rows(out)
    assert not w.empty
    assert float(w.min().min()) >= 0.0 - 1e-12
    assert float(w.max().max()) <= cfg.max_leverage + 1e-9
    gross = w.abs().sum(axis=1)
    assert float(gross.max()) <= cfg.max_leverage + 1e-9
    # The system actually takes positions (not a degenerate all-zero output).
    assert float(gross.max()) > 0.0


def test_long_only_has_no_negative_weights(synthetic: Dict[str, pd.DataFrame]) -> None:
    out = run_system(closes(synthetic), SystemConfig(boxes=BOXES, long_only=True, max_leverage=1.0))
    w = _valid_rows(out)
    assert float(w.min().min()) >= 0.0
    assert float(out.positions.loc[out.warmup_end :].min().min()) >= 0.0


def test_no_lookahead_fixed_scalars(synthetic: Dict[str, pd.DataFrame]) -> None:
    """Running on prices cut at ``t`` reproduces every value up to ``t`` (fixed scalars → fully PIT)."""
    px = closes(synthetic)
    cfg = SystemConfig(rules=EWMAC_ONLY, forecast_scalar_mode="fixed", boxes=BOXES)
    full = run_system(px, cfg)
    t = px.index[1150]
    cut = run_system(px.loc[:t], cfg)
    assert cut.warmup_end == full.warmup_end
    for name in ("vol_price", "combined_forecast", "subsystem_positions", "instrument_weights", "positions",
                 "buffered_positions", "target_weights"):
        a = getattr(full, name).loc[:t]
        b = getattr(cut, name)
        pd.testing.assert_frame_equal(a, b, check_exact=False, atol=1e-9, rtol=1e-7, obj=name)
    pd.testing.assert_series_equal(full.idm.loc[:t], cut.idm, check_exact=False, atol=1e-9, rtol=1e-7)


@pytest.mark.parametrize("weighting", ["box_risk_parity", "hrp"])
def test_no_lookahead_estimate_mode_end_to_end(synthetic: Dict[str, pd.DataFrame], weighting: str) -> None:
    """``estimate`` mode is point-in-time through every stage: the scalar is never back-filled."""
    px = closes(synthetic)
    cfg = SystemConfig(boxes=BOXES, instrument_weighting=weighting)  # type: ignore[arg-type]
    full = run_system(px, cfg)
    t = px.index[1100]
    cut = run_system(px.loc[:t], cfg)
    assert cut.warmup_end == full.warmup_end
    for rule in cfg.rules:
        pd.testing.assert_frame_equal(
            full.raw_forecasts[rule].loc[:t], cut.raw_forecasts[rule], check_exact=False, atol=1e-9, rtol=1e-7, obj=rule
        )
        pd.testing.assert_series_equal(
            full.forecast_scalars[rule].loc[:t], cut.forecast_scalars[rule], check_exact=False, atol=1e-9, rtol=1e-7
        )
        pd.testing.assert_frame_equal(
            full.scaled_forecasts[rule].loc[:t], cut.scaled_forecasts[rule], check_exact=False, atol=1e-9, rtol=1e-7
        )
    for name in ("vol_price", "pct_vol", "fdm", "combined_forecast", "subsystem_positions", "instrument_weights",
                 "positions", "buffered_positions", "target_weights"):
        pd.testing.assert_frame_equal(
            getattr(full, name).loc[:t], getattr(cut, name), check_exact=False, atol=1e-9, rtol=1e-7, obj=name
        )
    pd.testing.assert_series_equal(full.idm.loc[:t], cut.idm, check_exact=False, atol=1e-9, rtol=1e-7)


def test_warmup_end_waits_for_a_point_in_time_scalar(base_output: SystemOutput) -> None:
    """No back-fill: before ``scalar_min_periods`` the scalar is NaN and nothing is traded on it."""
    out = base_output
    cfg = out.config
    assert cfg is not None and cfg.forecast_scalar_mode == "estimate"
    assert out.warmup_end is not None
    firsts = [pd.Timestamp(s.first_valid_index()) for s in out.forecast_scalars.values()]
    for rule, scalar in out.forecast_scalars.items():
        assert bool(scalar.iloc[: cfg.scalar_min_periods - 1].isna().all()), rule
    # Every rule must have a real (not back-filled) scalar before the evaluated window opens...
    assert out.warmup_end >= max(firsts)
    # ...and nothing is sized before the first scalar of any rule exists.
    before = out.target_weights.loc[: min(firsts)].iloc[:-1]
    assert float(before.fillna(0.0).abs().max().max()) == 0.0
    assert bool(out.combined_forecast.loc[: min(firsts)].iloc[:-1].isna().all().all())


@pytest.mark.parametrize("weighting", ["box_risk_parity", "hrp"])
def test_instrument_risk_shares_are_not_inverse_vol(synthetic: Dict[str, pd.DataFrame], weighting: str) -> None:
    """Subsystems are already vol-normalised: the instrument weight is the risk share, not ``1/σ`` of it.

    Risk of the average position (forecast 10) = ``|avg position| · price · pct_vol``; with the old
    box inverse-vol weights IEF (6 % vol) carried ~35 % of the risk and VNQ (20 %) ~11 %; HRP on raw
    returns gave IEF ~58 %. Six boxes → 1/6 each.
    """
    from ibtrader.pipeline.portfolio_stage import average_abs_positions

    px = closes(synthetic)
    out = run_system(px, SystemConfig(boxes=BOXES, instrument_weighting=weighting))  # type: ignore[arg-type]
    assert out.warmup_end is not None
    avg_abs = average_abs_positions(out.vol_scalar, out.instrument_weights, out.idm)
    risk = (avg_abs * out.prices * out.pct_vol).loc[out.warmup_end :].dropna(how="any")
    assert not risk.empty
    shares = risk.div(risk.sum(axis=1), axis=0)
    if weighting == "box_risk_parity":
        assert np.allclose(shares.to_numpy(), 1.0 / 6.0, atol=1e-9)
    else:
        mean_share = shares.mean()
        assert float(mean_share.max()) < 0.30, mean_share.to_dict()
        assert float(mean_share.min()) > 0.08, mean_share.to_dict()
        # Lowest-vol and highest-vol instruments carry comparable risk.
        assert abs(float(mean_share["IEF"]) - float(mean_share["VNQ"])) < 0.12, mean_share.to_dict()


def test_legacy_box_inverse_vol_name_maps_to_box_risk_parity() -> None:
    cfg = SystemConfig(instrument_weighting="box_inverse_vol")  # type: ignore[arg-type]
    assert cfg.instrument_weighting == "box_risk_parity"
    with pytest.raises(ValueError):
        SystemConfig(instrument_weighting="nope")  # type: ignore[arg-type]


def test_target_weights_only_move_when_buffered_position_moves(base_output: SystemOutput) -> None:
    out = base_output
    start = out.warmup_end
    w = out.target_weights.loc[start:].fillna(0.0)
    pos = out.buffered_positions.loc[start:].fillna(0.0)
    w_moved = (w.diff().abs() > 1e-12).any(axis=1).iloc[1:]
    pos_moved = (pos.diff().abs() > 1e-12).any(axis=1).iloc[1:]
    # A weight change without any position change would mean trading on price drift.
    assert not bool((w_moved & ~pos_moved).any())
    # And the weights do move at some point (the system rebalances).
    assert bool(w_moved.any())


def test_fixed_and_estimate_scalar_modes_both_run(synthetic: Dict[str, pd.DataFrame]) -> None:
    px = closes(synthetic)
    est = run_system(px, SystemConfig(rules=EWMAC_ONLY, forecast_scalar_mode="estimate", boxes=BOXES))
    fix = run_system(px, SystemConfig(rules=EWMAC_ONLY, forecast_scalar_mode="fixed", boxes=BOXES))
    assert est.warmup_end is not None and fix.warmup_end is not None
    assert all(v == "estimate" for v in est.scalar_source.values())
    assert all(v == "fixed" for v in fix.scalar_source.values())
    for rule in EWMAC_ONLY:
        fixed_scalar = fix.forecast_scalars[rule].dropna()
        assert fixed_scalar.nunique() == 1, rule
        assert float(fixed_scalar.iloc[0]) > 0.0
        assert est.forecast_scalars[rule].dropna().gt(0.0).all(), rule
    for out in (est, fix):
        assert np.isfinite(_valid_rows(out).to_numpy()).all()


@pytest.mark.parametrize("weighting", ["hrp", "equal"])
def test_instrument_weighting_variants_run(synthetic: Dict[str, pd.DataFrame], weighting: str) -> None:
    px = closes(synthetic)
    out = run_system(px, SystemConfig(boxes=BOXES, instrument_weighting=weighting))  # type: ignore[arg-type]
    assert out.warmup_end is not None
    iw = out.instrument_weights.loc[out.warmup_end :].dropna(how="all")
    assert not iw.empty
    assert float(iw.min().min()) >= -1e-9
    row_sums = iw.sum(axis=1)
    assert np.allclose(row_sums.to_numpy(), 1.0, atol=1e-6)
    if weighting == "equal":
        assert np.allclose(iw.to_numpy(), 1.0 / px.shape[1], atol=1e-9)
    w = _valid_rows(out)
    assert float(w.abs().sum(axis=1).max()) <= 1.0 + 1e-9


def test_system_config_validation() -> None:
    with pytest.raises(ValueError):
        SystemConfig(rules=())
    with pytest.raises(ValueError):
        SystemConfig(rules=EWMAC_ONLY, rule_weights={"ewmac16_64": 1.0})
    with pytest.raises(ValueError):
        SystemConfig(tau=0.0)
    with pytest.raises(ValueError):
        SystemConfig(max_leverage=0.0)
    cfg = SystemConfig(rules=EWMAC_ONLY, rule_weights={r: 1.0 / 3.0 for r in EWMAC_ONLY})
    assert abs(sum(cfg.forecast_weights().values()) - 1.0) < 1e-12
    assert abs(sum(SystemConfig().forecast_weights().values()) - 1.0) < 1e-9


# --------------------------------------------------------------------------- PipelineStrategy + engine


def test_pipeline_strategy_signals_and_engine_weight_mode(synthetic: Dict[str, pd.DataFrame]) -> None:
    strat = PipelineStrategy(SystemConfig(boxes=BOXES))
    assert strat.signal_kind == "weight"
    signals = strat.generate_signals(synthetic)
    assert set(signals) == set(synthetic)
    out = strat.last_output
    assert out is not None and out.warmup_end is not None
    for sym, s in signals.items():
        assert s.index.equals(synthetic[sym].index), sym
        assert not s.isna().any(), sym
        assert float(s.min()) >= 0.0, sym
        assert float(s.loc[: out.warmup_end].iloc[:-1].abs().max()) == 0.0, f"{sym}: exposure before warm-up"
    gross = pd.DataFrame(signals).abs().sum(axis=1)
    assert float(gross.max()) <= 1.0 + 1e-9

    s = AppSettings()
    s.risk.killswitch_file = "./tests/__no_kill_switch__"
    res = backtest(
        data=synthetic,
        strategy=strat,
        commission_cfg=s.commission,
        slippage_cfg=s.slippage,
        initial_equity=100_000.0,
        direction="long_only",
        reg_fees_cfg=s.reg_fees,
    )
    assert isinstance(res.restricted, pd.Series)
    assert res.restricted.index.equals(res.equity_curve.index)
    assert len(res.trades) > 0
    first_trade = pd.Timestamp(res.trades[0][0])
    assert first_trade > out.warmup_end
    assert all(int(t[2]) != 0 for t in res.trades)
    # Long-only: never a short position.
    assert all(int(p.min()) >= 0 for p in res.positions.values())
    assert res.stats.trade_count == len(res.trades)
    assert np.isfinite(res.equity_curve.to_numpy()).all()
