from __future__ import annotations

import pandas as pd

from ibtrader.risk.loss_metrics import compute_loss_metrics


def test_loss_metrics_computation() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    equity = pd.Series([100_000.0, 99_000.0, 101_000.0, 102_000.0, 101_500.0], index=idx)
    day_start = 100_000.0
    # Long position with unrealized loss
    lm = compute_loss_metrics(
        equity_curve=equity,
        day_start_equity=day_start,
        position_qty=100,
        avg_price=105.0,
        last_price=101.5,
        realized_pnl_cum=-250.0,
    )
    assert lm.daily_loss_pct == (101_500.0 - 100_000.0) / 100_000.0
    assert lm.cumulative_loss_pct == (101_500.0 - 100_000.0) / 100_000.0
    assert lm.drawdown_from_peak_pct <= 0.0
    assert lm.per_position_unrealized_pct < 0.0
    assert lm.realized_loss <= 0.0
    assert lm.unrealized_loss <= 0.0

