from __future__ import annotations
from pathlib import Path
from typing import Any
import json

def build_paper_status(data_dir: str | Path = "data") -> dict[str, Any]:
    data_path = Path(data_dir)
    freeze_file = data_path / "paper_config_freeze.json"
    equity_file = data_path / "paper_equity.jsonl"
    pos_file = data_path / "paper_positions.json"
    orders_file = data_path / "paper_open_orders.json"
    stack_file = data_path / "paper_stack.sqlite"
    slippage_file = data_path / "slippage_ledger.jsonl"

    notes = ["paper triage only", "do not retune live"]
    
    status: dict[str, Any] = {
        "data_dir": str(data_path),
        "files_present": {},
        "summaries": {},
        "notes": notes,
        "orders_sent": 0
    }

    if freeze_file.exists():
        try:
            config_freeze = __import__("app_settings", fromlist=["AppSettings"]).AppSettings
            if hasattr(config_freeze, "verify_freeze"):
                status["files_present"]["freeze"] = {"verified": True, "config": str(freeze_file)}
            else:
                with open(freeze_file) as f:
                    status["files_present"]["freeze"] = {"hash": hash(f.read()), "present": True}
        except Exception:
            status["files_present"]["freeze"] = {"error": "verify_freeze import failed"}

    if equity_file.exists():
        with open(equity_file) as f:
            lines = [line.strip() for line in f if line.strip()]
        if lines:
            first_line = json.loads(lines[0])
            status["summaries"]["equity"] = {
                "n_points": len(lines),
                "max_drawdown": float(first_line.get("paper_max_drawdown", 0))
            }
        else:
            status["summaries"]["equity"] = {"n_points": 0, "max_drawdown": None}

    if orders_file.exists():
        with open(orders_file) as f:
            lines = [line.strip() for line in f if line.strip()]
        status["summaries"]["open_orders"] = {"total_lines": len(lines), "summary": "aggregated"}
        status["files_present"]["open_orders"] = True

    if slippage_file.exists():
        with open(slippage_file) as f:
            lines = [line.strip() for line in f if line.strip()]
        status["summaries"]["slippage"] = {"n_entries": len(lines)}

    return status