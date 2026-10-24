from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

try:
    from typing_extensions import NotRequired, TypedDict
except ImportError:
    pass

__all__: list[str] = ['load_equity_points', 'max_drawdown', 'paper_max_drawdown']


def load_equity_points(path: str | Path) -> list[dict]:
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        return []

    points: list[dict[str, float]] = []
    ts_aliases: set[str] = {'ts', 'timestamp', 't', 'as_of', 'time'}
    equity_aliases: set[str] = {'equity', 'nav', 'value'}

    try:
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj: dict[str, Any] = json.loads(stripped)
                except json.JSONDecodeError:
                    continue

                ts_key: str | None = None
                equity_key: str | None = None

                for k in ts_aliases:
                    if k in obj:
                        ts_key = k
                        break
                else:
                    continue

                for k in equity_aliases:
                    if k in obj:
                        equity_key = k
                        break
                else:
                    continue

                ts_val = obj[ts_key]
                equity_val = obj[equity_key]

                if not isinstance(ts_val, str):
                    continue

                try:
                    _ = float(equity_val)
                except (TypeError, ValueError):
                    continue

                eq_float: float = float(equity_val)

                if math.isnan(eq_float) or math.isinf(eq_float):
                    continue

                if eq_float <= 0:
                    continue

                points.append({'ts': ts_val, 'equity': eq_float})
    except (OSError, UnicodeDecodeError):
        return []

    return points


def max_drawdown(equities: list[float]) -> float | None:
    if len(equities) < 2:
        return None

    peak: float = equities[0]
    max_dd: float = 0.0

    for e in equities:
        if peak > 0 and (peak - e) / peak > max_dd:
            max_dd = (peak - e) / peak
        elif peak <= 0 and e < peak:
            # Only drawdown if we have a positive reference or standard logic applies
            # If peak is negative, drawdown conceptually implies loss relative to previous high
            # Standard formula (peak - e)/peak handles sign correctly usually but if peak<0 division flips.
            # Standard interpretation: track max value seen.
            pass
        else:
            pass
        
        if e > peak:
            peak = e

    return max_dd


def paper_max_drawdown(path: str | Path) -> float | None:
    points: list[dict] = load_equity_points(path)
    if not points:
        return None
    
    equities: list[float] = [p['equity'] for p in points]
    return max_drawdown(equities)