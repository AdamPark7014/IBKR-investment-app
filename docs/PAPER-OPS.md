# Paper ops — Fase 3 (triage)

Operación diaria de **paper disciplinado**. Cero órdenes LIVE. `MODE=PAPER`.
Playbook: `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` (Fase 3).

## Qué es

Fase 3 = meses de calendario con la **misma config congelada**, midiendo drift,
slippage y curva paper vs OOS. El código ya está; el trabajo de Adam es
registrar tareas, datos y **no retocar** parámetros con el último mes.

Todo comando aquí imprime JSON y, en modo sombra, envía **0 órdenes**.

## Corrida diaria única (desde 07-11-2026)

Un solo camino datos → objetivos → riesgo → orden, en dos fases. Es el único camino desde el 08-11-2026.

```text
ibtrader run-daily --phase plan      # tras el cierre: datos + frescura + contraste, freeze, pesos objetivo,
                                     # regla de drawdown, pre-trade; sombra = fills simulados con costes
ibtrader run-daily --phase execute   # tras la apertura: concilia, envía pending_orders.json, vuelve a conciliar
ibtrader heartbeat-check             # alerta crítica si la corrida no reportó en 30 h
ibtrader scorecard                   # calidad del modelo en números (meta + pass/fail/insufficient)
ibtrader ai-review                   # git diff → Claude vía puerta (look-ahead, fugas, bypass de riesgo)
```

- **Modo** (`EXECUTION__MODE`): `shadow` por defecto (cero órdenes). `paper_orders` exige
  `TRADING__ALLOW_BROKER_ORDERS=true`, Gateway paper (4002) y un freeze vigente; `live_orders` además
  `MODE=LIVE` y `LIVE_TRADING_CONFIRMED=yes`.
- **Códigos de salida**: 0 normal, 1 bloqueo seguro (datos viejos, pending caducado), 2 requiere humano
  (descuadre con el broker → kill switch, error de datos).
- **Órdenes idempotentes**: `orderRef = ibt-AAAAMMDD-SÍMBOLO-LADO`; si ya existe en el broker no se reenvía.
- **Freeze**: el snapshot incluye ahora `pretrade` y `execution`; tras el veredicto de investigación hay que
  rehacerlo con `config-freeze --write --force`.

Programación (Windows). El plan corre a las 19:00 de Nueva York porque Tiingo publica el cierre hacia las 17:30–18:00 ET; antes vería el bar de ayer y bloquearía:

```powershell
pwsh -File scripts/schedule-run-daily.ps1 -Action Register -PlanTime 19:00 -ExecuteTime 10:05   # horas de Nueva York; conviértelas a tu zona
```

Archivos nuevos en `data/`: `pending_orders.json` (→ `.done.json` / `.stale.json`), `orders.jsonl`
(ciclo de vida de cada orden), `alerts.jsonl`, `heartbeat.json`, `ai_usage.jsonl` (coste de Claude).
Informes por día en `reports/daily/`.

## Otros comandos (cero órdenes)

```text
ibtrader paper-stack            # desired/held/drift → data/paper_stack.sqlite
ibtrader paper-vs-oos           # DD paper vs Sharpe/DD OOS asumidos (kill_recommend)
ibtrader slippage-report        # resumen de data/slippage_ledger.jsonl
ibtrader ibc-checklist          # checklist Gateway/IBC (manual; no instala)
ibtrader config-freeze          # --verify (default) o --write → paper_config_freeze.json
ibtrader paper-equity           # curva/resumen de data/paper_equity.jsonl (--append = NAV del broker)
ibtrader paper-status           # presencia + resúmenes freeze/equity/stack/open-orders/slippage
```

`autopilot`, `paper-run` y `paper-reconcile` (motor de fase 1) se eliminaron el 08-11-2026.

## Copiloto de Claude (nunca envía órdenes)

Con `OPS__COPILOT=true` y la puerta configurada, después de cada `run-daily --phase plan` Claude:

- lee los hechos del día (objetivos, pesos, retornos recientes, caída, alertas);
- opina por ETF (`aumentar` / `mantener` / `reducir`, convicción 1-3);
- explica en español por qué el sistema hace lo que hace.

Las opiniones quedan en `data/copilot_opinions.jsonl` con los cierres del día. El plan y las órdenes no cambian.

- **Medición:** `ibtrader scorecard` → bloque `copiloto`. Compara la cartera "sistema + inclinación de Claude"
  (±20 % como máximo por ETF, mismo bruto, sin apalancamiento) contra el sistema solo, usando únicamente precios
  posteriores a cada opinión. Hacen falta 126 sesiones y t ≥ 3 para decir que aporta.
- **Investigación:** `ibtrader copilot-research` lee el último `research-portfolio` y propone hasta 3 hipótesis
  con reglas que ya existen. Luego se pasan por la compuerta con
  `ibtrader research-portfolio --profile full --hypotheses reports/research/copilot_hypotheses.json`.
  Cada hipótesis cuenta como una prueba más en el DSR.
