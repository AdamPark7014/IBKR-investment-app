<!-- Committed from owner's authoritative upload -->
# V2 — RONDA DE CORRECCIÓN FINAL ANTES DE REVISIÓN FORMAL

## CONTEXTO ACTUAL

La última verificación con datos reales en la PC produjo:

| Modo             |  CAGR | Sharpe | Max Drawdown |
| ---------------- | ----: | -----: | -----------: |
| Solo compras     |  4.8% |   0.72 |        -4.5% |
| Compras + cortos |  2.7% |   0.35 |        -9.4% |
| Buy & Hold SPY   | 16.5% |   1.01 |       -19.0% |

Estos resultados NO deben optimizarse ni modificarse deliberadamente durante esta ronda.

El objetivo de esta ronda es exclusivamente corregir errores de implementación, riesgo, validación, trazabilidad y reporting.

Actualmente quedan tres problemas importantes:

1. El stop-loss puede cerrar posiciones antes de alcanzar el umbral configurado.
2. El filtro de régimen permanece desactivado durante el periodo inicial de warm-up y eso interactúa incorrectamente con el límite de pérdida, llegando a bloquear la estrategia durante años.
3. Las operaciones y el walk-forward no registran correctamente la razón de cada salida y el reporte contiene métricas en cero, incluyendo comisiones y número de operaciones.

Además, en rondas anteriores el agente ha declarado correcciones que posteriormente no estaban implementadas o no estaban cubiertas por pruebas.

Por eso, en esta ronda:

> **NINGUNA CORRECCIÓN SE CONSIDERA REALIZADA HASTA QUE EXISTA UNA PRUEBA AUTOMÁTICA QUE DEMUESTRE SU COMPORTAMIENTO.**

---

# REGLA CERO — NO MODIFICAR LA ESTRATEGIA

NO modificar:

* parámetros para mejorar rendimiento;
* señales;
* thresholds de alpha;
* indicadores;
* filtros;
* selección de parámetros;
* combinación de parámetros;
* ventanas históricas con intención de mejorar resultados;
* lógica de entrada salvo cuando sea estrictamente necesario para corregir un bug documentado;
* metodología para obtener un CAGR/Sharpe mejor.

NO agregar alpha. NO agregar nuevos indicadores. NO optimizar. NO buscar una configuración que haga que el sistema supere SPY.

Esta ronda es de **correctness**, no de performance.

Si después de todas las correcciones el sistema sigue obteniendo 4.8% CAGR, ese resultado debe permanecer.

---

# 1. STOP-LOSS — CORRECCIÓN DEFINITIVA

Existe actualmente este comportamiento:

```text
Stop Loss = 2%
posición cerrada = -0.8%
```

Esto es incorrecto salvo que exista una causa explícita de ejecución que justifique la salida.

Primero determina exactamente qué significa el parámetro de stop-loss en el sistema (`STOP_LOSS = 2%`). Debe existir una definición inequívoca. Por ejemplo, para una posición long:

```text
stop_price = entry_price * (1 - stop_loss)
```

Para short:

```text
stop_price = entry_price * (1 + stop_loss)
```

Pero utiliza la convención real del proyecto y documenta matemáticamente la definición.

---

# 2. DISTINGUIR STOP-LOSS DE OTRAS SALIDAS

Una posición puede cerrarse por:

```text
SIGNAL_EXIT
STOP_LOSS
RISK_LIMIT
EMERGENCY_EXIT
REGIME_EXIT
MANUAL_EXIT
END_OF_BACKTEST
REBALANCE
```

No debe aparecer `STOP_LOSS` simplemente porque una posición perdió dinero. La razón de salida debe corresponder al evento real que produjo la orden.

---

# 3. TESTS DEL STOP-LOSS

Crea pruebas deterministas.

## LONG

Entrada: `entry = 100`, `stop = 2%`.

Mientras el precio sea 99, 98.5, 98.1: NO debe ejecutarse el stop si la metodología usa cierre diario y el umbral todavía no se ha alcanzado según la convención definida.

Cuando se alcanza el nivel correspondiente (98) debe generarse `exit_reason = STOP_LOSS`.

## SHORT

Entrada: `entry = 100`, `stop = 2%`. Prueba simétrica.

---

# 4. TEST DE NO-FALSE-POSITIVE

Crea explícitamente una prueba para el bug encontrado:

```text
configured stop = 2%
actual loss = -0.8%
```

Resultado obligatorio: `STOP_LOSS = false`.

Si la posición se cierra por otra razón, debe aparecer esa razón. Nunca etiquetar el cierre como stop-loss.

