from __future__ import annotations

import os
from datetime import timezone, datetime
from pathlib import Path
from typing import Any, Optional

try:
    from sqlalchemy import create_engine, MetaData, Table, text
except ImportError:
    import sqlite3 as sql
    from contextlib import contextmanager

DEFAULT_DB_PATH = "data/paper_stack.sqlite"


class PaperStack:
    """Paper-only stack layer. Zero broker orders."""

    _META = None
    _ENGINE = None
    _DESIRED_TABLE = None
    _HELD_TABLE = None

    @classmethod
    def _setup_engine(cls, db_path: str) -> None:
        if hasattr(sql, "connect"):  # stdlib sqlite3 branch
            cls._METADATA = MetaData()
            parent_dir = Path(db_path).parent
            if not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)

            cls._DESIRED_TABLE = Table("desired", cls._METADATA,
                                      autoload_with=cls._get_conn(), checkfirst=False)
            cls._HELD_TABLE = Table("held", cls._METADATA,
                                    autoload_with=cls._get_conn(), checkfirst=False)
            # Ensure columns exist or create if missing (simple fallback)
            with cls._get_conn() as conn:
                conn.execute(text("CREATE TABLE IF NOT EXISTS desired (symbol TEXT PRIMARY KEY, qty REAL NOT NULL, ts TEXT NOT NULL)"))
                conn.execute(text("CREATE TABLE IF NOT EXISTS held (symbol TEXT PRIMARY KEY, qty REAL NOT NULL, ts TEXT NOT NULL)"))
                conn.commit()
        else:  # sqlalchemy branch
            parent_dir = Path(db_path).parent
            if not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)
            engine = create_engine(f"sqlite:///{db_path}")
            MetaData().reflect(bind=engine)  # Reflect existing tables or fail cleanly
            cls._ENGINE = engine
            cls._METADATA = MetaData()

            desired = Table("desired", cls._METADATA, autoload_with=cls._ENGINE)
            held = Table("held", cls._METADATA, autoload_with=cls._ENGINE)
            cls._DESIRED_TABLE = desired
            cls._HELD_TABLE = held

    @classmethod
    def _get_conn(cls):
        return sql.connect(str(Path(DEFAULT_DB_PATH).absolute())) if hasattr(sql, "connect") else None

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        self.db_path = db_path
        self._setup_engine(db_path)
        # Re-setup with absolute path for relative calls if needed inside module
        self._setup_engine(str(Path(self.db_path).absolute()))

    def upsert_desired(self, symbol: str, qty: float, ts) -> None:
        ts_str = (ts.isoformat() if hasattr(ts, "isoformat") else ts)
        if hasattr(sql, "connect"):  # stdlib branch
            with self._get_conn() as conn:
                ins = sql.text(f"INSERT OR REPLACE INTO desired (symbol, qty, ts) VALUES ({symbol}, {qty}, '{ts_str}')")
                conn.execute(ins)
                conn.commit()
        else:  # sqlalchemy branch
            self._DESIRED_TABLE.insert().values(symbol=symbol, qty=qty, ts=ts_str).execute(self._ENGINE)

    def upsert_held(self, symbol: str, qty: float, ts) -> None:
        ts_str = (ts.isoformat() if hasattr(ts, "isoformat") else ts)
        if hasattr(sql, "connect"):  # stdlib branch
            with self._get_conn() as conn:
                ins = sql.text(f"INSERT OR REPLACE INTO held (symbol, qty, ts) VALUES ({symbol}, {qty}, '{ts_str}')")
                conn.execute(ins)
                conn.commit()
        else:  # sqlalchemy branch
            self._HELD_TABLE.insert().values(symbol=symbol, qty=qty, ts=ts_str).execute(self._ENGINE)

    def snapshot(self) -> dict[str, Any]:
        if hasattr(sql, "connect"):  # stdlib branch
            with self._get_conn() as conn:
                rows_des = conn.execute(sql.text("SELECT symbol, qty FROM desired ORDER BY symbol")).fetchall()
                rows_held = conn.execute(sql.text("SELECT symbol, qty FROM held ORDER BY symbol")).fetchall()

                d_map = {r[0]: r[1] for r in rows_des}
                h_map = {r[0]: r[1] for r in rows_held}

                all_keys = sorted(set(d_map.keys()) | set(h_map.keys()))
                drift_list = []
                for k in all_keys:
                    desired_val = d_map.get(k, 0.0)
                    held_val = h_map.get(k, 0.0)
                    drift_list.append({
                        "symbol": k,
                        "desired": desired_val,
                        "held": held_val,
                        "delta": desired_val - held_val
                    })

                return {
                    "desired": d_map,
                    "held": h_map,
                    "drift": drift_list
                }
        else:  # sqlalchemy branch
            with self._ENGINE.connect() as conn:
                rows_des = conn.execute(self._DESIRED_TABLE.select().order_by(self._DESIRED_TABLE.c.symbol)).fetchall()
                rows_held = conn.execute(self._HELD_TABLE.select().order_by(self._HELD_TABLE.c.symbol)).fetchall()

                d_map = {r[0]: r[1] for r in rows_des}
                h_map = {r[0]: r[1] for r in rows_held}

                all_keys = sorted(set(d_map.keys()) | set(h_map.keys()))
                drift_list = []
                for k in all_keys:
                    desired_val = d_map.get(k, 0.0)
                    held_val = h_map.get(k, 0.0)
                    drift_list.append({
                        "symbol": k,
                        "desired": desired_val,
                        "held": held_val,
                        "delta": desired_val - held_val
                    })

                return {
                    "desired": d_map,
                    "held": h_map,
                    "drift": drift_list
                }

    def sync_from_json(self, desired: dict[str, float], held: dict[str, float], ts: Optional[datetime] = None) -> None:
        if ts is None:
            ts = datetime.now(timezone.utc)
        for sym, qty in desired.items():
            self.upsert_desired(sym, qty, ts)
        for sym, qty in held.items():
            self.upsert_held(sym, qty, ts)


def cmd_paper_stack(db_path: Optional[str] = None) -> dict[str, Any]:
    """Return snapshot JSON-ready dict with orders_sent=0 (never sends broker orders)."""
    stack = PaperStack(db_path)
    snap = stack.snapshot()
    snap["orders_sent"] = 0
    return snap