import sqlite3
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
import json

class PaperStack:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
        
    def _create_tables(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS desired (symbol TEXT PRIMARY KEY, qty REAL, ts TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS held (symbol TEXT PRIMARY KEY, qty REAL, ts TEXT)''')

    def upsert_desired(self, symbol: str, qty: float, ts: Optional[str] = None):
        if ts is None:
            ts = self._get_current_ts()
        self.cursor.execute("INSERT OR REPLACE INTO desired (symbol, qty, ts) VALUES (?, ?, ?)", (symbol, qty, ts))
        self.conn.commit()

    def upsert_held(self, symbol: str, qty: float, ts: Optional[str] = None):
        if ts is None:
            ts = self._get_current_ts()
        self.cursor.execute("INSERT OR REPLACE INTO held (symbol, qty, ts) VALUES (?, ?, ?)", (symbol, qty, ts))
        self.conn.commit()

    def _get_current_ts(self) -> str:
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def sync_from_dicts(self, desired: dict[str, float], held: dict[str, float]) -> None:
        for sym, qty in desired.items():
            self.upsert_desired(sym, qty)
        for sym, qty in held.items():
            self.upsert_held(sym, qty)

    def snapshot(self) -> dict:
        self.cursor.execute("SELECT symbol, qty, ts FROM desired ORDER BY symbol")
        rows = self.cursor.fetchall()
        d_rows = []
        h_rows = []
        drift = []
        for row in rows:
            d_rows.append({"symbol": row[0], "qty": row[1], "ts": row[2]})
        self.cursor.execute("SELECT symbol, qty, ts FROM held ORDER BY symbol")
        rows = self.cursor.fetchall()
        h_rows = [{"symbol": row[0], "qty": row[1], "ts": row[2]} for row in rows]
        if len(d_rows) == 0 and len(h_rows) == 0:
            return {"desired": {}, "held": {}, "drift": [], "orders_sent": 0}
        
        d_map = {r["symbol"]: r["qty"] for r in d_rows}
        h_map = {r["symbol"]: r["qty"] for r in h_rows}
        all_syms = sorted(list(set(d_map.keys()) | set(h_map.keys())))
        drift_list = []
        total_orders_sent = 0
        
        for sym in all_syms:
            d_qty = d_map.get(sym, 0.0)
            h_qty = h_map.get(sym, 0.0)
            delta = h_qty - d_qty
            if delta < 0 and self._check_order_limit():
                # This is a simplified logic for 'orders_sent' counter simulation based on negative drift (need to buy)
                pass 
            drift_list.append({"symbol": sym, "desired": d_qty, "held": h_qty, "delta": delta})
            
        return {"desired": d_rows, "held": h_rows, "drift": drift_list, "orders_sent": total_orders_sent}

    def _check_order_limit(self) -> bool:
        # Placeholder for actual broker limit check logic if desired
        return True