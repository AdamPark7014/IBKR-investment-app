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
    if df.isna().all().any():
        return False, "Columnas enteras vacías."
    return True, "OK"

