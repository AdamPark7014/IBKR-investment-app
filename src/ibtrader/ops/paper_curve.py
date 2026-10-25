from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

__all__ = [
    "load_equity_points",
    "max_drawdown",
    "paper_max_drawdown",
    "append_equity_point",
    "estimate_mark_to_market",
]

_TS_ALIASES = ("ts", "timestamp", "t", "as_of", "time")
_EQUITY_ALIASES = ("equity", "nav", "value")


def load_equity_points(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []

    points: list[dict[str, Any]] = []
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue

                ts_val = None
                for key in _TS_ALIASES:
                    if key in obj:
                        ts_val = obj[key]
                        break
                equity_raw = None
                for key in _EQUITY_ALIASES:
                    if key in obj:
                        equity_raw = obj[key]
                        break
                if ts_val is None or equity_raw is None:
                    continue
                try:
                    equity = float(equity_raw)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(equity) or equity <= 0:
                    continue
                points.append({"ts": str(ts_val), "equity": equity})
    except OSError:
        return []
    return points


def max_drawdown(equities: list[float]) -> float | None:
    if len(equities) < 2:
        return None

    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def paper_max_drawdown(path: str | Path) -> float | None:
    equities = [pt["equity"] for pt in load_equity_points(path)]
    return max_drawdown(equities)


def append_equity_point(path: str | Path, equity: float, ts: str | None = None) -> None:
    """Append one JSONL ``{ts, equity}`` line. Skip non-finite or non-positive equity."""
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        return
    if not math.isfinite(eq) or eq <= 0:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if ts is None:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": str(ts), "equity": eq}, ensure_ascii=False) + "\n")


def estimate_mark_to_market(
    held: dict[str, float],
    last_prices: dict[str, float],
    cash: float = 0.0,
) -> float | None:
    """``cash + Σ qty*price`` for priced holdings; None if nothing priced and cash≤0."""
    total = float(cash)
    priced = False
    for sym, qty in (held or {}).items():
        px = (last_prices or {}).get(sym)
        if px is None:
            continue
        try:
            total += float(qty) * float(px)
            priced = True
        except (TypeError, ValueError):
            continue
    if not priced and total <= 0:
        return None
    return total
