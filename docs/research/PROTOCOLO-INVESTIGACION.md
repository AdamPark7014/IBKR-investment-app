# Protocolo de investigación de `ibtrader` (fase 1 del playbook)

Checklist operativa del "protocolo mínimo para un individuo" del anexo 2
(`quant-funds-2026-10-21/02-validacion-anti-overfitting.md`), aterrizado a lo
que este repo ya ejecuta por código: `research/suite.py` (hold-out y conteo de
pruebas), `research/gates.py` (umbrales), `research/registry.py` (bitácora) y
`ops/cli.py` (`research-run`, `golden-regen`). Cada punto dice qué se hace, qué
bandera lo deja escrito y qué pasa si se incumple. Referencias: Bailey, Borwein,
López de Prado & Zhu 2014 (PBO y presupuesto de pruebas), Bailey & López de Prado
2014 (DSR), Harvey & Liu 2015 (hold-out y haircut), Harvey, Liu & Zhu 2016
(t ≥ 3), Arnott, Harvey & Markowitz 2019 (hipótesis previa, no retocar en vivo),
Man AHL 2015 (esperar ~0,8× el Sharpe del backtest).

La regla que resume todo: **un backtest es una prueba de hipótesis con
múltiples comparaciones, no una demostración**. Sin N (cuántas configuraciones
se probaron) no hay DSR, PBO ni presupuesto; sin hold-out congelado no hay
confirmación; sin paper no hay implementación verificada.

---

## 0. Antes de tocar datos: hipótesis escrita

- [ ] Escribe en `docs/research/hipotesis/<fecha>-<nombre>.md` (o en la nota del
      `exp_id`): **causa → efecto**, quién pierde al otro lado (¿por qué existe
      la prima?), universo, horizonte, y el **Sharpe esperado** (realista: 0,5–0,8
      neto para tendencia/carry diversificado; un SR < 0,4 no sobrevive al haircut).
- [ ] Declara la **partición de datos** en el mismo documento: entrenamiento,
      validación (walk-forward / CPCV) y el hold-out congelado (fecha exacta).
- [ ] Fija el **presupuesto de pruebas** que te vas a permitir (cuántas
      configuraciones, ver §2) antes de la primera corrida.

Si la hipótesis se escribe después de ver resultados, la corrida es exploración,
no evidencia: no cuenta para pasar a paper.

## 1. Partición declarada: `RESEARCH__HOLDOUT_START`

- [ ] En `.env` (o en la línea de comandos): `RESEARCH__HOLDOUT_START=YYYY-MM-DD`.
      Recomendación del playbook: **los últimos 1–2 años**.
- [ ] Cualquier `research-run` normal **recorta todos los símbolos a barras
      anteriores a esa fecha antes de que corra cualquier track** (SMA, TSMOM,
      reversión, rotación, overlays, PBO, CPCV, DSR, analizador). El resumen y el
      registry lo dejan escrito: `holdout_applied=True`, `n_bars_hidden`,
      `data_end < holdout_start`.
- [ ] Si la fecha cae fuera del rango de datos (antes de la primera barra o
      después de la última) la corrida **falla con error claro**: un hold-out que
      no oculta nada, o que lo oculta todo, es una configuración rota.
- [ ] Un hold-out solo sirve si hay ≥ 1.000 observaciones diarias en total; con
      menos, usa CPCV y no te engañes con una confirmación de 60 barras.

## 2. Presupuesto de pruebas: `n_trials`, `years_needed`, `budget_ok`

Cada configuración evaluada cuenta como una prueba, pase o no pase. En
`ibtrader`:

| Campo | Qué es | Dónde |
|---|---|---|
| `n_trials` | Número de filas candidatas evaluadas en la corrida: todas las familias y todas las variantes de rejilla (SMA grid, regime, escalera de costos, TSMOM, reversión, overlays, rotación, cross-section). Las repeticiones del mismo par bajo otro costo también cuentan: es conservador a propósito. | resumen de la suite, payload del CLI, cada fila del registry |
| `years_available` | Años de datos realmente usados (sin el hold-out) del símbolo principal. | ídem |
| `years_needed` | `2·ln(n_trials) / SR_objetivo²` con `SR_objetivo = RESEARCH__TRIAL_BUDGET_TARGET_SHARPE` (1,0 por defecto). Con una sola prueba es 0. | ídem |
| `budget_ok` | `years_available ≥ years_needed`. | ídem; `gate_checks.budget_ok` |

Tabla de referencia con SR objetivo 1,0 (anexo 2): 2 años → ≤ 7 pruebas; 5 años
→ ≤ 45; 10 años → ~200; 14 años → ~1.000. Con SR objetivo 0,5 los años se
**cuadruplican**. López de Prado: ~20 iteraciones ya producen una estrategia falsa
al 5 %.

