from __future__ import annotations

from pathlib import Path


def activate_killswitch(path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("HALT", encoding="utf-8")


def clear_killswitch(path: str) -> None:
    p = Path(path)
    if p.exists():
        p.unlink()

