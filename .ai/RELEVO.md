# RELEVO

## Hecho (2026-10-24, cursor — oleada F3+)
- `execution/session.py` RTH ET; sim `require_rth` + `latency_ms`.
- `ops/alerts.py` + `config_freeze.py`; autopilot emite alerts + freeze hash.
- `scripts/schedule-autopilot.ps1` (Task Scheduler diario, 0 órdenes).
- Tests: session, alerts, freeze, broker RTH.

## Hecho (previo)
- Autopilot UI, PromptPack/brief, Fase 3 ledger/prob-fill/paper-reconcile/radar.

## A medias
- Tiingo + hold-out (Adam).
- Token puerta IA opcional.
- Agentes W1–W3 en background pueden solapar; disco = verdad tras este commit.

## Siguiente
- Oleada: stub passive→aggressive (`algoOriginalBest` paper-only) + enrich brief con freeze/alerts.
- IBC/Gateway docs-only (no instalar en máquina ajena).

## No tocar
- Solo `main`. PASS ≠ deploy. Hold-out una vez. Autopilot sin órdenes.

Escrito al cerrar turno cursor 2026-10-24 13:13.

