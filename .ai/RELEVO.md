# RELEVO

## Hecho (2026-10-25, cursor — W14b)
- NEW `scripts/ops-smoke.ps1`: Status (default) | RunOnce; banner PAPER triage; Status llama schedule-autopilot/reconcile/ibc-check; RunOnce: ibc-checklist → paper-reconcile → paper-vs-oos → paper-stack vía venv python -m ibtrader.ops.cli (continúa si non-zero; 0 órdenes / no LIVE)
- README.md: +2 líneas bajo schedule documentando ops-smoke.ps1
- Smoke Status: EXIT=0 con tareas no registradas
- Sin commit/push. No toqué autopilot/cli/simulated.

## A medias
- Tiingo + hold-out + pia + Task Scheduler Register (Adam)
- Fase 3 calendario paper congelado (no código)

## Siguiente
- Adam: Register tareas si quiere; RunOnce cuando venv/datos listos
- Commit/push solo si Adam pide

## No tocar
- Solo main. PASS ≠ deploy. Cero órdenes LIVE.
- No editar autopilot/cli/simulated en este hilo W14b.
