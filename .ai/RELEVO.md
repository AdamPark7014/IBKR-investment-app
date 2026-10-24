# RELEVO

## Hecho (2026-10-24, cursor — schedule-autopilot)
- `scripts/schedule-autopilot.ps1`: Action Register|Unregister|Status (default Status); Time 16:30 local; task `ibtrader-autopilot`; prefer `.venv\Scripts\python.exe -m ibtrader.ops.cli autopilot` else `ibtrader autopilot`; WorkingDirectory=repo via Set-Location; schtasks /F; paper triage only / zero orders / no LIVE.
- README: 3–4 líneas bajo paper/autopilot con `pwsh -File scripts/schedule-autopilot.ps1 -Action Register` (+ Status/Unregister/Time).
- Smoke Status OK (task not registered). NO commit (pedido Adam). NO edité `src/`.

## Hecho (previo)
- passive_aggressive helper + tests; W2 alerts; autopilot UI/PromptPack/brief.

## A medias
- Tiingo + hold-out (Adam). pia token opcional.
- Árbol puede tener dirty ajeno (`simulated.py`, `tests/test_session_rth.py`, drafts) — no reescribir si no es tuyo.

## Siguiente
- Adam: `pwsh -File scripts/schedule-autopilot.ps1 -Action Register` (puede pedir elevación schtasks).
- Cablear `decide_urgency` al paper path cuando toque (sin órdenes).

## No tocar
- Solo `main`. Autopilot sin órdenes broker. PASS ≠ deploy. No LIVE desde el schedule.
