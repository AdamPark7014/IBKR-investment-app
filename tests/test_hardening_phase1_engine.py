"""Hardening phase 1 (engine side): per-bar risk lockout flags, fail-closed
``update_equity`` and the 20% drawdown default."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import ibtrader.risk.manager as manager_mod
from ibtrader.backtest.engine import backtest, restricted_counts
from ibtrader.config import AppSettings, CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy

NO_KILL = "./data/NO_KILL"


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        return {sym: pd.Series(1, index=df.index, dtype=int) for sym, df in data.items()}


class NeverTrade(Strategy):
    def generate_signals(self, data):
        return {sym: pd.Series(0, index=df.index, dtype=int) for sym, df in data.items()}


def _ohlc(px: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px, "volume": 1_000.0},
        index=px.index,
    )


def _uptrend(n: int = 30) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=n)
    return {"SPY": _ohlc(pd.Series(100.0 + np.arange(n, dtype=float), index=idx))}


def _downtrend(n: int = 30) -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=n)
    return {"SPY": _ohlc(pd.Series(100.0 - np.arange(n, dtype=float), index=idx))}


def _wf_data(len_days: int = 300) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    vals = [100.0]
    for i in range(1, len(idx)):
        vals.append(vals[-1] * (1.0 + (0.002 if (i % 20) < 10 else -0.002)))
    return _ohlc(pd.Series(vals, index=idx).astype(float))


def _run(data, strategy, rm: RiskManager | None):
    return backtest(
        data=data,
        strategy=strategy,
        commission_cfg=CommissionConfig(),
        slippage_cfg=SlippageConfig(),
        direction="long_only",
        risk_manager=rm,
    )


# (a) ------------------------------------------------------------------------
def test_restricted_without_risk_manager_is_all_false() -> None:
    res = _run(_uptrend(), AlwaysLong(), None)
    assert hasattr(res, "restricted")
    assert res.restricted.dtype == bool
    assert res.restricted.index.equals(res.equity_curve.index)
    assert len(res.restricted) == len(res.equity_curve) == 30
    assert not res.restricted.any()
    assert restricted_counts(res) == (0, 30)


# (b) ------------------------------------------------------------------------
def test_tiny_daily_loss_limit_produces_restricted_bars() -> None:
    rm = RiskManager(
        RiskConfig(daily_loss_limit_pct=0.01, killswitch_file=NO_KILL),
        RiskState(starting_equity_today=100_000.0),
    )
    res = _run(_downtrend(), AlwaysLong(), rm)
    assert res.restricted.dtype == bool
    assert res.restricted.index.equals(res.equity_curve.index)
    restricted, total = restricted_counts(res)
    assert total == len(res.equity_curve)
    assert 0 < restricted <= total
    # Every bar that follows a losing close must be locked out
    losing_close = res.returns < -0.0001
    following = losing_close.shift(1, fill_value=False).astype(bool)
    assert res.restricted[following].all()


def test_restricted_is_deterministic_and_does_not_change_fills() -> None:
    cfg = RiskConfig(daily_loss_limit_pct=0.5, killswitch_file=NO_KILL)
    r1 = _run(_downtrend(), AlwaysLong(), RiskManager(cfg, RiskState(starting_equity_today=100_000.0)))
    r2 = _run(_downtrend(), AlwaysLong(), RiskManager(cfg, RiskState(starting_equity_today=100_000.0)))
    assert list(r1.restricted.values) == list(r2.restricted.values)
    assert list(r1.equity_curve.values) == list(r2.equity_curve.values)
    assert r1.trades == r2.trades


# (c) ------------------------------------------------------------------------
def test_restricted_counts_with_window() -> None:
    res = _run(_uptrend(10), AlwaysLong(), None)
    idx = res.equity_curve.index
    flags = [False, True, True, False, False, True, False, False, False, False]
    res.restricted = pd.Series(flags, index=idx, dtype=bool)

    assert restricted_counts(res) == (3, 10)
    # Inclusive (start, end) tuple
    assert restricted_counts(res, (idx[1], idx[2])) == (2, 2)
    assert restricted_counts(res, (idx[3], idx[5])) == (1, 3)
    # Open-ended tuple and label slice
    assert restricted_counts(res, (None, idx[2])) == (2, 3)
    assert restricted_counts(res, slice(idx[5], None)) == (1, 5)
    assert restricted_counts(res, slice(idx[3], idx[4])) == (0, 2)
    # Window outside the series -> nothing selected
    beyond = idx[-1] + pd.Timedelta(days=10)
    assert restricted_counts(res, (beyond, beyond + pd.Timedelta(days=5))) == (0, 0)
    # String labels work the same as Timestamps
    assert restricted_counts(res, (str(idx[1].date()), str(idx[2].date()))) == (2, 2)


def test_restricted_counts_empty_series() -> None:
    res = _run(_uptrend(5), AlwaysLong(), None)
    res.restricted = pd.Series(dtype=bool)
    assert restricted_counts(res) == (0, 0)


# (d) ------------------------------------------------------------------------
def test_probe_exception_marks_bar_restricted(monkeypatch) -> None:
    rm = RiskManager(RiskConfig(killswitch_file=NO_KILL), RiskState(starting_equity_today=100_000.0))

    def _boom(self):
        raise RuntimeError("simulated killswitch probe failure")

    monkeypatch.setattr(RiskManager, "killswitch_active", _boom)
    res = _run(_uptrend(12), NeverTrade(), rm)
    assert res.restricted.dtype == bool
    assert res.restricted.all()
    assert restricted_counts(res) == (12, 12)


def test_killswitch_active_marks_every_bar_restricted(monkeypatch) -> None:
    rm = RiskManager(RiskConfig(killswitch_file=NO_KILL), RiskState(starting_equity_today=100_000.0))
    monkeypatch.setattr(rm, "killswitch_active", lambda: True)
    res = _run(_uptrend(8), AlwaysLong(), rm)
    assert res.restricted.all()
    assert len(res.trades) == 0


# (e) ------------------------------------------------------------------------
def test_walk_forward_reports_restricted_bar_frac() -> None:
    from ibtrader.validation.walkforward import walk_forward_sma

    settings = AppSettings()
    wf, summary = walk_forward_sma(
        settings,
        {"SPY": _wf_data()},
        "SPY",
        param_grid=[(5, 20)],
        n_folds=2,
        warmup_bars=40,
    )
    stitched = wf.stitched_oos
    assert "restricted_bar_frac" in stitched
    assert 0.0 <= float(stitched["restricted_bar_frac"]) <= 1.0
    for fd in wf.per_fold:
        frac = fd["oos"]["restricted_bar_frac"]
        assert 0.0 <= float(frac) <= 1.0
    assert 0.0 <= float(summary["restricted_bar_frac"]) <= 1.0
    assert summary["oos_total_bars"] == sum(len(fd["oos_equity"]) for fd in wf.per_fold)
    assert 0 <= summary["oos_restricted_bars"] <= summary["oos_total_bars"]


def test_research_runners_report_restricted_bar_frac() -> None:
    from ibtrader.research.tsmom_runner import run_tsmom_research

    settings = AppSettings()
    rows = run_tsmom_research(settings, {"SPY": _wf_data()}, "SPY", lookbacks=[21], n_folds=2)
    assert len(rows) == 1
    frac = rows[0]["oos"]["restricted_bar_frac"]
    assert 0.0 <= float(frac) <= 1.0


# (f) ------------------------------------------------------------------------
def test_update_equity_exception_halts_next_day(caplog) -> None:
    rm = RiskManager(
        RiskConfig(daily_loss_limit_pct=5.0, max_position_pct=100.0, killswitch_file=NO_KILL),
        RiskState(starting_equity_today=100_000.0),
    )
    rm.on_new_day("2024-01-01", 100_000.0)
    assert rm.state.halt_next_day is False
    # Corrupt the day's starting equity so the close-time check raises (TypeError)
    rm.state.starting_equity_today = None  # type: ignore[assignment]
    mgr_log = logging.getLogger(manager_mod.__name__)
    mgr_log.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=manager_mod.__name__):
            rm.update_equity(100_500.0)  # a winning close, still fail-closed
    finally:
        mgr_log.removeHandler(caplog.handler)
    assert rm.state.halt_next_day is True
    assert any(
        r.levelno >= logging.ERROR and "risk_fail_closed" in r.getMessage() for r in caplog.records
    )

    # Next day: consumed into halted -> opens rejected, reductions allowed
    rm.on_new_day("2024-01-02", 100_500.0)
    assert rm.state.halted is True
    assert rm.state.halt_next_day is False
    ok, _ = rm.approve_order(
        symbol="SPY",
        equity=100_500.0,
        price=100.0,
        quantity=10,
        current_positions_value=0.0,
        current_position_qty=0,
    )
    assert not ok
    ok, _ = rm.approve_order(
        symbol="SPY",
        equity=100_500.0,
        price=100.0,
        quantity=-10,
        current_positions_value=50_000.0,
        current_position_qty=100,
    )
    assert ok

    # The day after, trading resumes normally
    rm.on_new_day("2024-01-03", 100_500.0)
    assert rm.state.halted is False
    ok, _ = rm.approve_order(
        symbol="SPY",
        equity=100_500.0,
        price=100.0,
        quantity=10,
        current_positions_value=0.0,
        current_position_qty=0,
    )
    assert ok


def test_update_equity_still_detects_real_breach() -> None:
    rm = RiskManager(
        RiskConfig(daily_loss_limit_pct=5.0, killswitch_file=NO_KILL),
        RiskState(starting_equity_today=100_000.0),
    )
    rm.on_new_day("2024-01-01", 100_000.0)
    rm.update_equity(96_000.0)
    assert rm.state.halt_next_day is False
    rm.update_equity(94_000.0)
    assert rm.state.halt_next_day is True


# (g) ------------------------------------------------------------------------
def test_drawdown_default_is_20_pct() -> None:
    assert RiskConfig().drawdown_limit_pct == 20.0
    assert AppSettings().risk.drawdown_limit_pct == 20.0
