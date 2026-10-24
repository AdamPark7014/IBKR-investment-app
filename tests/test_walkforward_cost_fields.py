from __future__ import annotations

from types import SimpleNamespace

from ibtrader.validation.walkforward import _stats_to_dict


def test_stats_to_dict_includes_cost_fields() -> None:
    stats = SimpleNamespace(
        cagr=0.1,
        sharpe=0.5,
        sortino=0.6,
        calmar=0.4,
        max_drawdown=-0.1,
        win_rate=0.5,
        trade_count=10,
        total_commission=12.0,
        turnover=1.2,
        profit_factor=1.5,
        expectancy=0.01,
        total_costs=20.0,
        avg_cost_bps_per_order=3.5,
        cost_drag_annual_pct=0.4,
        total_reg_fees=1.0,
    )
    d = _stats_to_dict(stats)
    assert d["avg_cost_bps_per_order"] == 3.5
    assert d["total_costs"] == 20.0
    assert d["cost_drag_annual_pct"] == 0.4
    assert d["total_reg_fees"] == 1.0
