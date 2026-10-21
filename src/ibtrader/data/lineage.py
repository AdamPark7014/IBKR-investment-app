from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class DataLineage:
    source: str
    source_url: Optional[str] = None
    fetched_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    methodology: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    license: Optional[str] = None
    notes: Optional[str] = None
    # Point-in-time vintage (playbook phase 1): where this exact snapshot lives and its SHA-256.
    vintage_date: Optional[str] = None
    vintage_path: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DataFrameWithMeta:
    data: pd.DataFrame
    lineage: DataLineage

    def copy(self) -> "DataFrameWithMeta":
        return DataFrameWithMeta(self.data.copy(), self.lineage)

