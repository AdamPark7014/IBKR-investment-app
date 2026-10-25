from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json

def load_open_order_age_seconds(path: Path | str, *, now: datetime | None = None) -> float:
    try:
        p = Path(path)
        if not p.exists(): return 0.0
        data = json.loads(p.read_text())
        n_dt = now or datetime.now(timezone.utc)
        max_age = 0.0
        is_dict = isinstance(data, dict)
        if is_dict and "age_seconds" in data:
            return float(data["age_seconds"])
        orders = data.get("orders", []) if is_dict else []
        for o in orders:
            s = o.get("opened_at") or o.get("opened_at_utc")
            if not s: continue
            try:
                dt_open = datetime.fromisoformat(s.replace('Z', '+00:00'))
                age = (n_dt - dt_open).total_seconds()
                if age > max_age: max_age = age
            except Exception: pass
        return max_age
    except Exception:
        return 0.0