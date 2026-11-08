# RELEVO

## Hecho (2026-11-07, claude-code — conexión Tiingo e IBKR)
- Tiingo: token en `.env` (`DATA__TIINGO_TOKEN`, ignorado por `.gitignore:15`, nunca en git). Probado:
  `/tiingo/daily/SPY` responde OK (historia 1993-01-29 → 2026-11-06).
- IB Gateway 10.50 Stable instalado (firma válida de Interactive Brokers) en
  `%LOCALAPPDATA%\Programs\ibgateway\ibgateway.exe`. Todavía sin configurar la API: esa configuración se guarda
  por usuario después de iniciar sesión.
- Cuenta IBKR: solicitud «En curso», falta «Pending Document Upload». **No hay cuenta paper (DU…)**: IBKR la
  habilita al aprobar la cuenta (Settings > Paper Trading Account).
- Al existir la paper: entrar a Gateway en modo Paper → Configure > Settings > API > Settings: Socket Clients on,
  puerto 4002 (`IB__PAPER_PORT`), solo localhost on, Read-Only off (el sistema manda órdenes a paper).
- 08-11: solicitud con formularios completos; falta que IBKR valide el domicilio y acredite el primer depósito.
- Puerta IA: proyecto `ibkr` (Haiku 5.5, 5 USD/mes), token en `C:\dev\secrets\puerta-ia\ibkr.token`.
  **`ANTHROPIC_*` no pueden ir en `.env`**: `AppSettings` prohíbe claves extra y todo el CLI truena. Pasarlas al
  proceso (ver cómo en la prueba del copiloto). Extra `.[ai]` instalado en el venv (faltaba: `sdk_missing`).
- `.env`: `DATA__TIINGO_TOKEN`, `OPS__COPILOT=true`, `OPS__AI_MODEL=claude-haiku-5-5`. `copilot-research` probado
  por la puerta: 1 hipótesis, US$0.006.
- Freeze de paper **no vigente**: `hash_mismatch` en `execution` y `pretrade` (cambios de 4e2cc1f). No se
  re-baselinó: decide Adam (`config-freeze --write --force`).

## Hecho (2026-10-26, claude-code — los cinco pendientes de la revisión)
- `short_only`: el runner armaba un sistema long-only que el motor short-only anulaba (cero operaciones).
  Ahora `SystemConfig.short_only` (excluyente con `long_only`) recorta a ≤ 0 y el runner lo mapea desde
  `TRADING__DIRECTION`.
- Tope de apalancamiento: ya no reescala todo el renglón; solo se escalan los símbolos cuya posición cambió ese
  día. Antes 43 % de los cambios de peso (989/2318) ocurrían sin que la posición del símbolo cambiara; ahora 0.
- Benchmarks en la ventana exacta de la candidata (`start=warmup_end`); un ETF sin precio en la primera barra se
  excluye de todos los benchmarks con aviso (`excluded_symbols`, `note`) en vez de mover la ventana.
- Sesión del simulador con calendario NYSE: feriados (incl. Viernes Santo, Juneteenth, regla de Año Nuevo en
  sábado), cierres a las 13:00 y cierres especiales (2025-01-09 Carter, etc.). Probado contra 2024–2027.
- Vol target: con `max_leverage=1.0` el sistema pide 10 % y entrega ~6,6–6,9 % (el tope ata 43–49 % de los días,
  datos sintéticos). Documentado en `SystemConfig`; `research-portfolio` reporta `vol_target`
  (pedido, realizado = objetivo efectivo, fracción de días con tope, `shortfall`). **No se subió el apalancamiento**:
  llegar a 10 % pide ~1,5× con margen, decisión de Adam.

## Hecho (2026-10-25 noche, claude-code — revisión y arreglo de lo de Cursor 23–25 oct)
- **CI**: estuvo roja del 24-10 (`7eabf12`) al 25-10 (`6a5bc12`): 20 corridas fallidas + 5 canceladas, todas
  en `ruff`, así que mypy y pytest **no corrieron en CI** en ese tramo. Arreglado: ruff 0 errores, mypy limpio
  (97 archivos), pytest offline 511 pasan (red bloqueada, 0 conexiones). La primera corrida con lint verde
  (40273486757) destapó lo que la CI roja escondía: `test_portfolio_runner_cli.py` importa `tests.…` y con el
  `pytest` plano de CI no se podía importar → `pythonpath = ["."]` en `pyproject.toml` (`d56bf3d`).
  **CI verde** en `d56bf3d`: corrida 40274125812, 4/4 jobs (lint+types+tests y CLI smoke, ubuntu y macOS).
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
- Cierres especiales futuros (duelo nacional, etc.) hay que agregarlos a mano en `SPECIAL_CLOSURES`.
- `research-portfolio --profile full` tarda ~6–8 min por corrida de 9 configuraciones.

## Adam
1. Tiingo + `RESEARCH__HOLDOUT_START` (sin hold-out declarado, `research-portfolio` siempre da FAIL).
2. Para medir paper de verdad: `data/paper_account.json` con `{"cash": …, "shares": {…}}` o
   `ibtrader paper-equity --append <NAV>` cada día.
3. Meses paper congelado.
4. Decidir si el objetivo de vol es el efectivo (~6–7 % sin margen) o se pide margen para `max_leverage` 1,5×.

## No tocar
- Solo main. Cero LIVE. No curve-fit al último fold. No re-baselinar el freeze para «arreglar» una alerta.