---

# 5. EJECUCIÓN REALISTA DEL STOP

Determina cómo se ejecuta un stop: intradía; al cierre; siguiente apertura; precio del stop; precio de apertura si existe gap.

No mezcles una metodología con otra. Si el motor trabaja con OHLC diario, documenta exactamente qué información utiliza. Ejemplo:

```text
signal at t
→ stop condition determined from available OHLC
→ execution at next realistically available price
```

Si existe gap por debajo del stop (`stop = 98`, `next open = 95`), no asumas automáticamente fill a 98 si el modelo no lo justifica. Documenta y prueba el comportamiento.

---

# 6. REGIME WARM-UP

Actualmente el filtro de régimen permanece desactivado hasta tener suficiente historia. Esto puede ser válido. Lo incorrecto es que `regime unavailable` se convierta implícitamente en una decisión de riesgo no documentada.

Define explícitamente `REGIME_WARMUP` durante el periodo donde no existe suficiente información. Documenta qué puede y qué no puede hacer la estrategia durante warm-up. Por ejemplo, `REGIME_UNKNOWN` debe ser distinto de `REGIME_BULL`, `REGIME_BEAR`, `REGIME_NEUTRAL`.

---

# 7. RÉGIMEN Y RISK LIMIT DEBEN SER INDEPENDIENTES

No permitir que `regime unavailable` active accidentalmente `loss limit` o viceversa.

Audita exactamente la cadena `REGIME → SIGNAL → RISK → ORDER` y determina qué componente está tomando cada decisión.

Un estado desconocido no debe transformarse silenciosamente en `SELL` ni `BLOCK EVERYTHING` sin una regla explícita.

---

# 8. EVITAR EL BLOQUEO DE AÑOS

El caso encontrado fue: `loss limit triggered → strategy locked → remains blocked for years`.

Reproduce este escenario con una prueba. Determina:

1. qué activó el bloqueo;
2. cuándo;
3. qué condición debía liberarlo;
4. por qué no se liberó;
5. qué estado interno permaneció activo.

El sistema debe tener una política explícita para `RISK_LOCK` y para `RISK_UNLOCK`.

No inventes una política nueva para mejorar resultados. Implementa la política que corresponda a la especificación existente y documenta cualquier ambigüedad.

---

# 9. RISK LOCK STATE MACHINE

Documenta formalmente:

```text
NORMAL
↓
RISK_TRIGGERED
↓
RESTRICTED
↓
RECOVERY / RESET
↓
NORMAL
```

Los nombres pueden adaptarse al código. Pero debe ser imposible tener un estado donde `new entries = blocked` y `exits = blocked`. Una posición existente siempre debe poder reducirse o cerrarse.

---

# 10. EXIT REASON — OBLIGATORIO

Cada operación de salida debe guardar una razón (p. ej. `{"exit_reason": "STOP_LOSS"}` o equivalente según la arquitectura).

Valores válidos deben estar centralizados. NO permitir strings arbitrarios repartidos por el código. Crea un enum/type/schema.

---

# 11. TRADE RECORD COMPLETO

Cada operación debe poder reconstruirse. Como mínimo:

```text
trade_id
symbol
side
entry_timestamp
entry_price
exit_timestamp
exit_price
quantity
gross_pnl
net_pnl
commission
slippage
return_pct
holding_period
entry_reason
exit_reason
strategy_version
```

Si un campo no aplica, utilizar `null` y NO `0` si cero significa algo diferente.

---

# 12. WALK-FORWARD REPORT

El reporte actual muestra métricas en cero. Esto no es aceptable si el motor realmente ejecutó operaciones.

Determina si el problema está en: aggregation, serialization, metric calculation, period reset, trade collection, report generation.

No simplemente cambies el reporte para mostrar números. Primero encuentra la causa.

---

# 13. MÉTRICAS POR VENTANA

Cada periodo walk-forward debe tener su propio: initial_equity, final_equity, return, CAGR, Sharpe, Sortino, max_drawdown, trade_count, win_rate, turnover, commissions, slippage.

Los resultados de una ventana NO deben contaminar otra.

---

# 14. TEST DE AISLAMIENTO ENTRE PERIODOS

Ejecuta Period A y después Period B por separado. Luego ejecuta A + B en una corrida compuesta. Comprueba que:

* el resultado de A individual = resultado de A dentro de la corrida correspondiente;
* el resultado de B individual = resultado de B dentro de la corrida correspondiente;
* el número de operaciones de A no aparece en B;
* las comisiones de A no aparecen en B;
* el cooldown de A no contamina B;
* el risk state de A no contamina B;
* el emergency switch de A no contamina B.

