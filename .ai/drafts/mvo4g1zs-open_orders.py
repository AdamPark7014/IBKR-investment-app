"""Paper open-orders JSON helper. No broker orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .urgency_age import load_open_order_age_seconds


def write_sample(path: Path | str) -> Path:
    """Write example paper_open_orders.json (orders only; no age_seconds)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    opened_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"orders": [{"symbol": "SPY", "opened_at": opened_at}]}
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def load_touchable(path: Path | str) -> bool:
    """True unless JSON has touchable:false. Missing/invalid → True."""
    p = Path(path)
    if not p.is_file():
        return True
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(data, dict):
        return True
    val = data.get("touchable")
    if val is False:
        return False
    if isinstance(val, str) and val.strip().lower() == "false":
        return False
    return True


def summary(path: Path | str) -> dict:
    """{age_seconds, touchable, orders_sent:0, n_orders}. Age via urgency_age."""
    p = Path(path)
    n_orders = 0
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("orders"), list):
                n_orders = len(data["orders"])
        except (OSError, json.JSONDecodeError):
            n_orders = 0
    return {
        "age_seconds": load_open_order_age_seconds(p),
        "touchable": load_touchable(p),
        "orders_sent": 0,
        "n_orders": n_orders,
    }


__all__ = ["write_sample", "load_touchable", "summary"]