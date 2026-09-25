from __future__ import annotations

from typing import Tuple

import pandas as pd


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

