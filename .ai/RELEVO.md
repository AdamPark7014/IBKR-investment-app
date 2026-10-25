# RELEVO

## Hecho (2026-10-24, cursor — W12)
- `paper_curve`: `append_equity_point` + `estimate_mark_to_market`
- `urgency_age.load_open_order_age_seconds` ← `data/paper_open_orders.json`
- Autopilot: age real + MTM append a `paper_equity.jsonl` + DD alerts
- `paper_vs_oos.compare_paper_vs_oos` + CLI `ibtrader paper-vs-oos`
- Tests: urgency_age, paper_vs_oos, paper_curve_append — verdes
- Push: `ba0468c` en origin/main (incluye f8d8222 modules)

## A medias
- W13 agentes: README + stack sync autopilot + paper_vs_oos en payload
- Tiingo + hold-out + pia + Task Scheduler Register (Adam)
- Fase 3 calendario paper congelado (no código)

## Siguiente
- Integrar/heal W13 → push
- Si código Fase 3 cerrado: solo ops Adam + meses paper

## No tocar
- Solo main. PASS ≠ deploy. Cero órdenes LIVE.
- No dejar que Ollama reescriba `cli.py` entero (ya pasó; restaurar de HEAD).
