# RELEVO

## Hecho (2026-10-24, cursor — W13b)
- `autopilot.py`: after `max_dd` → `compare_paper_vs_oos(paper_max_dd=max_dd, paper_n_points=len(load_equity_points(...)), assumed_sharpe=0.8)`
- payload `paper_vs_oos` + Alert `paper_vs_oos_dd` / `kill_recommend` when flag set
- Kept W13a stack sync: `PaperStack.sync_from_json` + payload `paper_stack`
- Extended `tests/test_paper_vs_oos.py` with `test_kill_recommend_emits_expected_flags`
- pytest: test_paper_vs_oos + test_ai_brief_autopilot + test_autopilot_freeze_urgency + test_paper_stack → 10 passed
- Sin commit/push. No toqué `cli.py`.

## A medias
- Tiingo + hold-out + pia + Task Scheduler Register (Adam)
- Fase 3 calendario paper congelado (no código)

## Siguiente
- Heal/integrar W13 → push si Adam pide
- Si código Fase 3 cerrado: solo ops Adam + meses paper

## No tocar
- Solo main. PASS ≠ deploy. Cero órdenes LIVE.
- No dejar que Ollama reescriba `cli.py` entero (ni truncar `autopilot.py`).
