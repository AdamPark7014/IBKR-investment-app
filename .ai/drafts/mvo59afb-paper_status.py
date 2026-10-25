from __future__ import annotations
import json
from pathlib import Path
from typing import Any

__all__ = ["build_paper_status"]


def build_paper_status(data_dir: str | Path) -> dict[str, Any]:
    root = Path(data_dir).resolve()
    paths = {
        "freeze": root / "paper_config_freeze.json",
        "equity": root / "paper_equity.jsonl",
        "stack": root / "paper_stack.sqlite",
        "open_orders": root / "paper_open_orders.json",
        "slippage": root / "slippage_ledger.jsonl",
    }

    presence = {k: p.is_file() for k, p in paths.items()}
    summaries: dict[str, Any] = {}

    if presence["equity"]:
        from .paper_curve import load_equity_points, paper_max_drawdown
        pts = load_equity_points(paths["equity"])
        summaries["equity"] = {
            "n_points": len(pts),
            "max_dd": paper_max_drawdown(paths["equity"]),
            "last_equity": pts[-1]["equity"] if pts else None,
        }

    if presence["open_orders"]:
        from .open_orders import summary as oo_summary
        summaries["open_orders"] = oo_summary(paths["open_orders"])

    if presence["freeze"]:
        try:
            raw = json.loads(paths["freeze"].read_text(encoding="utf-8"))
            summaries["freeze"] = {
                "hash": raw.get("hash"),
                "has_snapshot": isinstance(raw.get("snapshot"), dict),
            }
        except Exception:
            summaries["freeze"] = {"error": "invalid_json"}

    if presence["stack"]:
        try:
            from .stack import PaperStack
            snap = PaperStack(paths["stack"]).snapshot()
            desired = snap.get("desired") or {}
            held = snap.get("held") or {}
            drift_items = snap.get("drift") or []
            n_drift = sum(1 for r in drift_items if float(r.get("delta", 0)) != 0.0)
            summaries["stack"] = {
                "n_desired": len(desired),
                "n_held": len(held),
                "n_drift": n_drift,
            }
        except Exception:
            summaries["stack"] = {"error": "stack_read_failed"}

    if presence["slippage"]:
        from .slippage_ledger import summarize
        summaries["slippage"] = summarize(paths["slippage"])

    return {
        "data_dir": str(root),
        "presence": presence,
        "summaries": summaries,
        "orders_sent": 0,
    }