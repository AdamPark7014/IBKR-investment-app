"""The project depends on ib_async. Mocks hide a wrong import, so this checks the source directly."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "ibtrader"
BAD_IMPORT = re.compile(r"^\s*(from\s+ib_insync\b|import\s+ib_insync\b)", re.MULTILINE)


def test_source_never_imports_ib_insync() -> None:
    offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py") if BAD_IMPORT.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
