from __future__ import annotations

from dataclasses import dataclass
from typing import List

import yaml


@dataclass
class Watchlist:
    symbols: List[str]
    benchmark: str = "SPY"


def load_watchlist(path: str) -> Watchlist:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    syms = list(dict.fromkeys(list(data.get("symbols", []) or [])))
    bench = data.get("benchmark", "SPY")
    return Watchlist(symbols=syms, benchmark=bench)

