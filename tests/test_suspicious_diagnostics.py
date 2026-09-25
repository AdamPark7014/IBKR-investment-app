from __future__ import annotations

from types import SimpleNamespace as SN

import pandas as pd

from ibtrader.backtest.engine import BacktestResult
from ibtrader.diagnostics.suspicious import diagnose


def test_suspicious_flags_detect_extremes() -> None:
    # Minimal fake BacktestResult with extreme stats
    eq = pd.Series([100000.0, 300000.0], index=pd.to_datetime(["2024-01-01", "2024-12-31"]))
    ret = eq.pct_change().fillna(0.0)
    stats = SN(
        cagr=2.5,
        sharpe=5.0,
        sortino=0.0,
        max_drawdown=-0.1,
        win_rate=1.0,
        exposure=1.0,
        total_return=eq.iloc[-1] / eq.iloc[0] - 1.0,
        volatility=0.5,
        trade_count=10,
        total_commission=0.0,
        turnover=25.0,
        win_rate_trades=1.0,
        profit_factor=5.0,
        expectancy=100.0,
        var_95=0.0,
        cvar_95=0.0,
        current_underwater_days=0,
        max_underwater_days=0,
    )
    res = BacktestResult(equity_curve=eq, returns=ret, positions={}, trades=[], stats=stats)
    data = {
        "SPY": pd.DataFrame(
            {"close": [1.0, 2.0]},
            index=pd.to_datetime(["2024-01-01", "2024-12-31"]),
        )
    }
    flags = diagnose(res, data, lineage_sources={"SPY": "fixture"})
    codes = {f.code for f in flags}
    assert "extreme_cagr" in codes
    assert "extreme_sharpe" in codes
    assert "zero_costs" in codes
    assert "synthetic_source" in codes
    assert "anomalous_turnover" in codes


def test_fill_at_signal_price_detected() -> None:
    # Dataset with two days; a trade priced exactly at previous close should flag
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    df = pd.DataFrame({"close": [100.0, 101.0]}, index=idx)
    from types import SimpleNamespace as SN
    stats = SN(
        cagr=0.0,
        sharpe=0.0,
        sortino=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        exposure=0.0,
        total_return=0.0,
        volatility=0.0,
        trade_count=1,
        total_commission=1.0,
        turnover=0.0,
        win_rate_trades=0.0,
        profit_factor=0.0,
        expectancy=0.0,
        var_95=0.0,
        cvar_95=0.0,
        current_underwater_days=0,
        max_underwater_days=0,
    )
    # Trade at 2024-01-03 executed at exactly prior close (100.0)
    res = BacktestResult(
        equity_curve=df["close"].rename("eq"),
        returns=df["close"].pct_change().fillna(0.0),
        positions={},
        trades=[("2024-01-03", "SPY", 10, 100.0, "signal")],
        stats=stats,
    )
    flags = diagnose(res, {"SPY": df}, lineage_sources=None)
    codes = {f.code for f in flags}
    assert "fill_at_signal_price" in codes
