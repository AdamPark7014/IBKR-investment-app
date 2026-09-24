from __future__ import annotations

import pandas as pd
from types import SimpleNamespace as SN

from ibtrader.diagnostics.suspicious import diagnose
from ibtrader.backtest.engine import BacktestResult


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
    data = {"SPY": pd.DataFrame({"close": [1.0, 2.0]}, index=pd.to_datetime(["2024-01-01", "2024-12-31"]))}
    flags = diagnose(res, data, lineage_sources={"SPY": "fixture"})
    codes = {f.code for f in flags}
    assert "extreme_cagr" in codes
    assert "extreme_sharpe" in codes
    assert "zero_costs" in codes
    assert "synthetic_source" in codes
    assert "anomalous_turnover" in codes

