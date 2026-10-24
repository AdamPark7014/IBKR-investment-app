# EXEC-PACKET — Oleada F3+ (paper disciplinado, sin Adam-blockers)

**Estado:** FILLED  
**Git:** solo `main`  
**Bloqueado en Adam (no tocar):** Tiingo token, DD/capital/horizonte hold-out, token `pia_…`.

## Honestidad
No LIVE. No LLM noticias. No “perfecto = ganancias”. Perfecto aquí = cimientos Fase 3 del playbook que aún faltan en código.

## Gaps a cerrar esta oleada

### [ ] W1 — Sesión RTH + latencia en sim
- `execution/session.py`: `is_rth(ts, tz=America/New_York)` (09:30–16:00 ET, lun–vie).
- `SimulatedBroker`: `latency_ms` (default 0); opcional rechazar LMT/MKT fuera de RTH si `require_rth=True`.
- Tests.

### [ ] W2 — Alertas paper (DD / drift)
- `ops/alerts.py`: `evaluate_paper_alerts(equity_curve|dd, assumed_sharpe, n_drift, …) -> list[Alert]`.
- Si DD >> esperado bajo Sharpe asumido → `severity=kill_recommend` (no activa kill sola).
- Autopilot incluye `alerts` en payload + UI.

### [ ] W3 — Schedule diario (Windows)
- `scripts/schedule-autopilot.ps1`: registra Task Scheduler `ibtrader-autopilot` → `ibtrader autopilot` (0 órdenes).
- README 3 líneas.

### [ ] W4 — Tests + relevo + push

## No hacer
LIVE · IBC real en servidor ajeno · cambiar params de estrategia · hold-out
