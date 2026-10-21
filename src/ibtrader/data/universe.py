from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

log = logging.getLogger("ibtrader.data.universe")


@dataclass
class Watchlist:
    symbols: List[str]
    benchmark: str = "SPY"


def load_watchlist(path: str) -> Watchlist:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    syms = list(dict.fromkeys(list(data.get("symbols", []) or [])))
    bench = data.get("benchmark", "SPY")
    return Watchlist(symbols=syms, benchmark=bench)


# --------------------------------------------------------------------------------------
# Universe with lifecycle (playbook phase 1): listed_from / delisted_on per symbol so a
# backtest never sees bars the instrument could not have traded, and delisted names stay
# in the history instead of silently vanishing (survivorship bias).
# --------------------------------------------------------------------------------------


def _parse_date(value: Any, field_name: str, symbol: str) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as e:
        raise ValueError(f"Universo: {symbol}.{field_name}={value!r} no es una fecha ISO (YYYY-MM-DD): {e}") from e


@dataclass(frozen=True)
class UniverseEntry:
    symbol: str
    asset_class: str
    box: str
    listed_from: Optional[date] = None
    delisted_on: Optional[date] = None
    spread_bps: Optional[float] = None
    notes: Optional[str] = None

    def is_active(self, as_of: date) -> bool:
        if self.listed_from is not None and as_of < self.listed_from:
            return False
        if self.delisted_on is not None and as_of > self.delisted_on:
            return False
        return True


@dataclass(frozen=True)
class LifecycleClip:
    symbol: str
    removed_before: int
    removed_after: int
    listed_from: Optional[date]
    delisted_on: Optional[date]

    @property
    def removed(self) -> int:
        return self.removed_before + self.removed_after


@dataclass
class UniverseSpec:
    name: str
    entries: List[UniverseEntry] = field(default_factory=list)
    as_of: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for e in self.entries:
            key = e.symbol.upper()
            if key in seen:
                raise ValueError(f"Universo {self.name}: símbolo duplicado {e.symbol}")
            seen.add(key)

    @property
    def symbols(self) -> List[str]:
        return [e.symbol for e in self.entries]

    def get(self, symbol: str) -> Optional[UniverseEntry]:
        key = symbol.upper()
        for e in self.entries:
            if e.symbol.upper() == key:
                return e
        return None

    def boxes(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for e in self.entries:
            out.setdefault(e.box, []).append(e.symbol)
        return out

    def active_symbols(self, as_of: "date | str") -> List[str]:
        as_of_d = _parse_date(as_of, "as_of", "universe") or date.today()
        return [e.symbol for e in self.entries if e.is_active(as_of_d)]

    def clip_to_lifecycle(self, symbol: str, df: pd.DataFrame) -> Tuple[pd.DataFrame, LifecycleClip]:
        """Drop bars before ``listed_from`` and after ``delisted_on``; report how many were removed.

        A symbol missing from the spec is returned untouched with a WARNING: we cannot vouch for
        its lifecycle, and hiding that would be the silent failure the audit forbids.
        """
        entry = self.get(symbol)
        if entry is None:
            log.warning("universe_symbol_sin_ciclo_de_vida symbol=%s universe=%s", symbol, self.name)
            return df, LifecycleClip(symbol, 0, 0, None, None)
        return clip_to_lifecycle(entry, df)


def clip_to_lifecycle(entry: UniverseEntry, df: pd.DataFrame) -> Tuple[pd.DataFrame, LifecycleClip]:
    if df is None or df.empty:
        return df, LifecycleClip(entry.symbol, 0, 0, entry.listed_from, entry.delisted_on)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    keep = pd.Series(True, index=range(len(idx)))
    removed_before = 0
    removed_after = 0
    if entry.listed_from is not None:
        before = idx.normalize() < pd.Timestamp(entry.listed_from)
        removed_before = int(before.sum())
        keep &= ~pd.Series(before)
    if entry.delisted_on is not None:
        after = idx.normalize() > pd.Timestamp(entry.delisted_on)
        removed_after = int(after.sum())
        keep &= ~pd.Series(after)
    clip = LifecycleClip(entry.symbol, removed_before, removed_after, entry.listed_from, entry.delisted_on)
    if clip.removed:
        log.info(
            "universe_clip symbol=%s removed_before=%s removed_after=%s listed_from=%s delisted_on=%s rows_left=%s",
            entry.symbol,
            removed_before,
            removed_after,
            entry.listed_from,
            entry.delisted_on,
            int(keep.sum()),
        )
        return df.loc[keep.to_numpy()], clip
    return df, clip


def active_symbols(spec: UniverseSpec, as_of: "date | str") -> List[str]:
    return spec.active_symbols(as_of)


def _entry_from_dict(raw: Dict[str, Any]) -> UniverseEntry:
    sym = str(raw.get("symbol") or "").strip()
    if not sym:
        raise ValueError(f"Universo: entrada sin 'symbol': {raw}")
    for required in ("asset_class", "box"):
        if not raw.get(required):
            raise ValueError(f"Universo: {sym} sin '{required}'")
    spread = raw.get("spread_bps")
    return UniverseEntry(
        symbol=sym.upper(),
        asset_class=str(raw["asset_class"]),
        box=str(raw["box"]),
        listed_from=_parse_date(raw.get("listed_from"), "listed_from", sym),
        delisted_on=_parse_date(raw.get("delisted_on"), "delisted_on", sym),
        spread_bps=float(spread) if spread is not None else None,
        notes=str(raw["notes"]) if raw.get("notes") is not None else None,
    )


def load_universe_spec(path: "str | Path") -> UniverseSpec:
    """Load a universe JSON (or YAML) file.

    Shape: ``{name, as_of, source, notes, symbols: [{symbol, asset_class, box, listed_from, delisted_on, ...}]}``.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Universo no encontrado: {p}")
    text = p.read_text(encoding="utf-8")
    data: Any
    if p.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Universo {p}: el documento raíz debe ser un objeto")
    raw_entries = data.get("symbols") or data.get("entries") or []
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError(f"Universo {p}: 'symbols' vacío o inválido")
    entries = [_entry_from_dict(e) for e in raw_entries if isinstance(e, dict)]
    return UniverseSpec(
        name=str(data.get("name") or p.stem),
        entries=entries,
        as_of=str(data["as_of"]) if data.get("as_of") else None,
        source=str(data["source"]) if data.get("source") else None,
        notes=str(data["notes"]) if data.get("notes") else None,
    )

