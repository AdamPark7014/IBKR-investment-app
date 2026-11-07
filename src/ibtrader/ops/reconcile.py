"""Book vs broker reconciliation and the paper book update (audit 2026-11-07, §5 step 6).

The internal book is ``data/paper_account.json`` (``{"cash": float, "shares": {sym: qty}}``),
the same file the paper curve already reads. After each run:

* **shadow** mode: the book is advanced with the orders as if filled at the decision price
  minus the modelled cost (``apply_fills``). Optimistic on purpose and labelled as such.
* **orders** mode: the expected book (previous book + real fills) is compared with what IBKR
  reports (``reconcile``). Any share difference, or cash off by more than the tolerance, is a
  break: the caller activates the kill switch and alerts. When it matches, the book is
  overwritten with the broker's numbers (the broker is the source of truth for money).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


@dataclass
class Fill:
    symbol: str
    side: str  # BUY | SELL
    qty: int
    price: float
    cost: float = 0.0  # commission + fees in USD


@dataclass
class ReconcileResult:
    ok: bool
    share_diffs: List[Dict[str, Any]] = field(default_factory=list)
    cash_diff: Optional[float] = None
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "share_diffs": self.share_diffs, "cash_diff": self.cash_diff,
                "reasons": list(self.reasons)}


def load_book(path: str | Path) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or "cash" not in raw:
        return None
    shares = {str(k).upper(): int(v) for k, v in dict(raw.get("shares") or {}).items() if int(v) != 0}
    return {"cash": float(raw["cash"]), "shares": shares, **{k: v for k, v in raw.items()
                                                             if k not in ("cash", "shares")}}


def save_book(path: str | Path, book: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(book), indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(p)  # atomic on the same volume: a crash never leaves half a book


def apply_fills(book: Mapping[str, Any], fills: Iterable[Fill]) -> Dict[str, Any]:
    cash = float(book.get("cash") or 0.0)
    shares: Dict[str, int] = {str(k).upper(): int(v) for k, v in dict(book.get("shares") or {}).items()}
    for f in fills:
        sign = 1 if f.side.upper() == "BUY" else -1
        shares[f.symbol.upper()] = shares.get(f.symbol.upper(), 0) + sign * int(f.qty)
        cash -= sign * int(f.qty) * float(f.price)
        cash -= float(f.cost)
    out = {k: v for k, v in book.items() if k not in ("cash", "shares")}
    out["cash"] = cash
    out["shares"] = {k: v for k, v in sorted(shares.items()) if v != 0}
    return out


def reconcile(
    expected: Mapping[str, Any],
    broker_shares: Mapping[str, int],
    broker_cash: Optional[float] = None,
    *,
    cash_tolerance_usd: float = 25.0,
) -> ReconcileResult:
    exp_sh = {str(k).upper(): int(v) for k, v in dict(expected.get("shares") or {}).items() if int(v) != 0}
    brk_sh = {str(k).upper(): int(v) for k, v in dict(broker_shares).items() if int(v) != 0}
    res = ReconcileResult(ok=True)
    for sym in sorted(set(exp_sh) | set(brk_sh)):
        e, b = exp_sh.get(sym, 0), brk_sh.get(sym, 0)
        if e != b:
            res.share_diffs.append({"symbol": sym, "expected": e, "broker": b, "delta": b - e})
    if res.share_diffs:
        res.ok = False
        res.reasons.append(f"share_mismatch: {len(res.share_diffs)} symbol(s)")
    if broker_cash is not None and expected.get("cash") is not None:
        res.cash_diff = float(broker_cash) - float(expected["cash"])
        if abs(res.cash_diff) > cash_tolerance_usd:
            res.ok = False
            res.reasons.append(f"cash_mismatch: {res.cash_diff:+.2f} USD > ±{cash_tolerance_usd:.2f}")
    return res


__all__ = ["Fill", "ReconcileResult", "apply_fills", "load_book", "reconcile", "save_book"]
