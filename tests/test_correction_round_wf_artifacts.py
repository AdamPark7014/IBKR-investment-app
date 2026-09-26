from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as SN

import pandas as pd
from typer.testing import CliRunner

import ibtrader.ops.cli as cli_mod
from ibtrader.backtest.engine import BacktestResult, backtest
from ibtrader.backtest.reasons import TradeReason
from ibtrader.config import AppSettings, CommissionConfig, RiskConfig, SlippageConfig
from ibtrader.diagnostics.suspicious import diagnose
from ibtrader.ops.artifacts import save_run_artifact
from ibtrader.risk.manager import RiskManager, RiskState
from ibtrader.strategy.base import Strategy


class AlwaysLong(Strategy):
    def generate_signals(self, data):
        idx = next(iter(data.values())).index
        return {list(data.keys())[0]: pd.Series(1, index=idx, dtype=int)}


def _mk_oscillating(len_days: int = 600) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    base = pd.Series(100.0, index=idx).astype(float)
    wiggle = (pd.Series(range(len(idx)), index=idx) % 40).astype(float)
    wiggle = (wiggle - 20.0) * 0.5
    px = base + wiggle
    return pd.DataFrame(
        {"close": px, "open": px, "high": px, "low": px, "volume": 1_000.0},
        index=idx,
    )


def test_artifact_includes_exit_reason(tmp_path: Path) -> None:
    idx = pd.bdate_range("2024-05-01", periods=4)
    open_px = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx).astype(float)
    close_px = pd.Series([100.0, 90.0, 100.0, 100.0], index=idx).astype(float)
    high = open_px.combine(close_px, max)
    low = open_px.combine(close_px, min)
    df = pd.DataFrame(
        {"open": open_px, "high": high, "low": low, "close": close_px, "volume": 1000.0},
        index=idx,
    )
    rcfg = RiskConfig(
        stop_loss_per_position_pct=5.0, cooldown_bars=1, killswitch_file=str(tmp_path / "NO_KILL")
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
    s = AppSettings()
    s.resolve_paths()
    out = save_run_artifact(res, s, {"SPY": df}, str(tmp_path), "exit_reason_probe")
    art = json.loads(Path(out).read_text(encoding="utf-8"))
    assert art["trades"], "expected at least one trade in artifact"
    for tr in art["trades"]:
        assert "exit_reason" in tr
        assert tr["exit_reason"] == tr["reason"]
        assert tr["exit_reason"] in {e.value for e in TradeReason}
    assert any(tr["exit_reason"] == TradeReason.STOP_LOSS.value for tr in art["trades"])


def test_walk_forward_per_fold_metrics_and_no_single_best(monkeypatch, tmp_path):
    def fake_loader(settings):
        return {"SPY": _mk_oscillating()}

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    monkeypatch.setenv("RISK__MAX_POSITION_PCT", "100.0")
    monkeypatch.setenv("RISK__MAX_TOTAL_EXPOSURE_PCT", "100.0")
    # Point reports into tmp so artifacts are writable
    monkeypatch.setenv("DATA__REPORTS_DIR", str(tmp_path))
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["walk-forward", "--exp-id", "p9_metrics"])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    payload = json.loads(res.stdout.strip().splitlines()[-1])
    assert payload["best_params"] is None
    assert payload["in_sample"] is None
    assert payload["validation"] is None
    assert payload.get("per_fold_params")
    assert len(payload["per_fold_params"]) == len(payload["folds"])
    # Per-fold OOS must not leave trade metrics stuck at 0 when trades exist
    any_trades = False
    for fd in payload["folds"]:
        oos = fd["oos"]
        n = int(oos.get("trade_count") or 0)
        if n > 0:
            any_trades = True
            assert float(oos.get("total_commission") or 0) > 0 or float(oos.get("commission") or 0) > 0
            assert float(oos.get("turnover") or 0) > 0
            assert len(fd["oos_trades"]) == n
            for tr in fd["oos_trades"]:
                assert "exit_reason" in tr
    assert any_trades, "fixture should produce OOS trades in at least one fold"
    # Stitched OOS must carry commission
    assert payload.get("oos_commission_approx", 0) > 0
    assert payload["oos"].get("total_commission") or payload["oos"].get("commission")
    # Artifact must not be a shell
    art_path = payload["artifact"]
    assert os.path.exists(art_path)
    art = json.loads(Path(art_path).read_text(encoding="utf-8"))
    assert len(art.get("trades") or []) > 0
    assert len(art.get("equity_curve") or []) > 0
    assert str(art.get("strategy_version", "")).startswith("sma_wf_multi")
    assert all("exit_reason" in t for t in art["trades"])


