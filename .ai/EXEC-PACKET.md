# EXEC-PACKET — Hardening hiper-robusto post-auditoría

**Estado:** CLOSED — olas A–C, Ola D (D2 + registry hashes + data fail-loud + shadow stub) y fase 1 del playbook  
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
### [x] D — data fail-loud (P1-4: `validate_pit`, `cache.py` loud miss, `service.py` razones agregadas; `downloader.normalize_yf` ya no traga MultiIndex)
### [x] D — shadow book stub (P1-6): `ops/shadow.py` + `paper-run --shadow` (desired vs held, cero broker)
### [x] D2b — `restricted_bar_frac` en `backtest/report.stats_json` (desde `restricted_counts` del engine)
### [x] Fase 1 del playbook (2026-10-21) — datos PIT (Tiingo, vintages, universo), modelo de costos IBKR, presupuesto de pruebas + hold-out congelado, golden files
### [ ] Fase 2 — Universo ~10 ETFs según `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` (grafo de stages, EWMAC + 1/3/12 m, risk parity por cajas, vol target 10 %, buffers, hold-out congelado)

## DoD
- [x] `pytest`: 171 passed · `ruff check src tests` OK · `mypy src` OK (2026-10-21, Python 3.12)
- [x] Smoke CI en local: download-data, backtest-sample, compare-directions, walk-forward, research-run smoke (exit 0; gate estricto FAIL por `does_not_beat_bh`, esperado en datos sintéticos)
- [x] commit + `git pull --rebase` + push `main`

## No hacer
- No LIVE trading real · No force-push / ramas / PRs · No reivindicar PASS=deploy