---

# 15. RESET COMPLETO DEL ESTADO

Audita todos los estados persistentes. Especialmente: cooldown, risk_lock, emergency_switch, portfolio, cash, positions, trade_history, equity_peak, daily_loss, cumulative_loss, regime_state.

Cada backtest debe comenzar con un estado limpio salvo que explícitamente se solicite continuidad. Crea una función de inicialización/reset inequívoca.

---

# 16. EMERGENCY SWITCH

La corrección anterior indicó que el emergency switch ya no permite aumentar posiciones. No aceptes esta afirmación únicamente. Crea pruebas para:

* **Emergency OFF:** entry = allowed; increase = allowed; reduce = allowed; exit = allowed.
* **Emergency ON:** entry = blocked; increase = blocked; reduce = allowed; exit = allowed.
* **Emergency ON DURING POSITION:** existing position > 0 → emergency ON → close = allowed.
* **Emergency ON → OFF:** comprueba que el estado se reinicie correctamente.

---

# 17. ORDER LIMIT

El kill switch y el límite de órdenes anteriormente podían bloquear una salida. Reproduce explícitamente: `max_orders reached`, `existing position`, `exit order`. Resultado: `exit = ALLOWED`.

El límite de nuevas órdenes nunca debe impedir una liquidación necesaria.

---

# 18. SHORT REVERSAL

Anteriormente `LONG → SHORT` podía clasificarse erróneamente como una reducción. Esto es crítico. Define claramente:

```text
LONG → FLAT
FLAT → SHORT
LONG → SHORT
SHORT → FLAT
SHORT → LONG
```

Una reversión `LONG → SHORT` debe considerarse `close long + open short`, y la segunda parte debe pasar por las reglas de entrada. Después de un risk lock, `LONG → SHORT` NO puede saltarse el bloqueo de nuevas entradas.

Crea tests para las cinco transiciones.

---

# 19. DATA INTEGRITY

Repite la auditoría: real data, test data, synthetic data, fixtures. Verifica hashes antes/después.

Ningún test puede: borrar el emergency switch real; modificar el dataset real; escribir sobre configuración de producción; alterar archivos fuera de su sandbox.

---

# 20. NO CAMBIAR PARÁMETROS

Busca explícitamente en el diff cualquier modificación de: strategy parameters, optimization ranges, parameter combinations, selection criteria.

Si encuentras una modificación cuya única finalidad sea hacer pasar una prueba: REVERT y reportarla.

Una prueba debe adaptarse al comportamiento especificado. La estrategia no debe adaptarse para que una prueba pase.

---

# 21. VERIFICACIÓN DE TODAS LAS AFIRMACIONES

Para cada afirmación que vayas a realizar en el reporte ("corregido", "implementado", "validado", "PASS") debe existir evidencia concreta: `Claim → Implementation → Test → Test result`.

Ejemplo:

```text
Claim: Emergency switch blocks increases.
Implementation: RiskEngine.validate_order()
Test: test_emergency_blocks_position_increase
Result: PASS
```

Si no existe prueba: `UNVERIFIED`, no `PASS`.

---

# 22. TEST MATRIX FINAL

| Área              | Test                       | Resultado |
| ----------------- | -------------------------- | --------- |
| Stop-loss long    | threshold correcto         | PASS/FAIL |
| Stop-loss short   | threshold correcto         | PASS/FAIL |
| False stop        | -0.8% con stop 2%          | PASS/FAIL |
| Risk lock         | nuevas entradas bloqueadas | PASS/FAIL |
| Risk lock         | salidas permitidas         | PASS/FAIL |
| Emergency         | nuevas entradas bloqueadas | PASS/FAIL |
| Emergency         | salidas permitidas         | PASS/FAIL |
| Order limit       | salida permitida           | PASS/FAIL |
| Long→Short        | entrada short protegida    | PASS/FAIL |
| Regime warmup     | estado explícito           | PASS/FAIL |
| Regime look-ahead | test temporal              | PASS/FAIL |
| Walk-forward      | múltiples ventanas         | PASS/FAIL |
| Period isolation  | sin contaminación          | PASS/FAIL |
| Commissions       | registradas                | PASS/FAIL |
| Trade count       | correcto                   | PASS/FAIL |
| Exit reason       | registrado                 | PASS/FAIL |
| Data integrity    | hashes intactos            | PASS/FAIL |
| Reproducibilidad  | dos ejecuciones iguales    | PASS/FAIL |
| Clean install     | instalación limpia         | PASS/FAIL |

