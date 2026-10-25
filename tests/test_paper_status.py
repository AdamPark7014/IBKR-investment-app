from __future__ import annotations
import json
from pathlib import Path
from typer.testing import CliRunner
from ibtrader.ops.cli import app as cli_mod_app
from ibtrader.ops.paper_status import build_paper_status
from ibtrader.ops.paper_curve import append_equity_point
from ibtrader.ops.open_orders import write_sample
from ibtrader.ops.stack import PaperStack

def test_build_paper_status_empty(tmp_path: Path) -> None:
    out = build_paper_status(tmp_path)
    assert out["orders_sent"] == 0
    assert out["presence"] == {
        "freeze": False, "equity": False, "stack": False, "open_orders": False, "slippage": False
    }
    assert out["summaries"] == {}
    assert Path(out["data_dir"]) == tmp_path.resolve()

def test_build_paper_status_with_artifacts(tmp_path: Path) -> None:
    # freeze
    (tmp_path / "paper_config_freeze.json").write_text(
        json.dumps({"hash": "abc123", "snapshot": {"risk": {}}}), encoding="utf-8"
    )
    # equity: 100, 80, 90 → max_dd 0.2
    for eq in (100.0, 80.0, 90.0):
        append_equity_point(tmp_path / "paper_equity.jsonl", eq)
    # open orders sample
    write_sample(tmp_path / "paper_open_orders.json")
    # stack with drift
    stack = PaperStack(tmp_path / "paper_stack.sqlite")
    stack.upsert_desired("SPY", 10.0, "2026-01-01T00:00:00Z")
    stack.upsert_held("SPY", 8.0, "2026-01-01T00:00:00Z")
    # slippage one line
    (tmp_path / "slippage_ledger.jsonl").write_text(
        json.dumps(
            {
                "decision_ts": "2026-10-25T12:00:00+00:00",
                "symbol": "SPY",
                "slip_bps": 1.5,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = build_paper_status(tmp_path)
    assert out["orders_sent"] == 0
    assert all(out["presence"].values())
    assert out["summaries"]["freeze"]["hash"] == "abc123"
    assert out["summaries"]["freeze"]["has_snapshot"] is True
    assert out["summaries"]["equity"]["n_points"] == 3
    assert out["summaries"]["equity"]["last_equity"] == 90.0
    assert abs(out["summaries"]["equity"]["max_dd"] - 0.2) < 1e-9
    assert out["summaries"]["open_orders"]["orders_sent"] == 0
    assert out["summaries"]["open_orders"]["n_orders"] == 1
    assert out["summaries"]["stack"]["n_desired"] == 1
    assert out["summaries"]["stack"]["n_held"] == 1
    assert out["summaries"]["stack"]["n_drift"] == 1
    assert out["summaries"]["slippage"]["n"] == 1

def test_paper_status_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(cli_mod_app, ["paper-status", "--data-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout + str(res.exception)
    payload = json.loads(res.stdout)
    assert payload["orders_sent"] == 0
    assert payload["presence"]["equity"] is False
    assert payload["summaries"] == {}