- **Token de la puerta:** no va en `.env`, porque la configuración rechaza claves desconocidas. Las tareas
  programadas lo leen con `scripts/run-task.ps1` desde `C:\dev\secrets\puerta-ia\ibkr.token` (o desde la
  ruta en `IBTRADER_PUERTA_TOKEN_FILE`). Sin ese archivo, el sistema corre igual con Claude apagado. Después de
  actualizar, vuelve a registrar las tareas (`schedule-run-daily.ps1 -Action Register`).
- **Coste:** cada llamada queda en `data/ai_usage.jsonl`. Se detiene al llegar a `OPS__AI_MONTHLY_BUDGET_USD`.
- **Por qué no decide órdenes:** Claude ya "vio" el pasado al entrenarse, así que un backtest de sus decisiones
  está contaminado. La única prueba limpia es hacia adelante, en sombra.

## Tareas programadas (Windows)

```powershell
pwsh -File scripts/schedule-register-all.ps1 -Action Register   # run-daily plan/execute, heartbeat-check, ibc-check
pwsh -File scripts/ops-smoke.ps1                                 # Status
pwsh -File scripts/ops-smoke.ps1 -Action RunOnce                 # ibc-checklist → run-daily → heartbeat-check → scorecard
```

## Archivos bajo `data/`

| Archivo | Rol |
|---------|-----|
| `paper_account.json` | Libro paper real: `{"cash": 100000, "shares": {"SPY": 120}}` (base de la curva) |
| `paper_positions.json` | Pesos held (fracción del NAV) para el drift; **no** es equity |
| `paper_equity.jsonl` | Curva: un punto por día de mercado, `basis` `shadow` / `broker` (run-daily) o `nav` (`paper-equity --append`) |
| `paper_open_orders.json` | Solo órdenes paper reales; el ejemplo va a `paper_open_orders.sample.json` y se ignora |
| `paper_config_freeze.json` | Hash de config congelada |
| `paper_stack.sqlite` | Desired / held / drift |
| `slippage_ledger.jsonl` | Fills sim: decisión vs fill |

No commitear secretos ni dumps LIVE. Estos JSON/SQLite son locales de ops.

## Qué hace Adam (humano)

1. **Tiingo** (o proveedor EOD serio) en `.env` / providers — yfinance no es el
   piso institucional a largo plazo.
2. **Hold-out una vez** por hipótesis (`research-run --confirmation`); si FAIL,
   idea muerta — no retocar con esas barras.
3. **`pia_…` opcional** (pack / brief IA) solo sobre JSON ya comprimido; sin
   titulares ni noticias.
4. **Registrar** las tareas programadas (`schedule-register-all` o `schedule-run-daily.ps1 -Action Register`) y
   comprobar todo con `ibtrader chequeo`.
5. **Meses congelados**: tras `config-freeze --write`, no cambiar params porque
   el DD del mes “no cuadra”. Matar solo si `paper-vs-oos` / alertas lo dicen.

## El día que IBKR apruebe la cuenta paper

Mientras tanto el sistema corre en **sombra** con datos de Tiingo y no necesita a IBKR. Cuando llegue el acceso:

1. Abre IB Gateway en modo **paper**. En Configure → API → Settings activa "Enable ActiveX and Socket Clients",
   puerto **4002**, Trusted IPs = solo 127.0.0.1.
2. Corre `ibtrader chequeo`. Todo tiene que salir `ok: true` menos `permiso_ordenes`. Si `gateway_ibkr` falla,
   el Gateway no está escuchando en 4002.
3. Opcional: `IB__EXPECTED_ACCOUNT=DU…` en `.env`, para que el sistema se niegue a operar en otra cuenta.
4. Cambia en `.env`: `EXECUTION__MODE=paper_orders` y `TRADING__ALLOW_BROKER_ORDERS=true`. Deja `MODE=PAPER`.
5. `ibtrader config-freeze --write --force` (re-congela con el modo nuevo) y otra vez `ibtrader chequeo`. Ahora
   `listo_paper` debe ser `true`.
6. Nada más: las tareas programadas ya existen. El plan de las 19:00 deja `pending_orders.json` y la ejecución
   de las 10:05 lo envía, reconcilia con el broker y registra el slippage.
7. Dinero real solo cuando `ibtrader scorecard` diga `ready_for_live: true` (126 sesiones en paper).

## Prohibido (playbook §119 / “Lo que no entra”)

En paper triage **no**:

- LLM sobre **titulares** / noticias
- **Alt-data de pago**
- Señales **intradía**
- Retocar parámetros con el último mes de paper
- Cualquier camino a **LIVE** desde estos comandos

Autopilot `--use-ai` ≠ LLM de titulares: es brief corto sobre payload ya
calculado vía puerta IA del proyecto.

## Checklist rápido del día

```text
[ ] Gateway paper arriba (puerto 4002) — ibc-checklist
[ ] config-freeze verify ok
[ ] run-daily plan/execute y heartbeat-check programados (schedule-register-all)
[ ] mirar drift (paper-stack) y DD (paper-vs-oos)
[ ] no tocar freeze / params
```

Ver también: README (comandos paper), `docs/research/PROTOCOLO-INVESTIGACION.md`.
