# RELEVO

## Hecho (2026-10-24, cursor — low-token AI + autopilot UI)
- `PromptPack`: model/max_tokens/effort/idioma/tono/prohibiciones parametrizados.
- `brief.py`: comprime radar+paper → hechos; brief determinista (0 tokens); IA opcional vía puerta (`--use-ai`, haiku, ≤400 tokens).
- `ibtrader autopilot [--open]`: backend pesado → HTML de una pantalla (`reports/autopilot/latest.html`).
- Extra opcional: `pip install '.[ai]'` (anthropic). Sin clave → siempre determinista.
- Tests: `test_ai_brief_autopilot.py`.

## Hecho (previo)
- Fase 3: slippage ledger, prob-fill, paper-reconcile, market radar PIT.

## A medias
- Tiingo + hold-out (Adam: token, DD, capital, horizonte).
- Token `pia_ibtrader_…` en env si se quiere brief con IA real.

## Siguiente
- Programar Task Scheduler: `ibtrader autopilot --open` diario (paper, 0 órdenes).
- Ampliar facts del brief solo con métricas ya calculadas (no noticias).

## No tocar
- Solo `main`. PASS ≠ deploy. Hold-out una vez.
- No LLM sobre titulares / alt-data de pago / intradía / apalancados.
- Autopilot no envía órdenes broker.

Escrito al cerrar turno cursor 2026-10-24 13:03.

