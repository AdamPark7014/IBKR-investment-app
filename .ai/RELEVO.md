# RELEVO

## Hecho (2026-10-24, cursor — W11b paper stack)
- NEW `src/ibtrader/ops/stack.py`: PaperStack SQLite (`data/paper_stack.sqlite` injectable); upsert_desired/held; snapshot (desired/held/drift); sync_from_json; cmd_paper_stack (orders_sent=0).
- NEW `tests/test_paper_stack.py`: roundtrip + drift + orders_sent=0.
- CLI: append-only `@app.command("paper-stack")` at end of `cli.py` (~15 lines).
- pytest tests/test_paper_stack.py -q → 3 passed. NO commit/push.
- No toqué autopilot.py, simulated.py, paper_curve, schedule scripts, brief.py.

## Hecho (previo)
- W11a paper_curve / brief urgency / ibc-checklist / freeze+urgency / schedule scripts.

## A medias
- Tiingo + hold-out + pia (Adam).

## Siguiente
- Paper vivo congelado sin retocar params.
- Cuando haya Tiingo: OOS hold-out una vez.

## No tocar
- Solo main. PASS ≠ deploy. Autopilot/reconcile sin órdenes LIVE.
