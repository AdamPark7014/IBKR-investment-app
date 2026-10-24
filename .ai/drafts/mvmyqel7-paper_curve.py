from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

def load_equity_points(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    points = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = {"ts": "", "equity": 0.0}
                import json
                d = json.loads(line)
                data["ts"] = d.get("ts", "")
                equity_str = d.get("equity", "").replace(",", "")
                data["equity"] = float(equity_str)
                points.append(data)
            except Exception:
                continue
    return points

def max_drawdown(equities: list[float]) -> Optional[float]:
    if len(equities) < 2:
        return None
    peak = equities[0]
    trough = equities[0]
    for e in equities:
        if e > peak:
            peak = e
        if e < trough:
            trough = e
        dd = (peak - e) / peak
        if dd > 0 and dd > 0.0:
            return dd
    return None

def paper_max_drawdown(path: Path) -> Optional[float]:
    equities = [p["equity"] for p in load_equity_points(path)]
    max_dd = max_drawdown(equities)
    return max_dd