- [ ] Si `budget_ok=False` y `RESEARCH__FAIL_ON_BUDGET_EXCEEDED=true` (por
      defecto), **todas las filas fallan** con razón `trial_budget_exceeded`. No
      se "arregla" bajando el SR objetivo ni quitando filas del conteo: se arregla
      con más años de datos o con menos pruebas.
- [ ] Si lo apagas (`false`) para explorar, el veredicto no cambia pero
      `gate_checks.budget_ok=False` y `budget_warning` quedan escritos. Esa
      corrida no cuenta como evidencia.
- [ ] `n_trials` es también la **N real del DSR** (`dsr.n_trials`); la rejilla SMA
      sola queda en `dsr.n_grid_trials`. Un DSR calculado con N = 3 cuando
      probaste 40 cosas es una mentira contable.
- [ ] Lleva la cuenta **entre corridas**: el presupuesto de la suite es por
      corrida; el de tu hipótesis es acumulado. Suma los `n_trials` de todos los
      `experiments_*.jsonl` del mismo `exp_id`/hipótesis antes de decidir.

## 3. Umbrales (gates estrictos)

Para que una fila sea `PASS` en `research-run` deben cumplirse **todos**:

| Umbral | Valor | Bandera |
|---|---|---|
| Sharpe OOS (walk-forward cosido, con costos) | ≥ 0,25 | `oos_sharpe_ok` |
| Operaciones OOS | ≥ 5 | `trade_count_ok` |
| Max DD vs Buy & Hold | no peor por más de 5 pp | `dd_ok` |
| Lockout de riesgo | ≤ 50 % de barras OOS, **medido** (no supuesto) | `lock_ok`, `restricted_bar_frac_assumed` |
| Ganar al Buy & Hold ajustado a riesgo | Sharpe > B&H, o a ≤ 0,10 del B&H con DD ≥ 5 pp menos profundo | `beats_bh_ok` |
| PBO (CSCV, S = 16) | ≤ 0,05 | `pbo_high_overfit_risk` |
| DSR con N real | ≥ 0,95 | `dsr_ok` |
| CPCV | distribución no frágil | `fragile_cpcv` |
| Presupuesto de pruebas | `budget_ok` | `budget_ok`, `trial_budget_exceeded` |
| Hold-out | no sobreusado | `holdout_overused` |

Además, antes de pasar a paper, calcula a mano: **t = SR·√años ≥ 3** sobre el
periodo OOS (con SR 1 hacen falta 9 años; con SR 0,5, 36). Si no llegas, el
resultado es "prometedor", no "significativo", y se documenta así.

PASS ≠ permiso de despliegue. PASS = la idea merece la **única** apertura del
hold-out.

## 4. Una sola apertura del hold-out: `research-run --confirmation`

- [ ] El hold-out se abre **una vez por hipótesis** y solo con el flag escrito
      a mano: `ibtrader research-run --exp-id <id> --confirmation`. La variable
      `RESEARCH__CONFIRMATION_MODE` sola **no abre nada**: el CLI la ignora con
      aviso y corre con el hold-out cerrado.
- [ ] Al abrir, el CLI imprime en rojo que está usando barras ≥ `holdout_start`
      y el número de apertura, y deja una línea en
      `<reports>/research/holdout_openings.jsonl`:
      `{opened_at_utc, exp_id, git_commit, holdout_start, opening_no, ...}`.
      El resumen y el registry llevan `holdout_opened=True`.
- [ ] `RESEARCH__MAX_HOLDOUT_OPENINGS=1`. La segunda apertura del mismo
      `holdout_start` **sigue corriendo** (para que quede constancia) pero cada
      fila sale `FAIL` con `holdout_overused=True`; el registry lo guarda en
      `extra.holdout_overused` y `extra.holdout_opening_no`.
- [ ] **Si falla en el hold-out, la idea está muerta.** No se retoca con esas
      barras, no se "ajusta un parámetro", no se cambia la fecha del hold-out para
      estrenar un contador nuevo. Cambiar `holdout_start` después de abrirlo es
      trampa aunque el software te lo permita; el JSONL deja la evidencia.
- [ ] El archivo `holdout_openings.jsonl` no se borra. Si hay que empezar de
      cero (datos nuevos, hipótesis nueva), se declara otro `holdout_start` **en el
      documento de hipótesis**, con fecha y motivo, antes de correr.

## 5. Paper trading 2–3 meses

