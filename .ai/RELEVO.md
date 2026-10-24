# RELEVO

## Hecho (2026-10-24, cursor — Ola D cierre)
- Repo canónico sigue en `C:/dev/apps/IBKR-INVESTMENT-app` (`C:/dev/ibkr-investment-app` no existe en disco).
- **Ola D restante:** `ops/shadow.py` (log desired vs held), hook `paper-run --shadow`; `stats_json` expone
  `restricted_bar_frac` desde el engine; docstrings de `resolve_restricted_bar_frac` al día; `normalize_yf` fail-loud
  en flatten MultiIndex.
- D2 / registry hashes / walk-forward `restricted_bar_frac` ya estaban en main desde hardening fase 1 (2026-10-21).

## Hecho (2026-10-21, claude-code)
- Checkout canónico `C:/dev/apps/IBKR-INVESTMENT-app`; repo público; CI verde en `main` (ubuntu + macOS).
- Hardening fase 1 (gates estrictos, `restricted_bar_frac`, hashes, fail-closed) y playbook
  `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` con 7 anexos.
- **Fase 1 del playbook (cimientos)**, tres agentes en paralelo:
  - Datos PIT: `TiingoProvider` (token `DATA__TIINGO_TOKEN`, backoff 429), vintages parquet por
    `vintage_date` + `manifest.json` con SHA-256 (`data/vintage.py`), universo con ciclo de vida
    (`config/universe-10etf.json`, `data/universe.py`), validadores ruidosos (`validate_pit`) y
    `service.py` sin `except Exception` silenciosos. Fixtures no entran al almacén de vintages.
  - Costos IBKR (`execution/costs.py`, `COST_MODEL.md`): comisión Fixed/Tiered con mínimo y tope,
    cuotas regulatorias en ventas (SEC, TAF en pausa hasta 2026-12-31, CAT), medio spread por símbolo e
    impacto raíz cuadrada; métricas `total_costs`, `avg_cost_bps_per_order`, `cost_drag_annual_pct`;
    `cost_model_suspicious` en el honest report si el modelo sale más barato que 2.5 pb.
  - Disciplina: `n_trials`, presupuesto `years_needed = 2·ln N / SR²` y gate `trial_budget_exceeded`;
    hold-out congelado (`RESEARCH__HOLDOUT_START`, `research-run --confirmation`, aperturas en
    `reports/research/holdout_openings.jsonl`, `holdout_overused`); golden files en `tests/golden/`
    (`ibtrader golden-regen --yes`); `docs/research/PROTOCOLO-INVESTIGACION.md`.
- Config nueva en `config.py`: `CommissionConfig` ampliada, `RegFeesConfig`, `SlippageConfig`
  (`spread_impact` por defecto), `DataConfig` (tiingo, vintages, universo, spikes), `ResearchConfig`.

## A medias
- `broker/simulated.py` (paper) sigue con comisión y bps legados; los runners de research no exponen
  aún `avg_cost_bps_per_order` por fila (el honest report usa la estimación del modelo).
- Si un benchmark queda excluido por validación, `ops/cli.py` hace `data[bench]` y daría KeyError.
- `data/vintages/` local trae un snapshot del fixture creado antes de la guarda; borrar antes de la
  primera descarga real (está en .gitignore).

## Siguiente (fase 2 del playbook)
- Grafo de stages tipo pysystemtrade (forecast → escala ±20 → combinación FDM → vol target 10 % →
  pesos × IDM → buffers ±10 %), EWMAC multi-velocidad + 1/3/12 m, risk parity por cajas + HRP sobre
  `config/universe-10etf.json`, benchmarks AOR/RPAR/SG Trend y carteras aleatorias.
- Antes de dimensionar: Adam debe dar drawdown máximo tolerado, capital inicial, horizonte, cuenta IBKR
  y entidad/W-8BEN; y un token de Tiingo (Starter gratis) para la primera descarga real.

## No tocar
- Solo `main`. Paper-run no envía órdenes. PASS de gates ≠ deploy. El hold-out se abre una sola vez;
  no retocar parámetros con resultados del último mes.
