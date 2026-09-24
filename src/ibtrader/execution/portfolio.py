from __future__ import annotations

from typing import Dict


def positions_notional(positions: Dict[str, int], last_prices: Dict[str, float]) -> float:
    return sum(abs(qty) * last_prices.get(sym, 0.0) for sym, qty in positions.items())

