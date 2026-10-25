# Paper ops — Fase 3 (triage)

Operación diaria de **paper disciplinado**. Cero órdenes LIVE. `MODE=PAPER`.
Playbook: `docs/research/QUANT-FUNDS-PLAYBOOK-2026-10-21.md` (Fase 3).

## Qué es

Fase 3 = meses de calendario con la **misma config congelada**, midiendo drift,
slippage y curva paper vs OOS. El código ya está; el trabajo de Adam es
registrar tareas, datos y **no retocar** parámetros con el último mes.

Todo comando aquí imprime JSON (o HTML de autopilot) y envía **0 órdenes**.

## Comandos CLI

```text
ibtrader autopilot              # triage + UI; opcional --use-ai (puerta IA, sin noticias)
ibtrader paper-reconcile        # desired vs data/paper_positions.json (+ slippage si hay ledger)
ibtrader paper-stack            # desired/held/drift → data/paper_stack.sqlite
ibtrader paper-vs-oos           # DD paper vs Sharpe/DD OOS asumidos (kill_recommend)
ibtrader slippage-report        # resumen de data/slippage_ledger.jsonl
ibtrader ibc-checklist          # checklist Gateway/IBC (manual; no instala)
ibtrader config-freeze          # --verify (default) o --write → paper_config_freeze.json
ibtrader paper-equity           # curva/resumen de data/paper_equity.jsonl (--append opcional)
```

Notas breves:

- `autopilot` escribe/verifica freeze, sync de stack, append a `paper_equity.jsonl`,
  compara vs OOS y abre HTML de una pantalla (`--open`).
- `config-freeze --write` una vez al congelar; luego solo `--verify` (o default).
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
pwsh -File scripts/ops-smoke.ps1                 # Status de las 3 tareas
pwsh -File scripts/ops-smoke.ps1 -Action RunOnce # ibc-checklist → reconcile → vs-oos → stack
```

Atajo (las tres tareas):

```powershell
pwsh -File scripts/schedule-register-all.ps1 -Action Register   # Status|Unregister igual
```

## Archivos bajo `data/`

| Archivo | Rol |
|---------|-----|
| `paper_positions.json` | Posiciones held (paper) |
| `paper_equity.jsonl` | Curva MTM (append diario vía autopilot) |
| `paper_open_orders.json` | Órdenes abiertas simuladas / shadow |
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
