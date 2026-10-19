from __future__ import annotations
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    """Clasificar accion de papel basandose en score y reglas de veto.

    Veto orden:
      1. datos insuficientes o score no numerico
      2. killswitch activo
      3. simbolo fuera lista permitida
      4. direccion configurada bloquea largo/corto segun score
      5. dentro banda -> WATCH

    Args:
        score: señal numérica normalizada del motor.
        direction: 'long_only' | 'short_only' | 'long_short'.
        killswitch: bandera de paro preventivo global.
        symbol_allowed: indica si el ticker está en lista permitida.
        data_ok: datos suficientes para evaluar la señal.
        buy_threshold: umbral mínimo para abrir larga (por defecto 0.2).
        sell_threshold: umbral máximo para abrir corta (por defecto -0.2).

    Returns:
        Tupla (action, reason) en español donde action es BUY|SELL|NO_TRADE|WATCH.
    """
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
    """Dimensionar posiciones simuladas a partir de acciones clasificadas.

    Calcula el tamaño de cada acción (BUY/SELL/WATCH) aplicando límites individuales
    y un límite global de exposición bruta neta. Las acciones WATCH reciben 0.0.

    Args:
        actions: dict {ticker -> action} donde action es BUY|SELL|NO_TRADE|WATCH.
        vol_weights: dict {ticker -> float} ponderación de volatilidad implícita.
        max_position_pct: límite individual expresado en porcentaje del capital.
        max_total_exposure_pct: límite global de exposición neta absoluta (% capital).

    Returns:
        dict {ticker: float} tamaño asignado para cada acción (posiciones WATCH=0.0).
    """
    cap_pos = max_position_pct / 100.0
    cap_gross = max_total_exposure_pct / 100.0

    if cap_gross <= 0.0:
        return {ticker: 0.0 for ticker in actions}

    raw_sizes: dict[str, float] = {}
    gross_sum = 0.0

    for ticker, action in actions.items():
        vol_w = vol_weights.get(ticker, 0.0)
        if vol_w <= 0.0:
            raw_sizes[ticker] = 0.0
            continue

        if action == "BUY":
            size = min(cap_pos, max(0.0, vol_w))
            sign = +1.0
        elif action == "SELL":
            size = -min(cap_pos, max(0.0, vol_w))
            sign = -1.0
        else:  # WATCH, NO_TRADE
            raw_sizes[ticker] = 0.0
            continue

        raw_sizes[ticker] = size
        gross_sum += abs(size)

    # Si la suma bruta supera el límite global, escalar proporcionalmente
    if gross_sum > cap_gross:
        factor = cap_gross / gross_sum
        scaled_sizes: dict[str, float] = {}
        for ticker, size in raw_sizes.items():
            scaled_sizes[ticker] = size * factor
        return scaled_sizes

    # Si no excede el límite global, retornar los tamaños calculados
    return raw_sizes


def apply_stop_veto(
    action: str,
    desired_sign: int,
    effective_sign: int,
) -> tuple[str, str | None]:
    """Aplicar veto de parada técnica (ATR) sobre la acción deseada.

    Cuando desired_sign indica la dirección intencional y effective_sign es 0,
    implica que una parada ha vetado la entrada. Solo BUY con sign>0 y SELL con sign<0
    son afectados; WATCH/NO_TRADE pasan sin efecto.

    Args:
        action: resultado de classify_paper_action (BUY|SELL|WATCH|NO_TRADE).
        desired_sign: 1 para largo intencional, -1 para corto intencional, 0 neutral.
        effective_sign: 1 o -1 si la parada está activa, 0 si no hay parada.

    Returns:
        Tupla (action_result, reason) donde action_result es NO_TRADE si el veto aplica,
        y reason describe el motivo en español; otherwise devuelve (action, None).
    """
    if action == "BUY" and desired_sign > 0 and effective_sign == 0:
        return ("NO_TRADE", "Entrada larga vetada por stop ATR.")
    if action == "SELL" and desired_sign < 0 and effective_sign == 0:
        return ("NO_TRADE", "Entrada corta vetada por stop ATR.")

    return (action, None)