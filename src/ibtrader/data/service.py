from __future__ import annotations

from typing import Dict

import pandas as pd

from ..config import AppSettings
from .providers import DataQualityGate, StooqProvider, YahooProvider


def load_universe_v2(settings: AppSettings) -> Dict[str, pd.DataFrame]:
    primary = YahooProvider()
    fallback = StooqProvider()
    gate = DataQualityGate(min_rows=min(252, settings.engine.history_days))
    out: Dict[str, pd.DataFrame] = {}
    for sym in settings.universe.symbols:
        last_err = None
        for prov in (primary, fallback):
            try:
                dfm = prov.fetch_daily_ohlcv(sym)
                gate.validate(dfm)
                out[sym] = dfm.data
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        if last_err is not None:
            raise RuntimeError(f"Data no disponible para {sym}: {last_err}")
    return out

