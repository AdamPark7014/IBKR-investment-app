"""Position buffering (pysystemtrade ``systems/buffering.py``): trade only when the target leaves a band.

The band is ``target +/- buffer`` with ``buffer = buffer_frac * |average position|`` (the position
held at forecast 10: ``vol_scalar * w_instr * IDM``). Inside the band the current position is kept;
outside it the position moves to the nearest edge of the band (or to the target itself).

:func:`apply_buffer` is path dependent by construction (today's position depends on yesterday's),
but it only looks at the past: position ``t`` uses targets and buffers up to ``t``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def position_buffer(average_abs_position: pd.Series, buffer_frac: float = 0.10) -> pd.Series:
    """``buffer_frac * |average_abs_position|`` in shares."""
    if buffer_frac < 0:
        raise ValueError("buffer_frac must be >= 0")
    out: pd.Series = float(buffer_frac) * average_abs_position.astype(float).abs()
    out.name = "position_buffer"
    return out


def apply_buffer(target: pd.Series, buffer: pd.Series, trade_to_edge: bool = True,
                 min_trade: Optional[pd.Series] = None) -> pd.Series:
    """Path-dependent buffered position, starting from 0 shares.

    At each date, with ``actual`` the position carried from the previous date:

    * ``|target - actual| <= buffer``: keep ``actual``;
    * otherwise move to the nearest edge (``target - buffer`` if ``actual < target``,
      ``target + buffer`` if ``actual > target``) when ``trade_to_edge``, else to ``target``.

    A NaN target keeps the current position; a NaN buffer is treated as 0 (no band).
    ``buffer`` is aligned to ``target.index``.

    ``min_trade`` (shares, optional): the smallest trade worth paying a commission for (production
    skips orders below ``PRETRADE__MIN_ORDER_NOTIONAL_USD``). The band is at least that wide, and a trade
    to the edge smaller than it waits until the target has moved a full minimum away. A move to or from
    zero is never blocked (entries and exits must happen).
    """
    tgt = target.astype(float).to_numpy()
    buf = buffer.astype(float).reindex(target.index).to_numpy()
    mins = (min_trade.astype(float).reindex(target.index).to_numpy() if min_trade is not None
            else np.zeros(len(tgt)))
    n = len(tgt)
    out = np.empty(n, dtype=float)
    pos = 0.0
    for i in range(n):
        t = tgt[i]
        if np.isnan(t):
            out[i] = pos
            continue
        b = buf[i]
        b = 0.0 if np.isnan(b) else abs(b)
        m = mins[i]
        m = 0.0 if np.isnan(m) else abs(m)
        if t != 0.0 and pos != 0.0:
            b = max(b, m)
        if abs(t - pos) <= b:
            out[i] = pos
            continue
        if trade_to_edge:
            edge = t - b if pos < t else t + b
            if m > 0.0 and pos != 0.0 and t != 0.0 and abs(edge - pos) < m:
                out[i] = pos  # not worth a commission yet: wait until the edge is a full minimum away
                continue
            pos = edge
        else:
            pos = t
        out[i] = pos
    return pd.Series(out, index=target.index, dtype=float, name="buffered_position")
