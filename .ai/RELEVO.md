# RELEVO

## Hecho (2026-10-24, cursor — ibc-checklist)
- Spec ya estaba en `main`: `src/ibtrader/ops/ibc_checklist.py` (`build_ibc_checklist`, phase=paper-ops, 6 items, disclaimer), CLI `ibtrader ibc-checklist` → JSON via `_noneify`, `tests/test_ibc_checklist.py`.
- Este turno: Ollama apply truncó `cli.py` → `git restore`; quité duplicate command; ruff import fix en tests.
- Ruff + pytest `tests/test_ibc_checklist.py` verdes. NO commit (pedido Adam). Autopilot/paper-reconcile bodies intactos.

## Hecho (previo)
- schedule-reconcile / schedule-autopilot scripts + README.

## A medias
- Tiingo + hold-out (Adam). pia token opcional.
- Dirty local: solo `tests/test_ibc_checklist.py` (imports ruff) — no commitear salvo pedido.

## Siguiente
- Adam: Register schtasks autopilot/reconcile si aún no.
- Cablear `decide_urgency` al paper path cuando toque (sin órdenes).

## No tocar
- Solo `main`. Paper triage / zero broker orders / no LIVE. No instalar IBC desde checklist.
