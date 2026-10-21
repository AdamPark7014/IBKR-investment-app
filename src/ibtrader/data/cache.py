from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa

from .lineage import DataLineage

log = logging.getLogger("ibtrader.data.cache")


def cache_path(cache_dir: str, symbol: str, bar_size: str) -> Path:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol.replace('/', '_')}_{bar_size}.parquet"
    return Path(cache_dir) / fname


def load_from_cache(cache_dir: str, symbol: str, bar_size: str) -> Optional[pd.DataFrame]:
    """Return the cached frame, or None when absent.

    A cache file that exists but cannot be read is a *loud* miss: the reason is logged at ERROR
    (audit P1-4) and the caller falls back to the providers, which will overwrite it.
    """
    path = cache_path(cache_dir, symbol, bar_size)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError, pa.ArrowException) as e:
        log.error("cache_read_failed symbol=%s path=%s reason=%s: %s", symbol, path, type(e).__name__, e)
        return None


def save_to_cache(cache_dir: str, symbol: str, bar_size: str, df: pd.DataFrame) -> None:
    path = cache_path(cache_dir, symbol, bar_size)
    df.to_parquet(path)


def cache_meta_path(cache_dir: str, symbol: str, bar_size: str) -> Path:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol.replace('/', '_')}_{bar_size}.meta.json"
    return Path(cache_dir) / fname


def save_lineage(cache_dir: str, symbol: str, bar_size: str, lineage: DataLineage) -> None:
    """Write the lineage sidecar. Raises on failure: the caller decides whether a missing sidecar blocks."""
    path = cache_meta_path(cache_dir, symbol, bar_size)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lineage.to_dict(), f, ensure_ascii=False, indent=2)


def load_lineage(cache_dir: str, symbol: str, bar_size: str) -> Optional[DataLineage]:
    path = cache_meta_path(cache_dir, symbol, bar_size)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log.error("lineage_read_failed symbol=%s path=%s reason=%s", symbol, path, e)
        return None
    if not isinstance(data, dict) or not data.get("source"):
        log.error("lineage_invalid symbol=%s path=%s reason=sin campo 'source'", symbol, path)
        return None
    return DataLineage(
        source=str(data.get("source")),
        source_url=data.get("source_url"),
        fetched_at_utc=data.get("fetched_at_utc"),
        methodology=data.get("methodology"),
        parameters=data.get("parameters") or {},
        license=data.get("license"),
        notes=data.get("notes"),
        vintage_date=data.get("vintage_date"),
        vintage_path=data.get("vintage_path"),
        sha256=data.get("sha256"),
    )

