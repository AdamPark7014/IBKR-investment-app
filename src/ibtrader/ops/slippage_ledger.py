from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_PATH = "data/slippage_ledger.jsonl"


def slip_bps(side: str, decision_px: float, fill_px: float) -> float:
    """Adverse slippage in bps: positive means worse than decision."""
    side_u = side.upper()
    d = float(decision_px)
    f = float(fill_px)
    if d <= 0 or f <= 0:
        return 0.0
    if side_u == "BUY":
        return (f / d - 1.0) * 1e4
    if side_u == "SELL":
        return (d / f - 1.0) * 1e4
    raise ValueError(f"side must be BUY or SELL, got {side!r}")


def record_slip(
    path: str | Path,
    *,
    symbol: str,
    side: str,
    decision_px: float,
    fill_px: float,
    qty: int,
    source: str = "sim",
) -> dict[str, Any]:
    """Append one fill vs decision row to JSONL at ``path``."""
    entry: dict[str, Any] = {
        "decision_ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side.upper(),
        "decision_px": float(decision_px),
        "fill_px": float(fill_px),
        "qty": int(qty),
        "slip_bps": slip_bps(side, decision_px, fill_px),
        "source": source,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
    return entry


def _read_entries(path: Path, window_days: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = row.get("decision_ts")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                rows.append(row)
    return rows


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_v = sorted(values)
    idx = min(len(sorted_v) - 1, int(round(0.95 * (len(sorted_v) - 1))))
    return float(sorted_v[idx])


def summarize(
    path: str | Path,
    window_days: int = 30,
    *,
    by_symbol: bool = False,
) -> dict[str, Any]:
    """Aggregate slippage over the last ``window_days``."""
    rows = _read_entries(Path(path), window_days)
    slips = [float(r["slip_bps"]) for r in rows if "slip_bps" in r]
    out: dict[str, Any] = {
        "n": len(slips),
        "mean_slip_bps": statistics.fmean(slips) if slips else None,
        "p95_slip_bps": _p95(slips),
    }
    if by_symbol:
        by_sym: dict[str, list[float]] = {}
        for r in rows:
            if "slip_bps" not in r:
                continue
            sym = str(r.get("symbol", ""))
            by_sym.setdefault(sym, []).append(float(r["slip_bps"]))
        out["by_symbol"] = {
            sym: {
                "n": len(vals),
                "mean_slip_bps": statistics.fmean(vals) if vals else None,
                "p95_slip_bps": _p95(vals),
            }
            for sym, vals in sorted(by_sym.items())
        }
    return out
