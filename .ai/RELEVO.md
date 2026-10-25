# RELEVO

## Hecho (2026-10-25, cursor — W14c)
- Append-only `config-freeze` en `src/ibtrader/ops/cli.py` (~25 líneas antes de `if __name__`): `--write/--verify` (default verify), `--path` default `data/paper_config_freeze.json`, JSON `{ok, expected, actual, reason?, orders_sent=0}`.
- Smoke: `tests/test_config_freeze_cli.py` (tmp path write/verify/missing).
- `cli.py` size OK (~62k). No toqué simple_ui / simulated / autopilot / schedule.
- Sin commit/push.

## A medias
- W14a simple_ui cards (otro agente)
- W14b ops-smoke.ps1 (otro agente)
- W14d sim decide_urgency on aged LMT (otro agente)
- Adam: Tiingo + hold-out + pia + Task Scheduler Register
- Calendario: paper congelado meses

## Siguiente
- Integrar/heal/push W14 cuando cierren a/b/d → si no quedan huecos Fase 3, parar oleadas.

## No tocar
- Solo main. Cero LIVE. No reescribir `cli.py` entero con Ollama.
- No tocar simple_ui, simulated, autopilot, schedule scripts desde W14c.
