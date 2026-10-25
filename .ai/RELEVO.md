# RELEVO

## Hecho (2026-10-25, cursor — W15a)
- `scripts/schedule-register-all.ps1`: Actions Register|Unregister|Status (default Status); llama `schedule-autopilot.ps1` / `schedule-reconcile.ps1` / `schedule-ibc-check.ps1` con el mismo `-Action`; banner PAPER triage only — zero broker orders — NO LIVE; opcionales `-AutopilotTime`/`-ReconcileTime`/`-IbcTime` (defaults 16:30 / 16:35 / 08:00)
- README: +2 líneas under schedule (Register-all + Status/Unregister/horas)
- Smoke `-Action Status` → EXIT=0 (tareas no registradas = OK)
- Sin push propio. No toqué `.py`.

## A medias — W15
- W15c `docs/PAPER-OPS.md` + README config-freeze
- W15d `open_orders` helper + touchable en autopilot

## Adam (bloquea edge, no más código)
- Tiingo API · hold-out una vez · `pia_…` opcional
- `Register` Task Scheduler (o `schedule-register-all`)
- Meses de paper congelado sin retocar params

## No tocar
- Solo main. Cero LIVE. No reescribir `cli.py` entero con Ollama.
