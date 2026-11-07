"""Data freshness and cross-source reconciliation (audit 2026-11-07, §3.1 and §5 step 1).

Two fail-closed checks before any order is generated:

* **Freshness**: every symbol's last bar must be the last completed NYSE session. After the
  close (16:00 ET + ``grace_minutes``) that is today if today is a trading day; otherwise the
  previous trading day. A stale symbol blocks the run ("never trade on yesterday's data").
* **Cross-source**: the last close of each symbol from a second provider must agree with the
  primary within ``tol_bps``. Providers disagree on adjustments, so only the most recent
  ``lookback`` common dates are compared, where adjustments rarely differ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from ..execution.session import is_trading_day, session_close

ET = ZoneInfo("America/New_York")


def last_completed_session(now: datetime, grace_minutes: int = 30) -> date:
    """Most recent NYSE session whose close (+ grace) is at or before ``now``."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    now_et = now.astimezone(ET)
    d = now_et.date()
    if is_trading_day(d):
        close = datetime.combine(d, session_close(d), tzinfo=ET) + timedelta(minutes=grace_minutes)
        if now_et >= close:
            return d
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


@dataclass
class DataCheck:
    ok: bool
    expected_session: Optional[str] = None
    stale: Dict[str, Optional[str]] = field(default_factory=dict)
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "expected_session": self.expected_session, "stale": self.stale,
                "mismatches": self.mismatches, "reasons": list(self.reasons)}


def _last_date(df: pd.DataFrame) -> Optional[date]:
    if df is None or len(df) == 0:
        return None
    return pd.Timestamp(df.index.max()).date()


def check_freshness(frames: Mapping[str, pd.DataFrame], now: datetime, grace_minutes: int = 30) -> DataCheck:
    expected = last_completed_session(now, grace_minutes)
    res = DataCheck(ok=True, expected_session=expected.isoformat())
    for sym, df in frames.items():
        last = _last_date(df)
        if last is None or last < expected:
            res.stale[sym] = last.isoformat() if last else None
    if res.stale:
        res.ok = False
        res.reasons.append(f"stale_data: {sorted(res.stale)} last bar < {expected.isoformat()}")
    return res


def _close(df: pd.DataFrame) -> pd.Series:
    for col in ("close", "Close", "adj_close", "Adj Close"):
        if col in df.columns:
            return pd.Series(df[col], dtype=float)
    raise KeyError("no close column")


def cross_check(
    primary: Mapping[str, pd.DataFrame],
    secondary: Mapping[str, pd.DataFrame],
    *,
    tol_bps: float = 20.0,
    lookback: int = 1,
    require_secondary: bool = False,
) -> DataCheck:
    res = DataCheck(ok=True)
    for sym, dfp in primary.items():
        dfs = secondary.get(sym)
        if dfs is None or len(dfs) == 0:
            if require_secondary:
                res.ok = False
                res.reasons.append(f"secondary_missing: {sym}")
            continue
        a, b = _close(dfp), _close(dfs)
        a.index = pd.to_datetime(a.index).normalize()
        b.index = pd.to_datetime(b.index).normalize()
        common = a.index.intersection(b.index).sort_values()[-int(lookback):]
        if len(common) == 0:
            res.ok = False
            res.reasons.append(f"no_common_dates: {sym}")
            continue
        for ts in common:
            pa, pb = float(a.loc[ts]), float(b.loc[ts])
            if not (pa > 0 and pb > 0 and math.isfinite(pa) and math.isfinite(pb)):
                diff = float("inf")
            else:
                diff = abs(pa / pb - 1.0) * 1e4
            if diff > tol_bps:
                res.mismatches.append({"symbol": sym, "date": ts.date().isoformat(), "primary": pa,
                                       "secondary": pb, "diff_bps": diff})
    if res.mismatches:
        res.ok = False
        res.reasons.append(f"cross_source_mismatch: {len(res.mismatches)} > {tol_bps} bp")
    return res


__all__ = ["DataCheck", "check_freshness", "cross_check", "last_completed_session"]
