"""Position buffering (pysystemtrade ``systems/buffering.py``): trade only when the target leaves a band.

The band is ``target +/- buffer`` with ``buffer = buffer_frac * |average position|`` (the position
held at forecast 10: ``vol_scalar * w_instr * IDM``). Inside the band the current position is kept;
outside it the position moves to the nearest edge of the band (or to the target itself).

:func:`apply_buffer` is path dependent by construction (today's position depends on yesterday's),
but it only looks at the past: position ``t`` uses targets and buffers up to ``t``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def position_buffer(average_abs_position: pd.Series, buffer_frac: float = 0.10) -> pd.Series:
    """``buffer_frac * |average_abs_position|`` in shares."""
    if buffer_frac < 0:
        raise ValueError("buffer_frac must be >= 0")
    out: pd.Series = float(buffer_frac) * average_abs_position.astype(float).abs()
    out.name = "position_buffer"
    return out


def apply_buffer(target: pd.Series, buffer: pd.Series, trade_to_edge: bool = True) -> pd.Series:
    """Path-dependent buffered position, starting from 0 shares.

    At each date, with ``actual`` the position carried from the previous date:

    * ``|target - actual| <= buffer``: keep ``actual``;
    * otherwise move to the nearest edge (``target - buffer`` if ``actual < target``,
      ``target + buffer`` if ``actual > target``) when ``trade_to_edge``, else to ``target``.

    A NaN target keeps the current position; a NaN buffer is treated as 0 (no band).
    ``buffer`` is aligned to ``target.index``.
    """
    tgt = target.astype(float).to_numpy()
    buf = buffer.astype(float).reindex(target.index).to_numpy()
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
        if abs(t - pos) <= b:
            out[i] = pos
            continue
        if trade_to_edge:
            pos = t - b if pos < t else t + b
        else:
            pos = t
        out[i] = pos
    return pd.Series(out, index=target.index, dtype=float, name="buffered_position")
