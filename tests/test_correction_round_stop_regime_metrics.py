from __future__ import annotations

import math

import pandas as pd

from ibtrader.backtest.engine import backtest
from ibtrader.backtest.metrics import compute_stats
from ibtrader.backtest.reasons import TradeReason
from ibtrader.config import CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        return {list(data.keys())[0]: pd.Series(1, index=idx, dtype=int)}


def test_stoploss_long_triggers_exactly_at_threshold() -> None:
    # entry ~100, stop 2% → thresh 98; close 98 schedules; exit next open
    idx = pd.bdate_range("2024-07-01", periods=4)
    open_px = pd.Series([100.0, 100.0, 97.0, 100.0], index=idx).astype(float)
    close_px = pd.Series([100.0, 98.0, 97.0, 100.0], index=idx).astype(float)
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame(
        {"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0},
        index=idx,
    )
    rcfg = RiskConfig(
        stop_loss_per_position_pct=2.0, cooldown_bars=1, killswitch_file="./data/NO_KILL"
    )
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    assert any(reason == TradeReason.STOP_LOSS.value for *_, reason in res.trades)


def test_stoploss_long_no_trigger_just_above_threshold() -> None:
    # close 98.1 with 2% stop from 100 → must NOT schedule stop
    idx = pd.bdate_range("2024-07-01", periods=4)
    open_px = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    close_px = pd.Series([100.0, 98.1, 100.0, 100.0], index=idx).astype(float)
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame(
        {"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0},
        index=idx,
    )
    rcfg = RiskConfig(
        stop_loss_per_position_pct=2.0, cooldown_bars=1, killswitch_file="./data/NO_KILL"
    )
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )
    assert all(reason != TradeReason.STOP_LOSS.value for *_, reason in res.trades)


def test_stoploss_gap_fills_at_next_open_not_stop_price() -> None:
    # Close breaches stop (98); next open gaps to 95 → fill at open (worse), reason stop_loss
    idx = pd.bdate_range("2024-08-01", periods=4)
    open_px = pd.Series([100.0, 100.0, 95.0, 100.0], index=idx).astype(float)
    close_px = pd.Series([100.0, 98.0, 95.0, 100.0], index=idx).astype(float)
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame(
        {"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0},
        index=idx,
    )
    rcfg = RiskConfig(
        stop_loss_per_position_pct=2.0, cooldown_bars=1, killswitch_file="./data/NO_KILL"
    )
    rm = RiskManager(rcfg, RiskState(starting_equity_today=100_000.0))
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(bps=0.0),
        direction="long_only",
        risk_manager=rm,
    )
    stop_fills = [(q, p, r) for _, _, q, p, r in res.trades if r == TradeReason.STOP_LOSS.value]
    assert stop_fills, "expected stop_loss fill after close breach"
    # Sell fill should be at gapped open (~95), not magically at stop 98
    _, fill_px, _ = stop_fills[0]
    assert fill_px <= 95.01


def test_regime_nan_warmup_blocks_entries() -> None:
    idx = pd.bdate_range("2024-01-01", periods=5)
    px = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=idx)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}, index=idx
    )
    risk_on = pd.Series([float("nan")] * len(idx), index=idx)
    res = backtest(
        {"SPY": df},
        AlwaysLong(),
        CommissionConfig(),
        SlippageConfig(),
        direction="long_only",
        risk_on=risk_on,
        risk_on_threshold=0.5,
    )
    # Warm-up NaN ⇒ neutral/flat ⇒ no exposure-increasing fills
    assert len(res.trades) == 0
    assert (res.positions["SPY"].fillna(0) == 0).all()


def test_flat_equity_sharpe_is_nan_not_zero() -> None:
    idx = pd.bdate_range("2024-01-01", periods=10)
    eq = pd.Series(100_000.0, index=idx)
    rets = eq.pct_change().fillna(0.0)
    stats = compute_stats(eq, rets)
    assert math.isnan(stats.sharpe)
    assert math.isnan(stats.sortino)
