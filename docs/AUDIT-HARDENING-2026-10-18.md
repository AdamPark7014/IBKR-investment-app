# Auditoría hiper-robusta — 2026-10-18

Alcance: risk/execution, paper decision, data, research (overfitting / compresión de edge), ops.
Método: relevo limpio → rg/lectura de paths críticos → exploradores en paralelo → plan de hardening.

## Veredicto

El stack de **correctness P6–P9** y el **lab V3** son serios. Los huecos críticos no son “falta de features”: son **fail-open silencioso**, **gates OOS demasiado blandos frente a multiple testing**, **paper desconectado de `approve_order`**, **suite de research combinatoria sin perfil smoke**, y **LIVE con `expected_account` opcional**.

---

## P0 — fallos que pueden mentir o abrir exposición

| ID | Hallazgo | Dónde | Por qué duele | Fix mínimo |
|----|----------|-------|---------------|------------|
| P0-1 | `except Exception: pass` en gates de kill/halt/DD del backtest | `backtest/engine.py` ~253–321 | Si falla el chequeo, **sigue el trade** (fail-open) | Fail-closed: log + `delta=0`; test que fuerza excepción |
| P0-2 | Paper recomienda BUY/SELL sin `RiskManager.approve_order` | `engine/decision.py`, `paper_policy.py` | Kill/símbolo sí; **no** daily loss / DD / size / exposure FSM | Puente: clasificar → size → `approve_order` sintético → veto |
| P0-3 | Gate OOS: Sharpe ≥ 0 + 5 trades | `research/gates.py` | Acepta ruido; **DSR/PBO/CPCV no bloquean** `gate_passed` | Extender gates: exigir DSR/PBO cuando el suite los tiene; umbral Sharpe ≥ 0.25 OOS o documentar “interesting-only” |
| P0-4 | `run_research_suite` siempre full | `research/suite.py`, `ops/cli.py` `research-run` | 12+ tracks × grids → CI/test cuelga | `--profile smoke\|full`; smoke: SMA+gates+DSR only |
| P0-5 | LIVE: `IB_EXPECTED_ACCOUNT` opcional | `config.py` `live_safety_ok`, `broker/ibkr.py` | Orden LIVE en cuenta equivocada | Exigir cuenta no vacía en LIVE; fallar `place_order` |
| P0-6 | PAPER puede `place_order` sin flag explícito | `broker/ibkr.py` | Cualquier caller manda órdenes paper sin risk path | Requerir `TRADING__ALLOW_BROKER_ORDERS=yes` + risk approval hook |

## P1 — huecos de robustez / compresión estadística

| ID | Hallazgo | Dónde | Fix |
|----|----------|-------|-----|
| P1-1 | Compresión de potencia: demasiados tracks en un solo “PASS” | `suite.py`, `report.py` | Separar *discovery* vs *confirmation*; un solo family-wise error rate |
| P1-2 | Honest report marca skeptical pero no cambia `gate_passed` | `report.py` vs `gates.py` | `gate_passed_strict` = gates ∧ ¬skeptical_flags |
| P1-3 | Sin VIX → `risk_on=0` siempre | `intelligence/regime.py` | Proxy documentado (breadth+trend) o exigir `^VIX` en paper-run |
| P1-4 | `except Exception` en data/cache/providers | `data/*` | Fallar con razón agregada; no cachear basura |
| P1-5 | Journal swallow en decision | `engine/decision.py` | Re-raise en tests; métrica de fallo journal |
| P1-6 | Sin shadow book / champion-challenger | roadmap Fase 2 | Stub `ops/shadow.py`: log desired vs held, cero broker |
| P1-7 | Connect IBKR `readonly=False` siempre | `broker/ibkr.py` | PAPER connect readonly salvo flag órdenes |
| P1-8 | Registry: hashes a menudo vacíos | `registry.py` callers | Obligar `dataset_hash`/`config_hash` al guardar |

## P2 — deuda / higiene

| ID | Hallazgo | Fix |
|----|----------|-----|
| P2-1 | Stooq best-effort | Dejar de listarlo por defecto en docs/README |
| P2-2 | `test_research_run_cli_full_suite` sin timeout | Usar profile smoke + `pytest` mark `slow` |
| P2-3 | Confidence = \|score\| | Meta-label TAKE/SKIP (Fase 2) — no inventar calibración |
| P2-4 | Duplicado comentario killswitch en engine | Limpieza cosmética |

## Qué NO tocar (ya sólido)

- Separación walk-forward / OOS en P9
- FSM de riesgo + tests de killswitch / daily loss / flip
- Purge/embargo en `ml/cv.py`
- Política paper v1 (BUY/SELL/WATCH/NO_TRADE) sin enviar órdenes en CLI
- Disclaimer honest report “PASS ≠ deploy”

## Compresión (definición usada aquí)

No es “comprimir archivos”: es **multiple testing + demasiados candidatos** que **comprimen** el edge aparente (Sharpe inflado, PBO alto). Mitigación: menos tracks en smoke, gates estrictos con DSR/PBO, un confirmation set congelado.

---

## Addendum exploradores (2026-10-18)

Fuentes: [risk/exec](d8dacbe0-b638-49db-bbc2-6dcb537469e5) · [research/overfit](cb8063e2-7974-4080-8048-9b505654b162) · [decision/data](c25c4541-59cb-426c-8449-f0d16e3eed54).

### Extra P0 confirmados
| ID | Hallazgo | Estado |
|----|----------|--------|
| P0-7 | `killswitch_active` fail-open si `exists` lanza | **cerrado** en `risk/manager.py` |
| P0-8 | `is_emergency`/`is_stop` pueden abrir/aumentar | **cerrado** en `approve_order` |
| P0-9 | `bh_stats is None` → DD gate bypasseado | **cerrado** en `gates.py` |
| P0-10 | `restricted_bar_frac` siempre 0.0 en runners | pendiente (Ola B+) |
| P0-11 | Paper timing/costos/régimen ≠ backtest | pendiente (doc + bridge; no fingir paridad) |
| P0-12 | Puerto LIVE check tautológico; PAPER→4001 | pendiente Ola C |

### Extra P1 destacados
- Registry sin `dataset_hash`/`config_hash`
- DSR solo sobre 3 SMA trials
- WF sin embargo real entre val→test
- Sin VIX → risk-off forever (documentar + opcional proxy)
- `record_trade` dead code / journal sin WAL

---

## Plan de implementación (olas)

### Ola A — Fail-closed + paper↔risk (P0-1, P0-2)
1. Backtest: fail-closed en excepciones de risk gates + test
2. Paper: `approve_paper_intent` usando RiskManager
3. Tests decisión con halt/kill/DD

### Ola B — Research gates + smoke suite (P0-3, P0-4, P1-1, P1-2, P2-2)
1. `evaluate_candidate_gates(..., diagnostics=)` → strict
2. `run_research_suite(profile="smoke"|"full")`
3. CLI `--profile`; test CLI en smoke

### Ola C — Broker/LIVE (P0-5, P0-6, P1-7)
1. `live_safety_ok` exige `expected_account`
2. `place_order` exige allow-broker-orders + (LIVE → safety)
3. Tests de rechazo

### Ola D — Shadow + data fail-loud (P1-4, P1-5, P1-6) — siguiente turno si A–C verde

**Regla de flota:** mismo checkout `main`, archivos disjuntos, sin ramas/worktrees/PRs.
