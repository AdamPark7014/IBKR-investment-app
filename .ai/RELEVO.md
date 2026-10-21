# RELEVO

## Hecho (2026-10-21, claude-code)
- Checkout canónico movido a `C:/dev/apps/IBKR-INVESTMENT-app`; la copia vieja (27-09) quedó apartada en
  `C:/dev/tmp/IBKR-INVESTMENT-app-viejo-2026-09-27-borrar`.
- Fase 1 de hardening en `main`: gates estrictos deciden el PASS (Sharpe OOS ≥ 0.25 + ganar a B&H ajustado
  por riesgo); el engine emite `restricted_bar_frac` por barra (fail-closed); el registry exige hashes;
  `update_equity` fail-closed (`halt_next_day`); drawdown por defecto 20 %; bug `datetime.UTC`.
- Verificación: 171 passed, ruff y mypy limpios. Repo público desde hoy; CI verde en `main` con ubuntu + macOS
  (corrida 39640886952). ruff excluye `.ai/**` y `reports/**`.
- Investigación masiva (7 agentes, ~150 fuentes): `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` con
  arquitectura objetivo y plan por fases; anexos con fuentes en `docs/research/quant-funds-2026-10-21/`.

## A medias
- Ola D (shadow book, data fail-loud) sin empezar; queda absorbida por la fase 1 del playbook.

## Siguiente (según el playbook)
- Fase 1 (cimientos): proveedor de datos con delistings y manifiesto PIT (Tiingo/Massive), modelo de costos
  IBKR con sanidad ≥ 2.5–4 pb, golden files en CI, registro con N de pruebas y hold-out congelado.
- Fase 2 (sistema pesado): grafo de stages tipo pysystemtrade, EWMAC multi-velocidad + 1/3/12 m, risk parity
  por cajas + HRP, vol target 10 %, buffers ±10 %, benchmarks AOR/RPAR/SG Trend, validación completa.
- Antes de dimensionar: Adam debe dar drawdown máximo tolerado, capital inicial, horizonte y si existe la
  cuenta IBKR (y la entidad/W-8BEN para México).

## No tocar
- Solo `main`. Paper-run no envía órdenes (`allow_broker_orders=False` por defecto). PASS de gates ≠ deploy.
- No retocar parámetros con resultados del último mes; el hold-out se abre una sola vez.