def test_walk_forward_flat_equity_emits_null_sharpe(monkeypatch):
    # Constant prices → flat equity → Sharpe must serialize as JSON null, not 0.0
    def fake_loader(settings):
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        idx = pd.bdate_range(end=today, periods=300)
        px = pd.Series(100.0, index=idx)
        return {
            "SPY": pd.DataFrame(
                {"close": px, "open": px, "high": px, "low": px, "volume": 1000.0},
                index=idx,
            )
        }

    monkeypatch.setattr(cli_mod, "load_universe_v2", fake_loader)
    runner = CliRunner()
    res = runner.invoke(cli_mod.app, ["walk-forward", "--exp-id", "flat_null"])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    payload = json.loads(res.stdout.strip().splitlines()[-1])
    oos = payload.get("oos") or {}
    # Flat stitched OOS (if present) must not claim sharpe == 0.0; null is correct
    if "sharpe" in oos:
        assert oos["sharpe"] is None


def test_turnover_diagnostic_spares_normal_sma_churn() -> None:
    # Normal SMA-like: ~40 trades, turnover ~30 over ~2y → must NOT flag
    idx = pd.bdate_range("2022-01-01", periods=504)
    eq = pd.Series(100_000.0, index=idx) * (1.0 + pd.Series(range(len(idx)), index=idx) * 0.0001)
    ret = eq.pct_change().fillna(0.0)
    stats = SN(
        cagr=0.05,
        sharpe=0.5,
        sortino=0.5,
        max_drawdown=-0.1,
        win_rate=0.5,
        exposure=0.6,
        total_return=0.1,
        volatility=0.15,
        trade_count=40,
        total_commission=50.0,
        turnover=30.0,
        win_rate_trades=0.5,
        profit_factor=1.2,
        expectancy=10.0,
        var_95=-0.01,
        cvar_95=-0.02,
        current_underwater_days=0,
        max_underwater_days=5,
    )
    res = BacktestResult(equity_curve=eq, returns=ret, positions={}, trades=[], stats=stats)
    data = {"SPY": pd.DataFrame({"close": eq / 1000.0}, index=idx)}
    codes = {f.code for f in diagnose(res, data)}
    assert "anomalous_turnover" not in codes


def test_turnover_diagnostic_flags_inconsistent_pathology() -> None:
    idx = pd.bdate_range("2023-01-01", periods=252)
    eq = pd.Series(100_000.0, index=idx)
    ret = eq.pct_change().fillna(0.0)
    stats = SN(
        cagr=0.0,
        sharpe=0.0,
        sortino=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        exposure=1.0,
        total_return=0.0,
        volatility=0.0,
        trade_count=2,
        total_commission=1.0,
        turnover=100.0,  # absurd vs 2 trades in 1y
        win_rate_trades=0.0,
        profit_factor=0.0,
        expectancy=0.0,
        var_95=0.0,
        cvar_95=0.0,
        current_underwater_days=0,
        max_underwater_days=0,
    )
    res = BacktestResult(equity_curve=eq, returns=ret, positions={}, trades=[], stats=stats)
    data = {"SPY": pd.DataFrame({"close": [100.0] * len(idx)}, index=idx)}
    codes = {f.code for f in diagnose(res, data)}
    assert "anomalous_turnover" in codes
