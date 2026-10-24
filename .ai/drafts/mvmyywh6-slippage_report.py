from __future__ import annotations
from pathlib import Path
from slippage_ledger import summarize as slippage_summarize


def summarize_cli(path: str | Path, window_days: int = 30) -> dict:
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Ledger file not found at {path}")
    result = slippage_summarize(str(path_obj), window_days)
    return {
        "orders": [],
        "summary": result.get("summary", {}),
        "status": "processed",
        "message": "Zero orders included per request."
    }