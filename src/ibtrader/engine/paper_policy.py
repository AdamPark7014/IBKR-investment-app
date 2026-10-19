from __future__ import annotations

import math
from collections.abc import Mapping

__all__ = [
    "classify_paper_action",
    "size_paper_positions",
    "apply_stop_veto",
]


def classify_paper_action(
    *,
    score: float,
    direction: str,
    killswitch: bool,
    symbol_allowed: bool,
    data_ok: bool,
    buy_threshold: float = 0.2,
    sell_threshold: float = -0.2,
) -> tuple[str, str]:
    """Clasifica una recomendación de papel. No envía órdenes."""
    if not data_ok or not math.isfinite(score):
        return ("NO_TRADE", "Datos insuficientes o score no numérico.")
    if killswitch:
        return ("NO_TRADE", "Kill switch activo: no se abre exposición.")
    if not symbol_allowed:
        return ("NO_TRADE", "Símbolo fuera de la lista permitida.")

    long_ok = direction in {"long_only", "long_short"}
    short_ok = direction in {"short_only", "long_short"}

    if score >= buy_threshold and long_ok:
        return ("BUY", "Score largo por encima del umbral tras filtro de régimen.")
    if score >= buy_threshold and not long_ok:
        return ("NO_TRADE", "Señal larga bloqueada por la dirección configurada.")
    if score <= sell_threshold and short_ok:
        return ("SELL", "Score corto por debajo del umbral.")
    if score <= sell_threshold and not short_ok:
        return ("WATCH", "Señal corta ignorada: la dirección no permite cortos.")
    return ("WATCH", "Score dentro de la banda: sin operación.")


def size_paper_positions(
    actions: Mapping[str, str],
    vol_weights: Mapping[str, float],
    max_position_pct: float,
    max_total_exposure_pct: float,
) -> dict[str, float]:
    """Tamaños de papel firmados, con tope por nombre y por exposición bruta."""
    cap_pos = max_position_pct / 100.0
    cap_gross = max_total_exposure_pct / 100.0
    if cap_gross <= 0.0:
        return {ticker: 0.0 for ticker in actions}

    raw: dict[str, float] = {}
    gross = 0.0
    for ticker, action in actions.items():
        vol_w = float(vol_weights.get(ticker, 0.0))
        if action == "BUY" and vol_w > 0.0:
            size = min(cap_pos, vol_w)
        elif action == "SELL" and vol_w > 0.0:
            size = -min(cap_pos, vol_w)
        else:
            size = 0.0
        raw[ticker] = size
        gross += abs(size)

    if gross > cap_gross:
        factor = cap_gross / gross
        return {ticker: size * factor for ticker, size in raw.items()}
    return raw


def apply_stop_veto(
    action: str,
    desired_sign: int,
    effective_sign: int,
) -> tuple[str, str | None]:
    """Si el stop ATR deja la posición en cero, no se abre esa entrada."""
    if action == "BUY" and desired_sign > 0 and effective_sign == 0:
        return ("NO_TRADE", "Entrada larga vetada por stop ATR.")
    if action == "SELL" and desired_sign < 0 and effective_sign == 0:
        return ("NO_TRADE", "Entrada corta vetada por stop ATR.")
    return (action, None)
