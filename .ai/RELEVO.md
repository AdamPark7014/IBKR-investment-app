# RELEVO

## Hecho (2026-10-24, cursor — schedule-reconcile)
- `scripts/schedule-reconcile.ps1`: Action Register|Unregister|Status (default Status); Time 16:35 local (tras autopilot 16:30); task `ibtrader-paper-reconcile`; prefer `.venv\Scripts\python.exe -m ibtrader.ops.cli paper-reconcile` else `ibtrader paper-reconcile`; Set-Location repo; schtasks /F; banner paper triage / zero orders / no LIVE.
- README: 2 líneas bajo schedule-autopilot (Register 16:35 + Status|Unregister|Time).
- Smoke Status OK (task not registered). NO commit (pedido Adam). NO edité `src/`.

## Hecho (previo — schedule-autopilot)
- `scripts/schedule-autopilot.ps1` + README autopilot bullets.

## A medias
- Tiingo + hold-out (Adam). pia token opcional.
- Adam: Register de ambas tareas schtasks (puede pedir elevación).

## Siguiente
- Adam: `pwsh -File scripts/schedule-reconcile.ps1 -Action Register` (y autopilot si aún no).
- Cablear `decide_urgency` al paper path cuando toque (sin órdenes).

## No tocar
- Solo `main`. Schedule = paper triage, zero broker orders, no LIVE. PASS ≠ deploy.
