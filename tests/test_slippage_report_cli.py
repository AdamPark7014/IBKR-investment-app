from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ibtrader.ops.cli import app as cli_mod_app
from ibtrader.ops.slippage_ledger import record_slip


def test_slippage_report_cli_smoke(tmp_path: Path) -> None:
    ledger = tmp_path / "slippage_ledger.jsonl"
    record_slip(ledger, symbol="SPY", side="BUY", decision_px=100.0, fill_px=100.05, qty=10, source="sim")
    record_slip(ledger, symbol="SPY", side="SELL", decision_px=100.0, fill_px=99.95, qty=5, source="sim")

    runner = CliRunner()
    res = runner.invoke(
        cli_mod_app,
        ["slippage-report", "--path", str(ledger), "--window-days", "30"],
    )
    assert res.exit_code == 0, res.stdout + str(res.exception)
    payload = json.loads(res.stdout)
    assert payload["n"] >= 1
    assert "mean_slip_bps" in payload
