# EXEC-PACKET — Hardening hiper-robusto post-auditoría

**Estado:** FILLED (olas A–C implementadas; DoD tests focales verde)  
**Fuente:** `docs/AUDIT-HARDENING-2026-10-18.md`  
**Git:** solo `main` · sin ramas · sin worktrees · sin PRs

## Objetivo

Cerrar P0-1…P0-9 y smoke research usable. No conectar paper a broker. No inventar alpha.

## Pasos

### [x] A1 — Fail-closed backtest (`backtest/engine.py` + `tests/test_risk_fail_closed.py`)
- Agente: e22642fe — risk blocks log + block exposure increase

### [x] A2 — Paper ↔ RiskManager (`paper_policy.py`, `decision.py` + tests)
- Agente: 62a771b4 — `veto_if_risk_rejects` → `approve_order`

### [x] B1 — Gates estrictos (`gates.py` + tests)
- Agente: 994f9497 + follow-up — `evaluate_strict_gates`, BH missing FAIL

### [x] B2 — Suite profile (`suite.py`, `cli.py`, `test_research_cli.py`)
- smoke: 1 SMA + SPY + DSR; CLI `--profile smoke` (~16s)

### [x] B3 — restricted_bar_frac helpers (`runner.py` + runners)
- Agente: f8dff848 — resolve helper; engine aún no emite metric (assumed 0.0 anotado)

### [x] C1 — LIVE/PAPER broker safety (`config.py`, `broker/ibkr.py` + tests)
- Agente: 1104ecbb — `allow_broker_orders`, expected_account obligatorio LIVE, readonly connect

### [x] P0-7/P0-8 — Killswitch fail-closed + STOP/EMERGENCY no abren (`risk/manager.py`)
- Follow-up Cursor + `tests/test_risk_fail_closed_killswitch.py`

### [ ] D — Shadow + data fail-loud + registry hashes (siguiente turno)
### [ ] D2 — Engine emite `restricted_bar_frac` real (cierra B3 de verdad)

## DoD (olas A–C)
- [x] pytest focal hardening: 53 passed (risk fail-closed, killswitch, ibkr live safety, paper/decision, gates, smoke CLI, broker sim, config, killswitch engine)
- [ ] commit (espera pedido de Adam)
- [ ] push main

## No hacer
- No LIVE trading real · No force-push / ramas / PRs · No reivindicar PASS=deploy
