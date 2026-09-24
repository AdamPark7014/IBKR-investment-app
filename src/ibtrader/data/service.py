from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import pandas as pd

from ..config import AppSettings
from .cache import load_from_cache, save_lineage, save_to_cache
from .providers import DataQualityGate, IBKRProvider, StooqProvider, YahooProvider


def load_universe_v2(settings: AppSettings) -> Dict[str, pd.DataFrame]:
    # Providers order via settings.data.providers; default set in config is ["yahoo", "stooq"]
    prov_map = {
        "yahoo": lambda: YahooProvider(),
        "stooq": lambda: StooqProvider(),
        "ibkr": lambda: IBKRProvider(
            host=settings.ib.host, port=settings.ib.paper_port, client_id=settings.ib.client_id
        ),
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
        # Cache check
        if settings.engine.use_cache:
            cached = load_from_cache(settings.data.cache_dir, sym, settings.engine.bar_size)
            if cached is not None and not cached.empty and len(cached) >= gate.min_rows:
                out[sym] = cached
                continue
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