- [ ] Tras la confirmación, **paper (o capital mínimo) 2–3 meses**. Su objetivo
      es cazar errores de implementación (fills, costos, calendario, datos), no
      ganar significancia: con SR 1 harían falta 9 años para t = 3.
- [ ] Espera ~0,8× el Sharpe del backtest. Mata la estrategia si el drawdown en
      vivo es inconsistente con el SR asumido (p. ej., DD > 2× el peor DD OOS).
- [ ] Compara la curva viva contra la OOS (`ops/status`) y los costos reales
      contra el modelo (ledger de slippage): esa es la calibración que vale.

## 6. Prohibido retocar con resultados en vivo

- [ ] Los parámetros que entran a paper quedan **congelados** en el commit que
      los despliega. Ninguna corrección se hace mirando el PnL vivo (AHM 2019).
- [ ] Si el vivo obliga a cambiar algo, es **una hipótesis nueva**: documento
      nuevo, `exp_id` nuevo, presupuesto nuevo, hold-out nuevo, y vuelve al §0.
- [ ] Un bug de implementación se arregla; una "mejora" inspirada en el vivo se
      investiga desde cero.

## 7. Qué significa cada bandera del registry (`experiments_<exp_id>.jsonl`)

| Campo | Significado | Valor en filas viejas |
|---|---|---|
| `n_trials` | Configuraciones evaluadas en la corrida que produjo la fila (N para DSR/PBO y presupuesto). | `0` |
| `years_available` | Años de datos usados, sin el hold-out. | `0.0` |
| `years_needed` | `2·ln(N)/SR²` para esa corrida. | `0.0` |
| `budget_ok` | `True`/`False` según §2; `None` = la corrida no evaluó presupuesto. | `None` |
| `holdout_start` | Hold-out declarado (ISO) o `None` si no había. | `None` |
| `holdout_applied` | La fila se calculó **sin** ver el hold-out. | `False` |
| `holdout_opened` | Corrida de confirmación: la fila **sí** usó el hold-out (hay línea en el JSONL). | `False` |
| `extra.holdout_overused` | Esa apertura excedió `max_holdout_openings`; la fila no vale como confirmación. | ausente |
| `extra.holdout_opening_no` | Número de apertura con el que se calculó la fila. | ausente |
| `gate_passed` / `gate_reasons` | Veredicto estricto y por qué falló (incluye `trial_budget_exceeded`, `holdout_overused`). | igual que hoy |
| `dataset_hash` / `config_hash` | Procedencia obligatoria: datos y configuración exactos. | obligatorios desde fase 0 |

Lectura rápida: una fila **solo es evidencia de confirmación** si
`holdout_opened=True`, `extra.holdout_overused` ausente, `budget_ok=True` y
`gate_passed=True`. Una fila con `holdout_applied=True` es investigación
(selección); una con `holdout_start=None` ni siquiera declaró partición.

## 8. Golden files (CI de regresión, anexo 5 §4)

- [ ] `tests/golden/<estrategia>.json` congela, por estrategia (`sma_crossover`,
      `tsmom`, `rotation`, `mean_reversion`), las estadísticas y el SHA-256 de la
      lista de órdenes sobre `tests/fixtures` con la configuración por defecto.
      `tests/test_golden.py` falla ante **cualquier** deriva (hashes y enteros
      exactos, flotantes a `rel=1e-9`) y dice qué métrica se movió.
- [ ] Se regeneran **solo a propósito**, tras un cambio intencional de motor,
      costos o estrategia, y en un commit explícito que lo diga:
      `ibtrader golden-regen --yes` (sin `--yes` no escribe nada).
- [ ] Nunca se regeneran desde CI ni "para que pase". Si cambió un número y no
      sabes por qué, eso es el hallazgo.

---

## Comandos de referencia

```bash
# Investigación normal (hold-out oculto, presupuesto evaluado)
RESEARCH__HOLDOUT_START=2024-10-01 ibtrader research-run --exp-id h1-tsmom-2026-10

# Única confirmación (queda registrada en reports/research/holdout_openings.jsonl)
RESEARCH__HOLDOUT_START=2024-10-01 ibtrader research-run --exp-id h1-tsmom-2026-10-confirm --confirmation

# Golden files, solo tras un cambio intencional
ibtrader golden-regen --yes
```

Variables: `RESEARCH__HOLDOUT_START` (ISO), `RESEARCH__MAX_HOLDOUT_OPENINGS` (1),
`RESEARCH__TRIAL_BUDGET_TARGET_SHARPE` (1,0), `RESEARCH__FAIL_ON_BUDGET_EXCEEDED`
(true). `RESEARCH__CONFIRMATION_MODE` existe en la configuración pero el CLI exige
el flag `--confirmation` escrito.
