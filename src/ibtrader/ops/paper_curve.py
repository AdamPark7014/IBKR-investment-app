"""Paper equity curve. Zero broker orders.

Equity is money: ``cash + Σ shares · price`` from ``data/paper_account.json`` (the paper book,
``{"cash": 100000.0, "shares": {"SPY": 120}}``) or a NAV read from the broker and appended by
hand (``ibtrader paper-equity --append``). ``data/paper_positions.json`` holds **target weights**
for drift triage and is never valued as equity: ``Σ weight · price`` is not money and turned a
weight cut from 1.0 to 0.5 into a fake 50 % drawdown.

Each point carries a ``basis``: ``cash+shares`` or ``nav`` are real equity (``REAL_BASES``);
points without a basis are legacy and never feed the kill alerts.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

__all__ = [
    "BASIS_CASH_SHARES",
    "BASIS_NAV",
    "MIN_POINTS_FOR_KILL",
    "REAL_BASES",
    "account_equity",
    "append_daily_equity_point",
    "append_equity_point",
    "estimate_mark_to_market",
    "load_equity_points",
    "load_paper_account",
    "max_drawdown",
    "paper_max_drawdown",
]

BASIS_CASH_SHARES = "cash+shares"
BASIS_NAV = "nav"
REAL_BASES = (BASIS_CASH_SHARES, BASIS_NAV)
#: Daily points of real paper equity before a drawdown may recommend killing the system.
MIN_POINTS_FOR_KILL = 20

_TS_ALIASES = ("ts", "timestamp", "t", "as_of", "time")
_EQUITY_ALIASES = ("equity", "nav", "value")


def load_equity_points(path: str | Path, *, bases: Optional[Iterable[str]] = None) -> list[dict]:
    """``[{ts, equity, basis}]`` from a JSONL file; ``bases`` keeps only points with those bases."""
    p = Path(path)
    if not p.is_file():
        return []
    wanted = set(bases) if bases is not None else None

    points: list[dict[str, Any]] = []
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue

                ts_val = None
                for key in _TS_ALIASES:
                    if key in obj:
                        ts_val = obj[key]
                        break
                equity_raw = None
                for key in _EQUITY_ALIASES:
                    if key in obj:
                        equity_raw = obj[key]
                        break
                if ts_val is None or equity_raw is None:
                    continue
                try:
                    equity = float(equity_raw)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(equity) or equity <= 0:
                    continue
                basis = obj.get("basis")
                if wanted is not None and basis not in wanted:
                    continue
                points.append({"ts": str(ts_val), "equity": equity, "basis": basis})
    except OSError:
        return []
    return points


def max_drawdown(equities: list[float]) -> float | None:
    if len(equities) < 2:
        return None

    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def paper_max_drawdown(path: str | Path, *, bases: Optional[Iterable[str]] = None) -> float | None:
    equities = [pt["equity"] for pt in load_equity_points(path, bases=bases)]
    return max_drawdown(equities)


def _valid_equity(equity: Any) -> Optional[float]:
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(eq) or eq <= 0:
        return None
    return eq


def append_equity_point(path: str | Path, equity: float, ts: str | None = None, basis: str | None = None) -> None:
    """Append one JSONL ``{ts, equity[, basis]}`` line. Skip non-finite or non-positive equity."""
    eq = _valid_equity(equity)
    if eq is None:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if ts is None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row: dict[str, Any] = {"ts": str(ts), "equity": eq}
    if basis is not None:
        row["basis"] = str(basis)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_daily_equity_point(path: str | Path, equity: float, day: str, basis: str) -> bool:
    """One point per market day: a second run on the same ``day`` replaces that day's point.

    Weekends and re-runs therefore do not stack duplicate points. Returns True when written.
    """
    eq = _valid_equity(equity)
    if eq is None:
        return False
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    day = str(day)[:10]
    lines = p.read_text(encoding="utf-8").splitlines() if p.is_file() else []
    if lines:
        try:
            last = json.loads(lines[-1])
        except json.JSONDecodeError:
            last = None
        if isinstance(last, dict) and str(last.get("ts", ""))[:10] == day:
            lines = lines[:-1]
    lines.append(json.dumps({"ts": day, "equity": eq, "basis": str(basis)}, ensure_ascii=False))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def load_paper_account(path: str | Path) -> Optional[dict[str, Any]]:
    """``{"cash": float, "shares": {sym: qty}}`` from ``paper_account.json``; None if absent or invalid.

    ``cash`` is mandatory: without it the book cannot be valued (a positions-only file is not equity).
    """
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or "cash" not in raw:
        return None
    try:
        cash = float(raw["cash"])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cash):
        return None
    shares_raw = raw.get("shares") or {}
    if not isinstance(shares_raw, dict):
        return None
    shares: dict[str, float] = {}
    for sym, qty in shares_raw.items():
        try:
            q = float(qty)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(q):
            return None
        shares[str(sym)] = q
    return {"cash": cash, "shares": shares}


def account_equity(
    account: Mapping[str, Any], last_prices: Mapping[str, float]
) -> tuple[Optional[float], list[str]]:
    """``cash + Σ shares · price``. Any held symbol without a price → ``(None, missing)``: a partial
    valuation would look like a loss."""
    cash = float(account.get("cash", 0.0))
    total = cash
    missing: list[str] = []
    for sym, qty in dict(account.get("shares") or {}).items():
        q = float(qty)
        if q == 0.0:
            continue
        px = (last_prices or {}).get(sym)
        if px is None or not math.isfinite(float(px)) or float(px) <= 0:
            missing.append(str(sym))
            continue
        total += q * float(px)
    if missing:
        return None, sorted(missing)
    return total, []


def estimate_mark_to_market(
    held: dict[str, float],
    last_prices: dict[str, float],
    cash: float = 0.0,
) -> float | None:
    """``cash + Σ qty*price`` for priced holdings (``qty`` in **shares**); None if nothing priced and cash≤0.

    Never pass target weights here (``paper_positions.json``): use ``load_paper_account`` +
    ``account_equity``.
    """
    total = float(cash)
    priced = False
    for sym, qty in (held or {}).items():
        px = (last_prices or {}).get(sym)
        if px is None:
            continue
        try:
            total += float(qty) * float(px)
            priced = True
        except (TypeError, ValueError):
            continue
    if not priced and total <= 0:
        return None
    return total
