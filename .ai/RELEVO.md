# RELEVO

## Hecho (2026-10-24, cursor — passive_aggressive)
- `src/ibtrader/execution/passive_aggressive.py`: `UrgencyDecision` + `decide_urgency` (paper-only; algoOriginalBest conceptual; no orders).
- `tests/test_passive_aggressive.py`: 3 branches (not touchable / aged / within window).
- ruff clean; pytest 3 passed. NO commit (pedido Adam).
- NO toqué `simulated.py` ni `cli.py`.

## Hecho (previo)
- W2 polish alerts UI; F3+ RTH/freeze/autopilot.

## A medias
- Tiingo + hold-out (Adam). pia token opcional.
- Dirty ajeno en árbol: README.md, schedule-autopilot.ps1, drafts varios — no reescribir.

## Siguiente
- Cablear `decide_urgency` al paper path cuando toque (sin órdenes).
- Integrar W1/W3 si llegan limpios.

## No tocar
- Solo `main`. Autopilot sin órdenes. PASS ≠ deploy. simulated.py / cli.py en este turno.
