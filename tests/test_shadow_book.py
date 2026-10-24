"""Ola D — shadow book stub (P1-6)."""

from __future__ import annotations

from dataclasses import dataclass

from ibtrader.backtest.engine import backtest, restricted_counts
from ibtrader.backtest.report import stats_json
from ibtrader.ops.shadow import (
    compare_positions,
    desired_from_decisions,
    log_shadow_snapshot,
)
from ibtrader.strategy.sma_crossover import SMACrossover


@dataclass
class _Dec:
    symbol: str
    action: str
    position_size: float


def test_compare_positions_drift() -> None:
    lines = compare_positions({"SPY": 0.1, "QQQ": 0.0}, {"SPY": 0.05, "TLT": 0.02})
    by_sym = {line.symbol: line for line in lines}
    assert by_sym["SPY"].delta == 0.05
    assert by_sym["QQQ"].delta == 0.0
    assert by_sym["TLT"].delta == -0.02


def test_desired_from_decisions_signs() -> None:
    desired = desired_from_decisions(
        [
            _Dec("SPY", "BUY", 0.12),
            _Dec("QQQ", "SELL", 0.08),
            _Dec("IWM", "WATCH", 0.5),
        ]
    )
    assert desired["SPY"] == 0.12
    assert desired["QQQ"] == -0.08
    assert desired["IWM"] == 0.0


def test_log_shadow_snapshot_counts_drift() -> None:
    payload = log_shadow_snapshot({"A": 1.0}, {"A": 0.5, "B": 0.1}, tag="unit")
    assert payload["n_drift"] == 2
    assert payload["tag"] == "unit"
    assert len(payload["lines"]) == 2


def test_stats_json_includes_restricted_bar_frac() -> None:
    import pandas as pd

    idx = pd.date_range("2020-01-01", periods=5, freq="B")
    data = {
        "SPY": pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1e6},
            index=idx,
        )
    }
    from ibtrader.config import CommissionConfig, SlippageConfig

    strat = SMACrossover(fast_window=2, slow_window=3)
    res = backtest(
        data=data,
        strategy=strat,
        commission_cfg=CommissionConfig(),
        slippage_cfg=SlippageConfig(),
        initial_equity=100_000.0,
    )
    restricted, total = restricted_counts(res)
    sj = stats_json(res)
    assert sj["restricted_bars"] == restricted
    assert sj["total_bars"] == total
    assert sj["restricted_bar_frac"] == (restricted / total if total else 0.0)
