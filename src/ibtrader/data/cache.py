from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .lineage import DataLineage
import json

def cache_path(cache_dir: str, symbol: str, bar_size: str) -> Path:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol.replace('/', '_')}_{bar_size}.parquet"
    return Path(cache_dir) / fname


def load_from_cache(cache_dir: str, symbol: str, bar_size: str) -> Optional[pd.DataFrame]:
    path = cache_path(cache_dir, symbol, bar_size)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df
    except Exception:
        return None


def save_to_cache(cache_dir: str, symbol: str, bar_size: str, df: pd.DataFrame) -> None:
    path = cache_path(cache_dir, symbol, bar_size)
    df.to_parquet(path)

def cache_meta_path(cache_dir: str, symbol: str, bar_size: str) -> Path:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol.replace('/', '_')}_{bar_size}.meta.json"
    return Path(cache_dir) / fname

def save_lineage(cache_dir: str, symbol: str, bar_size: str, lineage: DataLineage) -> None:
    path = cache_meta_path(cache_dir, symbol, bar_size)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(lineage.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception:
        # Sidecar meta is best-effort
        return

def load_lineage(cache_dir: str, symbol: str, bar_size: str) -> Optional[DataLineage]:
    path = cache_meta_path(cache_dir, symbol, bar_size)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DataLineage(
            source=data.get("source"),
            source_url=data.get("source_url"),
            fetched_at_utc=data.get("fetched_at_utc"),
            methodology=data.get("methodology"),
            parameters=data.get("parameters") or {},
            license=data.get("license"),
            notes=data.get("notes"),
        )
    except Exception:
        return None

