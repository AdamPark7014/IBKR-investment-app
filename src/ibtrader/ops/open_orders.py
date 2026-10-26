"""Paper open-orders JSON helper. No broker orders.

``data/paper_open_orders.json`` is operational state: only real paper orders belong there. The
example written by ``write_sample`` goes to ``<stem>.sample.json``, is marked ``"sample": true`` and
is ignored by the triage (age, touchable, urgency): a fake order in the real file made every
autopilot brief say "urgency aggressive".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .urgency_age import is_sample_payload, load_open_order_age_seconds


def sample_path_for(path: Path | str) -> Path:
    """``data/paper_open_orders.json`` → ``data/paper_open_orders.sample.json``."""
    p = Path(path)
    if p.name.endswith(".sample.json"):
        return p
    return p.with_name(f"{p.stem}.sample.json")


def write_sample(path: Path | str) -> Path:
    """Write an example open-orders file (orders only; no age_seconds), marked ``sample``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    opened_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"sample": True, "orders": [{"symbol": "SPY", "opened_at": opened_at}]}
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def _load(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_touchable(path: Path | str) -> bool:
    """True unless JSON has touchable:false. Missing/invalid/sample → True."""
    data = _load(Path(path))
    if not isinstance(data, dict) or is_sample_payload(data):
        return True
    val = data.get("touchable")
    if val is False:
        return False
    if isinstance(val, str) and val.strip().lower() == "false":
        return False
    return True


def summary(path: Path | str) -> dict:
    """{age_seconds, touchable, orders_sent:0, n_orders, sample}. Age via urgency_age."""
    p = Path(path)
    data = _load(p)
    n_orders = 0
    if isinstance(data, dict) and isinstance(data.get("orders"), list):
        n_orders = len(data["orders"])
    return {
        "age_seconds": load_open_order_age_seconds(p),
        "touchable": load_touchable(p),
        "orders_sent": 0,
        "n_orders": n_orders,
        "sample": bool(is_sample_payload(data)),
        "path": str(p),
    }


__all__ = ["load_touchable", "sample_path_for", "summary", "write_sample"]
