from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import timezone, datetime as dt_type

import ibtrader.config
from ibtrader.ops.urgency_age import load_open_order_age_seconds

__all__: list[str] = ["write_sample", "load_touchable", "summary"]


def write_sample(path: Path | str) -> Path:
    """Write example paper_open_orders.json."""
    p = Path(path)
    now = dt_type.now(tz=timezone.utc).isoformat()
    data = {"orders": [{"symbol": "SPY", "opened_at": now}]}
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return p


def load_touchable(path: Path | str) -> bool:
    """Load touchable flag from file; default True if missing/invalid."""
    p = Path(path)
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        # Handle dict case with 'orders' key potentially present or absent
        if isinstance(d, dict):
            val = d.get("touchable")
            if val is False or (isinstance(val, str) and val.lower() == "false"):
                return False
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return True


def summary(path: Path | str) -> dict:
    """Return summary of paper open orders."""
    p = Path(path)
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        n_orders = 0
        if isinstance(d, dict):
            if "orders" in d and isinstance(d["orders"], list):
                n_orders = len(d["orders"])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {
        "age_seconds": load_open_order_age_seconds(p),
        "touchable": load_touchable(p),
        "orders_sent": 0,
        "n_orders": n_orders,
    }