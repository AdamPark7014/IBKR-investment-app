"""Read paper open-order age for urgency triage. No broker orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def is_sample_payload(data: Any) -> bool:
    """Example files written by ``open-orders --write-sample`` carry ``"sample": true``."""
    return isinstance(data, dict) and data.get("sample") is True


def load_open_order_age_seconds(path: Path | str, *, now: datetime | None = None) -> float:
    """Max age in seconds from open-orders JSON; missing/invalid/sample → 0.0.

    Accepted shapes:
    - ``{\"age_seconds\": 12.3}``
    - ``{\"opened_at\": \"ISO\"}``
    - ``{\"orders\": [{\"opened_at\": \"ISO\"}, ...]}``
    """
    p = Path(path)
    if not p.is_file():
        return 0.0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    if is_sample_payload(data):
        return 0.0

    n_dt = now or datetime.now(timezone.utc)
    if n_dt.tzinfo is None:
        n_dt = n_dt.replace(tzinfo=timezone.utc)

    if isinstance(data, dict) and "age_seconds" in data:
        try:
            return max(0.0, float(data["age_seconds"]))
        except (TypeError, ValueError):
            return 0.0

    opened: list[str] = []
    if isinstance(data, dict):
        if data.get("opened_at"):
            opened.append(str(data["opened_at"]))
        for o in data.get("orders") or []:
            if isinstance(o, dict) and (o.get("opened_at") or o.get("opened_at_utc")):
                opened.append(str(o.get("opened_at") or o.get("opened_at_utc")))
    elif isinstance(data, list):
        for o in data:
            if isinstance(o, dict) and o.get("opened_at"):
                opened.append(str(o["opened_at"]))

    max_age = 0.0
    for s in opened:
        dt_open = _parse_iso(s)
        if dt_open is None:
            continue
        if dt_open.tzinfo is None:
            dt_open = dt_open.replace(tzinfo=timezone.utc)
        age = (n_dt - dt_open).total_seconds()
        if age > max_age:
            max_age = age
    return max_age


__all__ = ["is_sample_payload", "load_open_order_age_seconds"]
