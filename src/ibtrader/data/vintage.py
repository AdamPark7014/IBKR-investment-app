"""Point-in-time vintages: immutable Parquet snapshots plus a SHA-256 manifest.

Why (playbook phase 1, annex 5 section 2): yfinance only knows survivors and re-adjusts history backwards,
so a backtest run today cannot be reproduced next month unless we keep *what we knew when*. Every successful
load writes ``<vintage_dir>/vintage_date=YYYY-MM-DD/<SYMBOL>_<bar>.parquet`` and records it in
``<vintage_dir>/manifest.json``::

    {
      "schema_version": 1,
      "vintages": {
        "2026-10-21": {
          "created_at_utc": "...", "updated_at_utc": "...",
          "files": [{"symbol", "bar_size", "path", "sha256", "rows", "first_bar", "last_bar", "provider"}],
          "dataset_hash": "sha256 over the sorted file sha256s"
        }
      }
    }

Rules:
  - A file already present for that vintage date with the *same* SHA-256 is left untouched (idempotent).
  - A different SHA-256 for the same day (e.g. yfinance refreshed the partial bar of today) overwrites it,
    logs a WARNING and keeps the superseded hash in the manifest entry (``superseded``).
  - ``load_vintage`` re-hashes every file and fails loudly when any hash disagrees with the manifest.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

log = logging.getLogger("ibtrader.data.vintage")

MANIFEST_NAME = "manifest.json"
VINTAGE_PREFIX = "vintage_date="
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VintageRecord:
    """What ``write_vintage`` returns: enough for ``DataLineage`` and for the manifest."""

    vintage_date: str
    symbol: str
    bar_size: str
    path: str  # relative to vintage_dir, POSIX separators
    sha256: str
    rows: int
    first_bar: Optional[str]
    last_bar: Optional[str]
    provider: str
    written: bool  # False when an identical file already existed


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: "str | os.PathLike[str]") -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def vintage_subdir(vintage_dir: str, vintage_date: str) -> Path:
    return Path(vintage_dir) / f"{VINTAGE_PREFIX}{vintage_date}"


def vintage_file_path(vintage_dir: str, vintage_date: str, symbol: str, bar_size: str) -> Path:
    return vintage_subdir(vintage_dir, vintage_date) / f"{symbol.replace('/', '_')}_{bar_size}.parquet"


def manifest_path(vintage_dir: str) -> Path:
    return Path(vintage_dir) / MANIFEST_NAME


def today_utc() -> str:
    return str(datetime.now(timezone.utc).date())


def _frame_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf)
    return buf.getvalue()


def _bar_label(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    try:
        return str(pd.Timestamp(ts).date())
    except (TypeError, ValueError):
        return str(ts)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, path)


def load_manifest(vintage_dir: str) -> Dict[str, Any]:
    """Load manifest.json; a missing manifest is an empty one, a corrupt one raises."""
    path = manifest_path(vintage_dir)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "vintages": {}}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("vintages"), dict):
        raise RuntimeError(f"Manifiesto de vintages corrupto: {path} (falta 'vintages')")
    return data


def dataset_hash_from_files(file_hashes: List[str]) -> str:
    """SHA-256 over the sorted per-file SHA-256s; order-independent, content-dependent."""
    h = hashlib.sha256()
    for fh in sorted(file_hashes):
        h.update(fh.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def _save_manifest(vintage_dir: str, manifest: Dict[str, Any]) -> None:
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _atomic_write_bytes(manifest_path(vintage_dir), payload)


def _upsert_manifest_entry(vintage_dir: str, rec: VintageRecord, superseded: Optional[str]) -> Dict[str, Any]:
    manifest = load_manifest(vintage_dir)
    now = datetime.now(timezone.utc).isoformat()
    vint = manifest["vintages"].setdefault(rec.vintage_date, {"created_at_utc": now, "files": []})
    files: List[Dict[str, Any]] = list(vint.get("files") or [])
    entry: Dict[str, Any] = {
        "symbol": rec.symbol,
        "bar_size": rec.bar_size,
        "path": rec.path,
        "sha256": rec.sha256,
        "rows": rec.rows,
        "first_bar": rec.first_bar,
        "last_bar": rec.last_bar,
        "provider": rec.provider,
    }
    kept: List[Dict[str, Any]] = []
    previous: List[str] = []
    for f in files:
        if f.get("symbol") == rec.symbol and f.get("bar_size") == rec.bar_size:
            previous = list(f.get("superseded") or [])
            if superseded and superseded != rec.sha256 and superseded not in previous:
                previous.append(superseded)
            continue
        kept.append(f)
    if previous:
        entry["superseded"] = previous
    kept.append(entry)
    kept.sort(key=lambda f: (str(f.get("symbol")), str(f.get("bar_size"))))
    vint["files"] = kept
    vint["updated_at_utc"] = now
    vint["dataset_hash"] = dataset_hash_from_files([str(f["sha256"]) for f in kept])
    manifest["schema_version"] = SCHEMA_VERSION
    _save_manifest(vintage_dir, manifest)
    return manifest


def write_vintage(
    vintage_dir: str,
    symbol: str,
    bar_size: str,
    df: pd.DataFrame,
    *,
    provider: str,
    vintage_date: Optional[str] = None,
) -> VintageRecord:
    """Persist ``df`` as the snapshot of ``symbol`` for ``vintage_date`` (default: today UTC) and update the manifest.

    Idempotent for identical content. Raises (does not swallow) on I/O errors: if we cannot record what we
    knew, the load must not pretend we did.
    """
    if df is None or df.empty:
        raise ValueError(f"write_vintage: DataFrame vacío para {symbol}")
    vdate = vintage_date or today_utc()
    # Validate the date format early so a typo never creates a bogus partition.
    date.fromisoformat(vdate)
    target = vintage_file_path(vintage_dir, vdate, symbol, bar_size)
    payload = _frame_to_parquet_bytes(df)
    new_hash = sha256_bytes(payload)
    rel = target.relative_to(Path(vintage_dir)).as_posix()
    rec = VintageRecord(
        vintage_date=vdate,
        symbol=symbol,
        bar_size=bar_size,
        path=rel,
        sha256=new_hash,
        rows=int(len(df)),
        first_bar=_bar_label(df.index.min()),
        last_bar=_bar_label(df.index.max()),
        provider=provider,
        written=True,
    )
    superseded: Optional[str] = None
    if target.exists():
        old_hash = sha256_file(target)
        if old_hash == new_hash:
            log.info("vintage_unchanged symbol=%s vintage_date=%s sha256=%s", symbol, vdate, new_hash[:12])
            rec = VintageRecord(**{**asdict(rec), "written": False})
            # Make sure the manifest knows about it even if a previous run died between file and manifest.
            _upsert_manifest_entry(vintage_dir, rec, superseded=None)
            return rec
        superseded = old_hash
        log.warning(
            "vintage_overwrite symbol=%s vintage_date=%s old_sha256=%s new_sha256=%s rows=%s",
            symbol,
            vdate,
            old_hash[:12],
            new_hash[:12],
            len(df),
        )
    _atomic_write_bytes(target, payload)
    _upsert_manifest_entry(vintage_dir, rec, superseded=superseded)
    log.info(
        "vintage_written symbol=%s vintage_date=%s rows=%s sha256=%s provider=%s",
        symbol,
        vdate,
        len(df),
        new_hash[:12],
        provider,
    )
    return rec


def list_vintages(vintage_dir: str) -> List[str]:
    """Vintage dates known to the manifest, oldest first."""
    manifest = load_manifest(vintage_dir)
    return sorted(manifest["vintages"].keys())


def load_vintage(
    vintage_dir: str,
    vintage_date: str,
    *,
    bar_size: str = "1d",
    symbols: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """Rebuild exactly the snapshot recorded for ``vintage_date``.

    Every file is re-hashed and compared with the manifest; any mismatch or missing file raises a single
    ``RuntimeError`` listing all problems (nothing partial is returned).
    """
    manifest = load_manifest(vintage_dir)
    vint = manifest["vintages"].get(vintage_date)
    if vint is None:
        known = ", ".join(sorted(manifest["vintages"].keys())) or "ninguno"
        raise RuntimeError(f"Vintage {vintage_date} no existe en {manifest_path(vintage_dir)} (conocidos: {known})")
    wanted = {s.upper() for s in symbols} if symbols else None
    out: Dict[str, pd.DataFrame] = {}
    problems: List[str] = []
    seen: set[str] = set()
    for f in vint.get("files") or []:
        if f.get("bar_size") != bar_size:
            continue
        sym = str(f.get("symbol"))
        if wanted is not None and sym.upper() not in wanted:
            continue
        seen.add(sym.upper())
        path = Path(vintage_dir) / str(f.get("path"))
        if not path.exists():
            problems.append(f"{sym}: falta el archivo {path}")
            continue
        actual = sha256_file(path)
        expected = str(f.get("sha256"))
        if actual != expected:
            problems.append(f"{sym}: sha256 no coincide (manifiesto {expected[:12]}, disco {actual[:12]}) en {path}")
            continue
        out[sym] = pd.read_parquet(path)
    if wanted is not None:
        missing = sorted(wanted - seen)
        if missing:
            problems.append(f"símbolos sin entrada en el vintage {vintage_date}: {missing}")
    if problems:
        raise RuntimeError(f"Vintage {vintage_date} no verificable: " + "; ".join(problems))
    if not out:
        raise RuntimeError(f"Vintage {vintage_date} no tiene archivos con bar_size={bar_size}")
    return out
