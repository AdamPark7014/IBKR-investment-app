"""Project-wide trial ledger: N counted across runs, not per run.

The DSR and the trial budget deflate by the number of configurations tried. Counting only the
current run understates N: every earlier run over the same market data, and every change made
after looking at it, is also a trial (López de Prado: ~20 iterations are enough to find a false
strategy at 5 %). This ledger appends one line per run and sums N per *dataset family*.

A dataset family is ``<universe>|<first bar>``: it stays the same when new daily bars are
appended (the hash changes every day, the researcher's knowledge of the history does not).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

LEDGER_NAME = "trials_ledger_global.jsonl"


def ledger_path(reports_dir: str | Path) -> Path:
    return Path(reports_dir) / "research" / LEDGER_NAME


def dataset_family(symbols: Iterable[str], first_bar: Any) -> str:
    syms = ",".join(sorted({str(s).upper() for s in symbols}))
    first = str(first_bar)[:10] if first_bar is not None else "?"
    return f"{syms}|{first}"


def prior_trials(path: str | Path, family: str) -> int:
    """Sum of ``n_trials`` already logged for ``family`` (missing file → 0)."""
    p = Path(path)
    if not p.exists():
        return 0
    total = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("family") == family:
            try:
                total += max(int(row.get("n_trials") or 0), 0)
            except (TypeError, ValueError):
                continue
    return total


def record_trials(
    path: str | Path,
    family: str,
    n_trials: int,
    *,
    exp_id: Optional[str] = None,
    kind: str = "research-run",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one run to the ledger and return the row written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    row: Dict[str, Any] = {
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        "family": family,
        "n_trials": int(max(n_trials, 0)),
        "exp_id": exp_id,
        "kind": kind,
    }
    if extra:
        row["extra"] = dict(extra)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    return row


__all__ = ["LEDGER_NAME", "ledger_path", "dataset_family", "prior_trials", "record_trials"]
