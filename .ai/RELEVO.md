# RELEVO

## Hecho (2026-10-24, cursor — W13a)
- README paper ops: bullets `ibtrader paper-stack`, `slippage-report`, `paper-vs-oos` (JSON, cero órdenes)
- `autopilot.py`: tras desired/held → `PaperStack(.../paper_stack.sqlite).sync_from_json(desired, held)`; payload opcional `paper_stack.n_drift`
- pytest `tests/test_paper_stack.py` + `tests/test_ai_brief_autopilot.py` OK
- Sin commit/push. No toqué `cli.py`.

## A medias
- W13b: wire `compare_paper_vs_oos` into autopilot payload (otro agente)
- Tiingo + hold-out + pia + Task Scheduler Register (Adam)
- Fase 3 calendario paper congelado (no código)

## Siguiente
- Completar W13b → heal/integrar → push
- Si código Fase 3 cerrado: solo ops Adam + meses paper

## No tocar
- Solo main. PASS ≠ deploy. Cero órdenes LIVE.
- No dejar que Ollama reescriba `cli.py` entero.
