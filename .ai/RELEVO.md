# RELEVO

## Hecho (2026-10-25, cursor — W14a)
- `simple_ui.py`: 3 cards extra en `render_simple_console` — Urgency / Stack drift / vs OOS
- Urgency: `payload.urgency.mode` (o str) → fallback `facts.extra.urgency_mode`
- Stack drift: `paper_stack.n_drift` (preserva 0)
- vs OOS: `paper_vs_oos.dd_ok` → OK / BREACH / —
- Nuevo `tests/test_simple_ui.py` (3 tests) — pytest 3 passed
- Sin commit/push (relevo cerrar auto-commiteó; undid `git reset HEAD~1` → tip sigue `7e3a3fc`)
- No toqué `autopilot.py`, `cli.py`, `simulated.py`

## A medias
- Tiingo + hold-out + pia + Task Scheduler Register (Adam)
- Fase 3 calendario paper congelado (no código)
- Otros WIP en árbol ajenos a W14a: `README.md`, `scripts/ops-smoke.ps1`, drafts

## Siguiente
- Commit W14a solo si Adam pide (solo simple_ui + test_simple_ui)
- No incluir ops-smoke/README de otros agentes en el mismo commit

## No tocar
- Solo main. PASS ≠ deploy. Cero órdenes LIVE.
- No dejar que Ollama reescriba `cli.py` entero (ni truncar `autopilot.py`).
