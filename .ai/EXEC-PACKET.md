# EXEC-PACKET — Fase 3 paper disciplinado (cimiento)

**Estado:** FILLED  
**Fuente:** `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` §Fase 3  
**Git:** solo `main`

## Honestidad (no negociable)

Este turno **no** promete ganancias rápidas ni “leer todas las noticias del mundo”.
El playbook §119 excluye: LLM sobre titulares, alt-data de pago, intradía, ETFs apalancados.
La fuerza institucional = ejecución realista + reconciliación + no retocar parámetros con paper vivo.

## Objetivo

Cimientos de Fase 3: fills probabilísticos en el sim, ledger de slippage (decisión vs fill), CLI de reconciliación paper (sin LIVE).

## Pasos

### [ ] F3-1 — `ops/slippage_ledger.py`
- SQLite o JSONL bajo `data/`: `decision_ts`, `symbol`, `side`, `decision_px`, `fill_px`, `qty`, `slip_bps`, `source`
- `record_slip(...)`, `summarize(window_days) -> {n, mean_slip_bps, p95}`

### [ ] F3-2 — `SimulatedBroker` fills probabilísticos
- `prob_fill_on_limit: float` (default 0.7) en config o ctor
- LMT: con probabilidad `prob_fill` rellena; si no, unfilled
- Al fill MKT/LMT: escribir en slippage ledger si se pasa `ledger=`

### [ ] F3-3 — CLI `paper-reconcile`
- Compara desired (DecisionEngine) vs held (`paper_positions.json` o empty)
- Imprime drift + opcional resumen ledger
- Cero órdenes broker

### [ ] F3-4 — Tests + RELEVO
- Tests unitarios ledger + prob fill + CLI smoke
- Actualizar packet checkboxes

## DoD
- pytest focal verde; ruff en paths tocados
- relevo cerrar + push main

## No hacer
- No LIVE · No LLM noticias · No cambiar parámetros de estrategia por resultados paper
