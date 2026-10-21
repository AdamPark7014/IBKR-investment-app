# EXEC-PACKET — Hardening hiper-robusto post-auditoría

**Estado:** CLOSED — olas A–C + fase 1 (B cerrada de verdad, D2 cerrada, D parcial)  
**Fuente:** `docs/AUDIT-HARDENING-2026-10-18.md`  
**Git:** solo `main` · sin ramas · sin worktrees · sin PRs

## Objetivo

Cerrar P0-1…P0-9 y smoke research usable. No conectar paper a broker. No inventar alpha.

## Pasos

### [x] A1 — Fail-closed backtest (`backtest/engine.py` + `tests/test_risk_fail_closed.py`)
### [x] A2 — Paper ↔ RiskManager (`paper_policy.py`, `decision.py` + tests)
### [x] B1 — Gates estrictos existen (`gates.py` + tests)
### [x] B1b — Gates estrictos DECIDEN el PASS (2026-10-21)
- `evaluate_strict_gates`: Sharpe OOS ≥ 0.25 **y** ganar a B&H ajustado por riesgo
  (Sharpe mayor, o Sharpe ≥ B&H − 0.10 con DD ≥ 5 pp menos profundo); sin Sharpe de B&H = FAIL.
- `suite._apply_strict_gates`: re-evalúa cada fila; conserva `gate_passed_loose`; DSR/PBO/CPCV solo
  a la familia SMA del símbolo de la suite; `restricted_bar_frac_assumed` = FAIL. `n_pass`/`any_gate_passed` son estrictos.
### [x] B2 — Suite profile smoke/full (`suite.py`, `cli.py`)
### [x] B3 + D2 — `restricted_bar_frac` real desde el engine (2026-10-21)
- `BacktestResult.restricted` por barra (halted / FSM ≠ NORMAL / killswitch; excepción = True, fail-closed),
  helper `restricted_counts`; walk-forward y runners (tsmom, mean-rev, xsection, loss-mitigation) escriben
  `restricted_bar_frac` en las stats OOS (stitched y por fold).
### [x] C1 — LIVE/PAPER broker safety (`config.py`, `broker/ibkr.py` + tests)
### [x] P0-7/P0-8 — Killswitch fail-closed + STOP/EMERGENCY no abren (`risk/manager.py`)
### [x] P1-8 — Registry con hashes obligatorios (2026-10-21)
- `build_experiment_records` lanza `ValueError` sin `dataset_hash`/`config_hash`; `research-run` los pasa
  desde `ops/artifacts`. La carga sigue tolerando filas viejas.
### [x] Riesgo fail-closed en `update_equity` (2026-10-21): excepción → `halt_next_day=True` + log ERROR.
### [x] Bug `market-analyze`: `datetime.UTC` → `timezone.utc` (y `utcnow` deprecado en `research-run`).
### [x] Defaults conservadores: drawdown 25 → 20 % (`config.py`, `RISK_MODEL.md`, `.env.example` con `RISK__*`).
### [x] CI en `main` con ubuntu + macOS y smoke de `research-run` (`.github/workflows/ci.yml`).
### [ ] D — Shadow book (`ops/shadow.py`) + data fail-loud (P1-4, P1-5, P1-6) — siguiente turno
### [ ] Fase 2 — Universo ~10 ETFs: paridad de riesgo, TSMOM, dual momentum vs 60/40, periodo de confirmación congelado

## DoD
- [x] `pytest`: 171 passed · `ruff check src tests` OK · `mypy src` OK (2026-10-21, Python 3.12)
- [x] Smoke CI en local: download-data, backtest-sample, compare-directions, walk-forward, research-run smoke (exit 0; gate estricto FAIL por `does_not_beat_bh`, esperado en datos sintéticos)
- [x] commit + `git pull --rebase` + push `main`

## No hacer
- No LIVE trading real · No force-push / ramas / PRs · No reivindicar PASS=deploy
