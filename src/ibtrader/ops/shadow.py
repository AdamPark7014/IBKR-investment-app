"""Shadow book (P1-6): log desired vs held positions without touching a broker."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping

from ..logging import setup_logging

log = setup_logging()


@dataclass(frozen=True)
class ShadowLine:
    symbol: str
    desired: float
    held: float
    delta: float


def compare_positions(
    desired: Mapping[str, float],
    held: Mapping[str, float],
) -> list[ShadowLine]:
    """Pairwise desired vs held weights (fraction of portfolio or share units)."""
    symbols = sorted(set(desired) | set(held))
    lines: list[ShadowLine] = []
    for sym in symbols:
        d = float(desired.get(sym, 0.0))
        h = float(held.get(sym, 0.0))
        lines.append(ShadowLine(symbol=sym, desired=d, held=h, delta=d - h))
    return lines


def desired_from_decisions(decisions: Iterable[Any]) -> Dict[str, float]:
    """Map paper ``Decision`` rows to signed target weights (BUY +, SELL −)."""
    out: Dict[str, float] = {}
    for row in decisions:
        if hasattr(row, "symbol"):
            sym = str(row.symbol)
            action = str(row.action)
            size = float(row.position_size)
        elif isinstance(row, Mapping):
            sym = str(row["symbol"])
            action = str(row["action"])
            size = float(row.get("position_size", 0.0))
        else:
            continue
        if action == "BUY":
            out[sym] = size
        elif action == "SELL":
            out[sym] = -abs(size)
        else:
            out[sym] = 0.0
    return out


def log_shadow_snapshot(
    desired: Mapping[str, float],
    held: Mapping[str, float] | None = None,
    *,
    tag: str = "shadow",
) -> Dict[str, Any]:
    """Log champion desired vs held snapshot; returns JSON-serializable summary."""
    held_map = dict(held or {})
    lines = compare_positions(desired, held_map)
    payload: Dict[str, Any] = {
        "tag": tag,
        "lines": [asdict(line) for line in lines],
        "n_symbols": len(lines),
        "n_drift": sum(1 for line in lines if abs(line.delta) > 1e-9),
    }
    log.info(
        "shadow_book tag=%s n_drift=%s lines=%s",
        tag,
        payload["n_drift"],
        payload["lines"],
    )
    return payload
