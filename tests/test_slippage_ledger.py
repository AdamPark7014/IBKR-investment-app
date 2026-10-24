from __future__ import annotations

from pathlib import Path

from ibtrader.ops.slippage_ledger import record_slip, slip_bps, summarize


def test_slip_bps_buy_adverse() -> None:
    assert abs(slip_bps("BUY", 100.0, 100.1) - 10.0) < 1e-9


def test_slip_bps_sell_adverse() -> None:
    assert abs(slip_bps("SELL", 100.0, 99.9) - 10.01001001) < 1e-6


def test_record_and_summarize(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    record_slip(path, symbol="SPY", side="BUY", decision_px=100.0, fill_px=100.05, qty=10, source="sim")
    record_slip(path, symbol="SPY", side="SELL", decision_px=100.0, fill_px=99.95, qty=5, source="sim")
    s = summarize(path, window_days=30)
    assert s["n"] == 2
    assert s["mean_slip_bps"] is not None
    assert s["p95_slip_bps"] is not None
