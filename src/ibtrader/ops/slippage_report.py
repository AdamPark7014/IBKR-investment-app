from __future__ import annotations

from pathlib import Path
from typing import Any

from .slippage_ledger import summarize


def summarize_cli(path: str | Path, window_days: int = 30) -> dict[str, Any]:
    """Thin CLI wrapper around ``slippage_ledger.summarize`` (zero orders)."""
    return summarize(path, window_days)
