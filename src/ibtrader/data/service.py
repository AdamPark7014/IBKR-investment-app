from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import pandas as pd

from ..config import AppSettings
from .cache import load_from_cache, load_lineage, save_lineage, save_to_cache
from .lineage import DataFrameWithMeta
from .providers import DataQualityGate, FixtureProvider, IBKRProvider, StooqProvider, YahooProvider


def load_universe_v2(settings: AppSettings) -> Dict[str, pd.DataFrame]:
    # Providers order via settings.data.providers; default set in config is ["yahoo", "stooq"]
    prov_map = {
        "yahoo": lambda: YahooProvider(),
        "stooq": lambda: StooqProvider(),
        "ibkr": lambda: IBKRProvider(
            host=settings.ib.host, port=settings.ib.paper_port, client_id=settings.ib.client_id
        ),
        "fixture": lambda: FixtureProvider(),
    }
    provider_chain: List[Tuple[str, object]] = []
    for name in settings.data.providers:
        fac = prov_map.get(name.lower())
        if fac is not None:
            provider_chain.append((name.lower(), fac()))
    gate = DataQualityGate(min_rows=min(252, settings.engine.history_days))
    out: Dict[str, pd.DataFrame] = {}
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=settings.engine.history_days)
    start_s = str(start_dt.date())
    end_s = str(end_dt.date())
    for sym in settings.universe.symbols:
        # Cache check + validation
        if settings.engine.use_cache:
            cached = load_from_cache(settings.data.cache_dir, sym, settings.engine.bar_size)
            if cached is not None and not cached.empty and len(cached) >= gate.min_rows:
                meta = load_lineage(settings.data.cache_dir, sym, settings.engine.bar_size)
                last_dt = (
                    pd.to_datetime(cached.index.max()).tz_localize(
                        "UTC",
                        nonexistent="shift_forward",
                        ambiguous="NaT",
                    )
                    if not pd.api.types.is_datetime64tz_dtype(cached.index)
                    else cached.index.max()
                )
                today = pd.Timestamp(datetime.now(timezone.utc).date()).tz_localize("UTC")
                age_days = (today - last_dt.normalize()).days if last_dt is not pd.NaT else 10**9
                allowed_sources = {"yahoo", "stooq", "ibkr"}
                has_future = pd.to_datetime(cached.index.max()) > pd.Timestamp(datetime.now(timezone.utc).date())
                meta_ok = meta is not None and (meta.source or "").lower() in allowed_sources
                fresh_ok = (age_days <= max(settings.data.max_cache_age_days, 1))
                if (not has_future) and meta_ok and fresh_ok:
                    try:
                        gate.validate(DataFrameWithMeta(cached, meta))
                        out[sym] = cached
                        continue
                    except Exception:
                        # fall through to providers
                        pass
        errors: List[str] = []
        for name, prov in provider_chain:
            try:
                dfm = prov.fetch_daily_ohlcv(sym, start=start_s, end=end_s)
                gate.validate(dfm)
                out[sym] = dfm.data
                # Save cache + lineage sidecar
                try:
                    save_to_cache(settings.data.cache_dir, sym, settings.engine.bar_size, dfm.data)
                    save_lineage(settings.data.cache_dir, sym, settings.engine.bar_size, dfm.lineage)
                except Exception:
                    # Cache failures should not block a valid load
                    pass
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
                continue
        if sym not in out:
            errs = "; ".join(errors) if errors else "sin detalle"
            raise RuntimeError(f"Data no disponible para {sym}: {errs}")
    return out

