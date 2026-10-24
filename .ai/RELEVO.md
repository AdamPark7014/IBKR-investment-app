# RELEVO

## Hecho (2026-10-24, cursor — Fase 3 cimiento + market radar PIT)
- `ops/slippage_ledger.py`: JSONL decisión vs fill + `summarize`.
- `SimulatedBroker`: `prob_fill_on_limit` (default 0.7) + ledger en fills.
- CLI `ibtrader paper-reconcile` (desired vs `paper_positions.json`, 0 órdenes).
- `intelligence/market_radar.py`: snapshot PIT (trend/vol/VIX/rates/commod/breadth) — triage, no predicción.
- `market-analyze` incluye `market_radar` en el JSON.
- Tests focal: ledger, prob-fill, radar, paper-reconcile, broker sim.

## Hecho (previo)
- tsmom/MR OOS costos, CI portfolio smoke, sim IBKR, Fase 2 CLI, shadow, hardening.

## A medias
- Tiingo real + hold-out: inputs de Adam (token, DD, capital, horizonte).
- Paper vivo prolongado sin retocar parámetros (disciplina Fase 3).

## Siguiente
- Push main + vigilar CI.
- Cuando haya Tiingo: confirmación OOS una sola vez.
- Ampliar universe de radar (más proxies) solo con datos PIT ya en disco.

## No tocar
- Solo `main`. PASS ≠ deploy. Hold-out una vez. Paper-run / paper-reconcile sin órdenes broker.
- No LLM sobre titulares / alt-data de pago / intradía / apalancados (playbook §119).
