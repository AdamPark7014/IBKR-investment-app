"""Universe loader: cache -> provider chain -> loud validation -> vintage snapshot -> cache.

Fail-loud contract (audit P1-4, playbook phase 1):
  - every provider failure or rejected payload is logged with its reason and the next provider is tried;
  - a symbol for which *all* providers fail raises ``SymbolLoadError`` (all reasons attached) and is
    excluded from the result with an ERROR log;
  - if no symbol survives, ``load_universe_v2`` raises instead of returning an empty dict;
  - nothing that failed validation is ever written to the cache or to a vintage.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyarrow as pa

from ..config import AppSettings
from .cache import load_from_cache, load_lineage, save_lineage, save_to_cache
from .lineage import DataFrameWithMeta, DataLineage
from .providers import (
    DataQualityGate,
    FixtureProvider,
    IBKRProvider,
    MarketDataProvider,
    StooqProvider,
    TiingoProvider,
    YahooProvider,
)
from .universe import UniverseSpec, load_universe_spec
from .validators import validate_pit
from .vintage import write_vintage

log = logging.getLogger("ibtrader.data.service")

# Sources whose cached frames may be served without re-fetching. "fixture" is CI-only and always re-read.
CACHEABLE_SOURCES = frozenset({"yahoo", "stooq", "ibkr", "tiingo"})
# Sources that never enter the vintage store: the fixture is synthetic test data and a `pytest` run must not
# overwrite (or masquerade as) the real snapshot of the same day. Logged, not silent.
NON_VINTAGE_SOURCES = frozenset({"fixture"})


class SymbolLoadError(RuntimeError):
    """Every provider failed (or its data was rejected) for one symbol; ``reasons`` keeps all of them."""

    def __init__(self, symbol: str, reasons: List[str]) -> None:
        self.symbol = symbol
        self.reasons = list(reasons)
        super().__init__(f"{symbol}: " + " | ".join(self.reasons))


def build_provider_chain(settings: AppSettings) -> List[Tuple[str, MarketDataProvider]]:
    """Instantiate ``settings.data.providers`` in order. Tiingo without token is skipped with a WARNING."""
    chain: List[Tuple[str, MarketDataProvider]] = []
    for raw in settings.data.providers:
        name = raw.strip().lower()
        if name == "tiingo":
            if not settings.data.tiingo_token.strip():
                log.warning("tiingo_disabled reason='DATA__TIINGO_TOKEN vacío'; se omite el proveedor")
                continue
            chain.append((name, TiingoProvider(settings.data.tiingo_token)))
        elif name == "yahoo":
            chain.append((name, YahooProvider()))
        elif name == "stooq":
            chain.append((name, StooqProvider()))
        elif name == "ibkr":
            chain.append(
                (
                    name,
                    IBKRProvider(host=settings.ib.host, port=settings.ib.paper_port, client_id=settings.ib.client_id),
                )
            )
        elif name == "fixture":
            chain.append((name, FixtureProvider()))
        else:
            log.warning("provider_desconocido name=%s; se ignora", raw)
    if not chain:
        raise RuntimeError(f"Ningún proveedor de datos utilizable en data.providers={list(settings.data.providers)}")
    return chain


def _load_spec(settings: AppSettings) -> Optional[UniverseSpec]:
    if not settings.data.universe_file:
        return None
    spec = load_universe_spec(settings.data.universe_file)
    log.info(
        "universe_spec_loaded name=%s symbols=%s file=%s", spec.name, len(spec.entries), settings.data.universe_file
    )
    return spec


def _clip(spec: Optional[UniverseSpec], symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    if spec is None:
        return df
    clipped, _report = spec.clip_to_lifecycle(symbol, df)
    return clipped


def _validation_reasons(
    settings: AppSettings, gate: DataQualityGate, symbol: str, df: pd.DataFrame, lineage: DataLineage, today: date
) -> List[str]:
    """Gate (strict schema + min rows) and point-in-time checks; returns every reason, empty when clean."""
    reasons: List[str] = []
    try:
        gate.validate(DataFrameWithMeta(df, lineage))
    except RuntimeError as e:
        reasons.append(str(e))
    ok, pit_reasons = validate_pit(
        df,
        symbol,
        max_price_spike_pct=settings.data.max_price_spike_pct,
        reject_future_bars=settings.data.reject_future_bars,
        today=today,
    )
    if not ok:
        reasons.extend(pit_reasons)
    return reasons


def _cached_candidate(
    settings: AppSettings, gate: DataQualityGate, spec: Optional[UniverseSpec], symbol: str, today: date
) -> Optional[pd.DataFrame]:
    """Serve the cache only when lineage, freshness and validation all agree; log why when they do not."""
    bar = settings.engine.bar_size
    cached = load_from_cache(settings.data.cache_dir, symbol, bar)
    if cached is None or cached.empty:
        return None
    reasons: List[str] = []
    meta = load_lineage(settings.data.cache_dir, symbol, bar)
    if meta is None:
        reasons.append("sin linaje (.meta.json ausente o inválido)")
    elif (meta.source or "").lower() not in CACHEABLE_SOURCES:
        reasons.append(f"fuente no cacheable: {meta.source!r}")
    last_ts = pd.Timestamp(cached.index.max())
    if last_ts.tzinfo is not None:
        last_ts = last_ts.tz_convert("UTC").tz_localize(None)
    age_days = (pd.Timestamp(today) - last_ts.normalize()).days
    max_age = max(settings.data.max_cache_age_days, 1)
    if age_days > max_age:
        reasons.append(f"caché vencida: última barra {last_ts.date()} ({age_days} días > {max_age})")
    candidate = _clip(spec, symbol, cached)
    if meta is not None:
        reasons.extend(_validation_reasons(settings, gate, symbol, candidate, meta, today))
    if reasons:
        log.warning("cache_rechazada symbol=%s reasons=%s", symbol, " | ".join(reasons))
        return None
    log.info(
        "cache_hit symbol=%s rows=%s last_bar=%s source=%s",
        symbol,
        len(candidate),
        last_ts.date(),
        meta.source if meta else None,
    )
    return candidate


def _fetch_symbol(
    settings: AppSettings,
    gate: DataQualityGate,
    spec: Optional[UniverseSpec],
    chain: List[Tuple[str, MarketDataProvider]],
    symbol: str,
    start_s: str,
    end_s: str,
    today: date,
) -> DataFrameWithMeta:
    """Walk the provider chain; the first provider whose data passes every check wins."""
    reasons: List[str] = []
    for name, prov in chain:
        try:
            dfm = prov.fetch_daily_ohlcv(symbol, start=start_s, end=end_s)
        except Exception as e:  # provider boundary: any failure becomes a recorded reason, never silence
            reason = f"{name}: {type(e).__name__}: {e}"
            reasons.append(reason)
            log.warning("provider_failed symbol=%s provider=%s reason=%s", symbol, name, e)
            continue
        df = _clip(spec, symbol, dfm.data)
        bad = _validation_reasons(settings, gate, symbol, df, dfm.lineage, today)
        if bad:
            reasons.append(f"{name}: " + "; ".join(bad))
            log.warning("provider_data_rechazada symbol=%s provider=%s reasons=%s", symbol, name, " | ".join(bad))
            continue
        return DataFrameWithMeta(df, dfm.lineage)
    raise SymbolLoadError(symbol, reasons or ["sin proveedores en la cadena"])


def _persist(settings: AppSettings, symbol: str, dfm: DataFrameWithMeta) -> DataLineage:
    """Vintage first (loud on failure), then cache + sidecar (logged on failure, never blocks a valid load)."""
    bar = settings.engine.bar_size
    lineage = dfm.lineage
    if settings.data.write_manifest:
        if (lineage.source or "").lower() in NON_VINTAGE_SOURCES:
            log.info("vintage_skipped symbol=%s source=%s reason='datos de prueba, no entran al almacén PIT'",
                     symbol, lineage.source)
        else:
            rec = write_vintage(settings.data.vintage_dir, symbol, bar, dfm.data, provider=lineage.source)
            lineage = replace(lineage, vintage_date=rec.vintage_date, vintage_path=rec.path, sha256=rec.sha256)
    try:
        save_to_cache(settings.data.cache_dir, symbol, bar, dfm.data)
        save_lineage(settings.data.cache_dir, symbol, bar, lineage)
    except (OSError, ValueError, pa.ArrowException) as e:
        log.error(
            "cache_write_failed symbol=%s dir=%s reason=%s: %s", symbol, settings.data.cache_dir, type(e).__name__, e
        )
    return lineage


def load_universe_v2(settings: AppSettings) -> Dict[str, pd.DataFrame]:
    spec = _load_spec(settings)
    chain = build_provider_chain(settings)
    gate = DataQualityGate(min_rows=min(252, settings.engine.history_days))
    end_dt = datetime.now(timezone.utc)
    today = end_dt.date()
    start_s = str((end_dt - timedelta(days=settings.engine.history_days)).date())
    end_s = str(today)
    out: Dict[str, pd.DataFrame] = {}
    failures: Dict[str, List[str]] = {}
    for sym in settings.universe.symbols:
        if settings.engine.use_cache:
            cached = _cached_candidate(settings, gate, spec, sym, today)
            if cached is not None:
                out[sym] = cached
                continue
        try:
            dfm = _fetch_symbol(settings, gate, spec, chain, sym, start_s, end_s, today)
        except SymbolLoadError as e:
            failures[sym] = e.reasons
            log.error("symbol_excluido symbol=%s reasons=%s", sym, " | ".join(e.reasons))
            continue
        _persist(settings, sym, dfm)
        out[sym] = dfm.data
    if not out:
        detail = "; ".join(f"{s}: {' | '.join(r)}" for s, r in failures.items()) or "universo vacío"
        raise RuntimeError(f"Ningún símbolo cargó ({len(failures)} fallaron): {detail}")
    if failures:
        log.error("universe_parcial loaded=%s excluded=%s", sorted(out), sorted(failures))
    return out

