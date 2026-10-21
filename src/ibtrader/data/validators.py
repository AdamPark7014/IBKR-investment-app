from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def validate_timeseries_strict(df: pd.DataFrame) -> Tuple[bool, str]:
    if df.empty:
        return False, "DataFrame vacío."
    if df.index.has_duplicates:
        return False, "Índice con duplicados."
    if not df.index.is_monotonic_increasing:
        return False, "Índice no es estrictamente creciente."
    # Require standard OHLCV columns to exist when present and not contain NaNs row-wise
    required = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    if not required:
        return False, "Faltan columnas OHLCV."
    if df[required].isna().any(axis=1).any():
        return False, "Filas con valores OHLCV faltantes."
    if df[required].isna().all().any():
        return False, "Columnas enteras vacías."
    return True, "OK"


def _index_as_naive_utc(idx: pd.Index) -> pd.DatetimeIndex:
    """Return the index as tz-naive UTC timestamps (tz-aware indexes are converted, naive are assumed UTC)."""
    didx = pd.DatetimeIndex(idx)
    if didx.tz is not None:
        didx = didx.tz_convert("UTC").tz_localize(None)
    return didx


def _fmt_dates(values: "pd.Index | List[pd.Timestamp]", limit: int = 5) -> str:
    items = [str(pd.Timestamp(v).date()) for v in list(values)[:limit]]
    extra = len(values) - len(items)
    return ", ".join(items) + (f" (+{extra} más)" if extra > 0 else "")


def validate_pit(
    df: pd.DataFrame,
    symbol: str,
    *,
    max_price_spike_pct: float,
    reject_future_bars: bool,
    today: Optional[date] = None,
) -> Tuple[bool, List[str]]:
    """Point-in-time validation that collects *every* reason instead of stopping at the first one.

    Checks (playbook phase 1, audit P1-4):
      - empty frame / non-datetime index
      - duplicated or non-monotonic index
      - missing OHLCV columns or NaN inside them
      - non-positive close
      - bars dated after ``today`` (UTC) when ``reject_future_bars``
      - day-over-day close jumps above ``max_price_spike_pct`` (0 disables the check)

    Returns ``(ok, reasons)``; ``reasons`` is empty when ``ok``.
    """
    reasons: List[str] = []
    if df is None or df.empty:
        return False, [f"{symbol}: DataFrame vacío"]
    try:
        idx = _index_as_naive_utc(df.index)
    except (TypeError, ValueError) as e:
        return False, [f"{symbol}: índice no es de fechas ({e})"]

    if idx.has_duplicates:
        dups = idx[idx.duplicated()]
        reasons.append(f"{symbol}: {len(dups)} fechas duplicadas: {_fmt_dates(dups)}")
    if not idx.is_monotonic_increasing:
        reasons.append(f"{symbol}: índice no monótono creciente")

    present = [c for c in OHLCV_COLUMNS if c in df.columns]
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        reasons.append(f"{symbol}: faltan columnas OHLCV: {missing}")
    if present:
        nan_mask = df[present].isna().any(axis=1)
        if bool(nan_mask.any()):
            bad = idx[nan_mask.to_numpy()]
            reasons.append(f"{symbol}: {int(nan_mask.sum())} filas con NaN en OHLCV: {_fmt_dates(bad)}")

    if "close" in df.columns:
        close = pd.to_numeric(df["close"], errors="coerce").astype(float)
        nonpos = close <= 0
        if bool(nonpos.any()):
            reasons.append(f"{symbol}: {int(nonpos.sum())} cierres <= 0: {_fmt_dates(idx[nonpos.to_numpy()])}")
        if max_price_spike_pct and max_price_spike_pct > 0 and len(close) > 1:
            # Sort by index for the spike check so a non-monotonic frame does not fabricate jumps.
            order = np.argsort(idx.values, kind="stable")
            close_sorted = close.to_numpy()[order]
            idx_sorted = idx[order]
            with np.errstate(divide="ignore", invalid="ignore"):
                pct = np.abs(np.diff(close_sorted) / close_sorted[:-1]) * 100.0
            spike_mask = np.isfinite(pct) & (pct > float(max_price_spike_pct))
            if bool(spike_mask.any()):
                where = np.nonzero(spike_mask)[0]
                sample = ", ".join(
                    f"{pd.Timestamp(idx_sorted[i + 1]).date()} ({pct[i]:.1f}%)" for i in where[:5]
                )
                extra = f" (+{len(where) - 5} más)" if len(where) > 5 else ""
                reasons.append(
                    f"{symbol}: {len(where)} saltos de cierre > {max_price_spike_pct:g}% día a día: {sample}{extra}"
                )

    if reject_future_bars:
        today_d = today or datetime.now(timezone.utc).date()
        cutoff = pd.Timestamp(today_d)
        future_mask = idx.normalize() > cutoff
        if bool(future_mask.any()):
            reasons.append(
                f"{symbol}: {int(future_mask.sum())} barras con fecha futura (> {today_d}): "
                f"{_fmt_dates(idx[future_mask])}"
            )

    return (len(reasons) == 0), reasons

