from __future__ import annotations
import pathlib
from slippage_ledger import summarize as _summarize

def summarize_cli(path: str | pathlib.Path, window_days: int = 30) -> dict:
    if isinstance(path, str):
        path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    return _summarize(str(path.resolve()), window_days)