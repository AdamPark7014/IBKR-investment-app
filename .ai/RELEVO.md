# RELEVO

## Hecho (2026-10-21, claude-code)
- Checkout canónico movido a `C:/dev/apps/IBKR-INVESTMENT-app`; la copia vieja (27-09) quedó apartada en
  `C:/dev/tmp/IBKR-INVESTMENT-app-viejo-2026-09-27-borrar` (sus reportes HTML únicos ya se copiaron a `reports/`).
- Fase 1 de hardening: gates estrictos deciden el PASS (Sharpe OOS ≥ 0.25 + ganar a B&H ajustado por riesgo);
  el engine emite `restricted_bar_frac` por barra (fail-closed) y walk-forward/runners lo escriben en stats OOS;
  el registry exige `dataset_hash`/`config_hash`; `update_equity` fail-closed (`halt_next_day`);
  drawdown por defecto 20 %; bug `datetime.UTC` en `market-analyze`.
- Verificación: 171 passed, ruff y mypy limpios. CI ahora corre en `main` con ubuntu + macOS (antes solo
  escuchaba `dev` y `cursor/**`, así que `main` nunca tuvo CI).

## A medias
- Ola D: shadow book (`ops/shadow.py`) y data fail-loud sin empezar.

## Siguiente
- Mirar la corrida de Actions en `main` (los jobs macOS). Si el repo sigue privado, macOS cuesta 10x minutos.
- Fase 2: universo de ~10 ETFs (paridad de riesgo, TSMOM, dual momentum) contra 60/40 con periodo de
  confirmación congelado. SMA sobre SPY no tiene edge (CAGR 0.4 % vs 11.7 % buy & hold).

## No tocar
- Solo `main`. Paper-run no envía órdenes (`allow_broker_orders=False` por defecto). PASS de gates ≠ deploy.
