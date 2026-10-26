# RELEVO

## Hecho (2026-10-25 noche, claude-code — revisión y arreglo de lo de Cursor 23–25 oct)
- **CI**: estuvo roja del 24-10 (`7eabf12`) al 25-10 (`6a5bc12`): 20 corridas fallidas + 5 canceladas, todas
  en `ruff`, así que mypy y pytest **no corrieron en CI** en ese tramo. Arreglado: ruff 0 errores, mypy limpio
  (97 archivos), pytest offline 511 pasan (red bloqueada, 0 conexiones). La primera corrida con lint verde
  (40273486757) destapó lo que la CI roja escondía: `test_portfolio_runner_cli.py` importa `tests.…` y con el
  `pytest` plano de CI no se podía importar → `pythonpath = ["."]` en `pyproject.toml`.
- **Investigación (`94a3a6c`)**:
  - Escalar de forecast sin `bfill` (look-ahead de hasta 500 barras en la ventana evaluada); `warmup_end`
    espera a un escalar point-in-time.
  - Pesos de instrumento = riesgo: cajas `b_k/n_k` sin `1/σ`, HRP sobre `r_t/σ_{t-1}` (antes IEF cargaba
    35–58 % del riesgo). `box_inverse_vol` → `box_risk_parity` (alias).
  - `research-portfolio`: t ≥ 3, DSR ≥ 0,95 sobre todos los trials (ledger `reports/research/portfolio_trials.jsonl`),
    PBO < 0,5, percentil ≥ 95 vs carteras aleatorias, hold-out obligatorio, selección por DSR.
    Paseos aleatorios (semillas 7/11/23, grid completo): gates viejos pasaban 6/9 y 9/9; ahora 0/9.
  - Motor modo peso reintenta tras veto; costos OOS sin las órdenes del calentamiento.
- **Paper (`9a1eb78`)**: curva = caja + acciones × precio (`data/paper_account.json`) o NAV del broker
  (`paper-equity --append`); alertas de «matar» por DD apagadas hasta 20 días de equity real. Freeze schema 2
  (mode/trading/strategy), nunca se auto-escribe, `--write` no re-baselina sin `--force`. Orden de ejemplo
  fuera de `data/`. Brief IA sin `temperature` y solo por la puerta (`--use-ai` sin puerta sale 2).
  Simulador: LMT envejecida no cruza su límite; semilla 0 por defecto.
- **Repo (`e543123`)**: `.ai/drafts` (194) y `data/paper_*.json` fuera del índice.
- Freeze local reescrito a schema 2 (misma config, hash `1658a22e075133ca`); no se tocaron las tareas programadas.

## Corrección a lo que decía este RELEVO (Cursor, 25-10)
- «expectancy −$1886/trade» **engañaba**: es el promedio de solo 16 trades cerrados del OOS cosido y no cuenta la
  posición abierta. El fold 3 da expectancy −$2034 con P&L +$2,7k. Lo que vale es el P&L de la curva:
  OOS cosido CAGR ~3,4 %, Sharpe ~0,49 contra comprar y mantener 15,1 % / 0,94. La conclusión no cambia: el SMA
  sobre SPY pierde contra B&H; no retocar params con este OOS.

## A medias / pendiente
- `ibtrader-ibc-check` (08:00) solo imprime una lista fija que nadie ve: se puede quitar
  (`pwsh -File scripts/schedule-ibc-check.ps1 -Action Unregister`). Autopilot y reconcile: inofensivos (0 órdenes).
- El paper sigue sobre el motor viejo SMA/SPY; nada de fase 2 ha pasado gates con datos reales (no hay corridas).
- Vol target 10 % no se alcanza con `max_leverage=1.0` (realizada ~4–6 %); benchmarks con otra ventana si un ETF
  cotiza tarde. No arreglado (fuera de esta ronda).
- `research-portfolio --profile full` tarda ~6–8 min por corrida de 9 configuraciones.

## Adam
1. Tiingo + `RESEARCH__HOLDOUT_START` (sin hold-out declarado, `research-portfolio` siempre da FAIL).
2. Para medir paper de verdad: `data/paper_account.json` con `{"cash": …, "shares": {…}}` o
   `ibtrader paper-equity --append <NAV>` cada día.
3. Meses paper congelado.

## No tocar
- Solo main. Cero LIVE. No curve-fit al último fold. No re-baselinar el freeze para «arreglar» una alerta.
