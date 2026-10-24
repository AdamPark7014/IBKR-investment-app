# EXEC-PACKET — Oleada F3++ (cablear lo ya construido)

**Estado:** FILLED  
**Git:** solo `main`  
**Agentes previos:** todos terminados. No hay cola viva.

## Honestidad
“Perfecto” ≠ ingresos. Bloqueado en Adam: Tiingo, hold-out, pia token.  
Esta oleada solo **cablea** piezas ya en disco (urgency, freeze) + reconcile schedule + checklist IBC (docs-as-code JSON).

## Gaps

### [ ] W6 — Autopilot: `config_freeze` + `decide_urgency`
- Al arrancar: write_freeze si falta; verify_freeze → alert `config_drift` si mismatch.
- Facts: urgency snapshot (age=0 paper triage → passive) en compress/extra.
- UI ya muestra alerts.

### [ ] W7 — `scripts/schedule-reconcile.ps1`
- Igual patrón que schedule-autopilot: diario `ibtrader paper-reconcile`.
- README 2 líneas.

### [ ] W8 — `ops/ibc_checklist.py` + CLI `ibc-checklist`
- Checklist JSON honesta (Gateway paper puerto, Read-Only off, API 127.0.0.1, IBC opcional).
- No instala nada; no LIVE.

### [ ] W9 — Tests + push

## No hacer
LIVE · retocar params estrategia · LLM noticias · hold-out
