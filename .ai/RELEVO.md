# RELEVO

## Hecho (2026-10-25, cursor — W14d)
- `src/ibtrader/broker/simulated.py`: ctor `order_age_seconds` / `max_passive_seconds`; LMT calls `decide_urgency`; aggressive → MKT-like `total_order_cost` fill; `partial_fill_frac` solo path no-aggressive; RTH reject no limpia `last_latency_ms`
- `tests/test_sim_prob_fill.py`: `test_aged_lmt_fills_aggressive_even_if_limit_far` (limit far + age≥window + prob_fill=0 → fill; young control → no fill)
- pytest `test_sim_prob_fill` + `test_broker_sim` → 9 passed
- Sin commit/push. No toqué cli/autopilot/simple_ui.

## A medias
- W14a simple_ui cards / W14b ops-smoke / W14c config-freeze (otros agentes)
- Adam: Tiingo + hold-out + pia + Task Scheduler Register
- Calendario: paper congelado meses

## Siguiente
- Integrar/heal/push W14 cuando cierren a–c
- Si no quedan huecos Fase 3 código → parar oleadas

## No tocar
- Solo main. Cero LIVE. No reescribir `cli.py` entero con Ollama.