---

# 23. END-TO-END TEST OBLIGATORIO

Ejecuta una prueba completa:

```text
DATA → VALIDATION → FEATURES → REGIME → SIGNAL → RISK → ORDER → EXECUTION → PORTFOLIO → TRADE LOG → METRICS → WALK-FORWARD → REPORT
```

El resultado debe contener operaciones reales del fixture y `trade_count > 0`, `commission > 0` cuando corresponda.

No aceptar un reporte con `trade_count = 0`, `commission = 0` si el motor claramente ejecutó operaciones.

---

# 24. REGRESIÓN

Todos los bugs encontrados anteriormente deben tener un regression test. Como mínimo BUG-001, BUG-002, BUG-003, ...

No eliminar un test porque ya no sea necesario. Cada bug corregido debe quedar protegido contra regresión.

---

# 25. RESULTADOS FINANCIEROS

Después de corregir exclusivamente bugs, ejecuta nuevamente la misma configuración que produjo Solo compras = 4.8%, Compras + cortos = 2.7%, Buy & Hold = 16.5%.

No cambies parámetros. Compara ANTES vs DESPUÉS. Si cambian las métricas, explica exactamente qué bug produjo el cambio. No presentes el cambio como una mejora. Puede subir. Puede bajar. Ambos resultados son aceptables si el motor ahora es correcto.

---

# 26. CRITERIO DE APROBACIÓN

NO declarar aprobado si:

* algún test crítico falla;
* existe stop-loss falso;
* existe look-ahead;
* una salida puede quedar bloqueada;
* existe contaminación entre periodos;
* emergency switch puede abrir posiciones;
* LONG→SHORT puede saltarse risk limits;
* métricas del reporte no coinciden con el motor;
* las comisiones son incorrectas;
* trade_count es incorrecto;
* existen claims sin test;
* se modificaron parámetros de estrategia;
* los datos reales fueron alterados.

---

# 27. FORMATO OBLIGATORIO DE ENTREGA

Entrega exactamente estas secciones:

* **A. STATUS** — `APPROVED` o `NOT APPROVED`. No utilices frases ambiguas.
* **B. BUGS CORREGIDOS** — para cada uno: Bug ID, Descripción, Root cause, Archivo, Función, Fix, Regression test, Resultado.
* **C. STOP-LOSS** — long formula, short formula, execution model, gap behavior, exit reason, tests.
* **D. RISK ENGINE** — entry, increase, reduce, close, emergency exit, reversal, risk lock, unlock.
* **E. REGIME** — warmup, states, transition, data available at t, look-ahead protection, tests.
* **F. WALK-FORWARD** — mostrar TODAS las ventanas, no únicamente el agregado.
* **G. TRADE AUDIT** — ejemplos reales de entry_reason, exit_reason, commission, slippage, PnL.
* **H. METRICS AUDIT** — comparar engine, report, manual verification.
* **I. TEST MATRIX** — mostrar todos los tests relevantes.
* **J. DATA INTEGRITY** — dataset hash before, dataset hash after, test directories.
* **K. REPRODUCIBILITY** — ejecutar dos veces: RUN 1, RUN 2, DIFF.
* **L. STRATEGY PARAMETER AUDIT** — mostrar que los parámetros de estrategia NO fueron modificados durante esta ronda.
* **M. FINANCIAL RESULTS** — únicamente después de que todos los tests anteriores estén correctos. Comparar previous official run, current official run, buy & hold, sin optimización.

---

# 28. REGLA DE HONESTIDAD DEL AGENTE

Es obligatorio distinguir entre IMPLEMENTED, TESTED, VERIFIED. No son sinónimos.

* Una función implementada pero no probada: `IMPLEMENTED / UNVERIFIED`.
* Una prueba que existe pero falla: `IMPLEMENTED / TEST FAIL`.
* Una corrección cubierta por una prueba que pasa: `VERIFIED`.

Solo aquello que esté realmente demostrado puede marcarse como `PASS`.

---

# 29. CONDICIÓN DE PARADA

Cuando termines: **DETENTE.**

No avances a una nueva fase. No agregues alpha. No optimices. No cambies parámetros para mejorar resultados. No hagas ingeniería de rendimiento. No intentes superar SPY. No ejecutes cambios adicionales después de generar el reporte.

Entrega el reporte completo y espera revisión.

El objetivo de esta ronda no es demostrar que el algoritmo gana dinero. El objetivo es demostrar que cuando el algoritmo diga "gané" o "perdí", podemos confiar en que el número corresponde exactamente a lo que realmente ocurrió en la simulación.
