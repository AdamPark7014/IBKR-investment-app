from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "data/paper_stack.sqlite"
_DDL = """
CREATE TABLE IF NOT EXISTS desired (
  symbol TEXT PRIMARY KEY, qty REAL NOT NULL, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS held (
  symbol TEXT PRIMARY KEY, qty REAL NOT NULL, ts TEXT NOT NULL
);
"""

def _ts_iso(ts) -> str:
  if isinstance(ts, datetime):
    if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()
  return str(ts)

class PaperStack:
  def __init__(self, db_path: str | Path | None = None) -> None:
    self.db_path = Path(db_path) if db_path is not None else Path(DEFAULT_DB_PATH)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    with self._connect() as conn:
      conn.executescript(_DDL)

  def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _upsert(self, table: str, symbol: str, qty: float, ts) -> None:
    assert table in ("desired", "held")
    with self._connect() as conn:
      conn.execute(
        f"INSERT INTO {table}(symbol, qty, ts) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET qty=excluded.qty, ts=excluded.ts",
        (str(symbol), float(qty), _ts_iso(ts)),
      )

  def upsert_desired(self, symbol: str, qty: float, ts) -> None:
    self._upsert("desired", symbol, qty, ts)

  def upsert_held(self, symbol: str, qty: float, ts) -> None:
    self._upsert("held", symbol, qty, ts)

  def snapshot(self) -> dict[str, Any]:
    with self._connect() as conn:
      desired = {r["symbol"]: float(r["qty"]) for r in conn.execute("SELECT symbol, qty FROM desired")}
      held = {r["symbol"]: float(r["qty"]) for r in conn.execute("SELECT symbol, qty FROM held")}
    drift = []
    for sym in sorted(set(desired) | set(held)):
      d = float(desired.get(sym, 0.0))
      h = float(held.get(sym, 0.0))
      drift.append({"symbol": sym, "desired": d, "held": h, "delta": d - h})
    return {"desired": desired, "held": held, "drift": drift}

  def sync_from_json(self, desired: dict, held: dict, ts=None) -> None:
    if ts is None: ts = datetime.now(timezone.utc)
    for sym, qty in dict(desired or {}).items():
      self.upsert_desired(str(sym), float(qty), ts)
    for sym, qty in dict(held or {}).items():
      self.upsert_held(str(sym), float(qty), ts)

def cmd_paper_stack(db_path: str | Path | None = None) -> dict[str, Any]:
  snap = PaperStack(db_path).snapshot()
  snap["orders_sent"] = 0
  return snap