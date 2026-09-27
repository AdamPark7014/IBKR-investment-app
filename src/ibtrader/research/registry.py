"""Experiment registry: append-only JSONL under reports/research/."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_REGISTRY_DIR = Path("reports") / "research"
DEFAULT_REGISTRY_FILE = DEFAULT_REGISTRY_DIR / "experiments.jsonl"


@dataclass
class ExperimentRecord:
    """One research evaluation row (config + OOS metrics + gate outcome)."""

    exp_id: str
    created_at_utc: str
    git_commit: str
    candidate_id: str
    params: Dict[str, Any]
    oos: Dict[str, Any]
    buy_hold_oos: Optional[Dict[str, Any]]
    gate_passed: bool
    gate_reasons: List[str]
    notes: str = ""
    dataset_hash: str = ""
    config_hash: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def default_registry_path(reports_dir: str | Path | None = None) -> Path:
    """Return JSONL path under ``reports/research/`` (or ``<reports_dir>/research/``)."""
    if reports_dir is None:
        return DEFAULT_REGISTRY_FILE
    return Path(reports_dir) / "research" / "experiments.jsonl"


def save_experiment(path: str | Path, record: ExperimentRecord) -> Path:
    """Append one experiment record as a JSONL line. Creates parent dirs."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return out


def load_experiments(path: str | Path) -> List[ExperimentRecord]:
    """Load all experiment records from a JSONL file. Missing file → empty list."""
    p = Path(path)
    if not p.exists():
        return []
    rows: List[ExperimentRecord] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        # Tolerate older rows that omit optional fields
        known = {f.name for f in fields(ExperimentRecord)}
        filtered = {k: v for k, v in d.items() if k in known}
        rows.append(ExperimentRecord(**filtered))
    return rows
