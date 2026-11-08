# Paper ops — Fase 3 (triage)

Operación diaria de **paper disciplinado**. Cero órdenes LIVE. `MODE=PAPER`.
Playbook: `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` (Fase 3).

## Qué es

Fase 3 = meses de calendario con la **misma config congelada**, midiendo drift,
slippage y curva paper vs OOS. El código ya está; el trabajo de Adam es
registrar tareas, datos y **no retocar** parámetros con el último mes.

Todo comando aquí imprime JSON (o HTML de autopilot) y envía **0 órdenes**.

## Corrida diaria única (desde 07-11-2026)

Un solo camino datos → objetivos → riesgo → orden, en dos fases. Sustituye a `autopilot` /
`paper-reconcile` para operar; esos siguen existiendo para el triage viejo.

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

Programación (Windows; horas locales del PC = cierre NYSE + 45 min y apertura + 10 min):

```powershell
pwsh -File scripts/schedule-run-daily.ps1 -Action Register -PlanTime 16:45 -ExecuteTime 09:40
```

Archivos nuevos en `data/`: `pending_orders.json` (→ `.done.json` / `.stale.json`), `orders.jsonl`
(ciclo de vida de cada orden), `alerts.jsonl`, `heartbeat.json`, `ai_usage.jsonl` (coste de Claude).
Informes por día en `reports/daily/`.

## Comandos CLI (triage fase 3)

```text
ibtrader autopilot              # triage + UI; opcional --use-ai (puerta IA, sin noticias)
ibtrader paper-reconcile        # desired vs data/paper_positions.json (+ slippage si hay ledger)
ibtrader paper-stack            # desired/held/drift → data/paper_stack.sqlite
ibtrader paper-vs-oos           # DD paper vs Sharpe/DD OOS asumidos (kill_recommend)
ibtrader slippage-report        # resumen de data/slippage_ledger.jsonl
ibtrader ibc-checklist          # checklist Gateway/IBC (manual; no instala)
ibtrader config-freeze          # --verify (default) o --write → paper_config_freeze.json
ibtrader paper-equity           # curva/resumen de data/paper_equity.jsonl (--append = NAV del broker)
ibtrader paper-status           # presencia + resúmenes freeze/equity/stack/open-orders/slippage
```

Notas breves:

- `autopilot` **verifica** el freeze (nunca lo escribe), sincroniza el stack y, si existe
  `paper_account.json`, agrega el punto del día = caja + acciones × precio. Las alertas de «matar» por
  drawdown (`dd_vs_sharpe`, `paper_vs_oos_dd`) están apagadas hasta tener 20 días de equity real y lo dice
  una alerta `paper_kill_alerts_inactive`. Cambiar la config (incluidos `mode`, `trading`, `strategy`)
  con el freeze puesto da `config_drift` aunque el archivo exista.
- `config-freeze --write` una vez al congelar; luego solo `--verify` (o default). Si la config cambió,
  `--write` se niega (sale 1); `--force` solo para re-baselinar a propósito.
- `paper-equity` lee/resume la curva; autopilot sigue haciendo el append diario.

## Schedules (Task Scheduler, Windows)

| Tarea | Script | Hora default |
|-------|--------|--------------|
| `ibtrader-autopilot` | `scripts/schedule-autopilot.ps1` | 16:30 |
| `ibtrader-paper-reconcile` | `scripts/schedule-reconcile.ps1` | 16:35 |
| `ibtrader-ibc-check` | `scripts/schedule-ibc-check.ps1` | 08:00 |

Acciones comunes: `-Action Register|Unregister|Status` (+ `RunOnce` en IBC).
Hora: `-Time HH:mm`.

```powershell
pwsh -File scripts/schedule-autopilot.ps1 -Action Register
pwsh -File scripts/schedule-reconcile.ps1 -Action Register
pwsh -File scripts/schedule-ibc-check.ps1 -Action Register
```

Smoke (sin LIVE):

```powershell
pwsh -File scripts/bootstrap-paper.ps1           # freeze --write + paper-status (no schtasks, sin datos de ejemplo)
pwsh -File scripts/ops-smoke.ps1                 # Status de las 3 tareas
pwsh -File scripts/ops-smoke.ps1 -Action RunOnce # ibc-checklist → reconcile → vs-oos → stack
```

`bootstrap-paper.ps1` = triage only (0 órdenes, NO LIVE); no registra Task Scheduler.

Atajo (las tres tareas):

```powershell
pwsh -File scripts/schedule-register-all.ps1 -Action Register   # Status|Unregister igual
```

## Archivos bajo `data/`

| Archivo | Rol |
|---------|-----|
| `paper_account.json` | Libro paper real: `{"cash": 100000, "shares": {"SPY": 120}}` (base de la curva) |
| `paper_positions.json` | Pesos held (fracción del NAV) para el drift; **no** es equity |
| `paper_equity.jsonl` | Curva: un punto por día de mercado, `basis` `cash+shares` (autopilot) o `nav` (`paper-equity --append`) |
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
4. **Register** Task Scheduler (`schedule-register-all` o los tres scripts).
5. **Meses congelados**: tras `config-freeze --write`, no cambiar params porque
   el DD del mes “no cuadra”. Matar solo si `paper-vs-oos` / alertas lo dicen.

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
[ ] autopilot / reconcile programados o corridos a mano
[ ] mirar drift (paper-stack) y DD (paper-vs-oos)
[ ] no tocar freeze / params
```

Ver también: README (comandos paper), `docs/research/PROTOCOLO-INVESTIGACION.md`.
