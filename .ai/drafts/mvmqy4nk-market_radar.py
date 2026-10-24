from __future__ import annotations

import typing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _close_col(df: pd.DataFrame) -> Optional[pd.Series]:
    """Extrae la columna de cierre de un DataFrame."""
    if df is None or len(df) == 0:
        return None
    # Intentar 'Close', luego 'close', luego 'Adj Close'
    cols = [c for c in ['Close', 'adj_close', 'close', 'Adjustment'] if c in df.columns]
    return df[cols[0]].copy() if cols else None


def _slice(prices: Dict[str, pd.DataFrame], symbol: str, as_of: Optional[pd.Timestamp]) -> Optional[pd.Series]:
    """Filtrar y retornar serie de precios hasta 'as_of' (