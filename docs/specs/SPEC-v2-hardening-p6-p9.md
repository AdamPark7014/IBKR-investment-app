# V2 — HARDENING Y VALIDACIÓN DEFINITIVA DE FASES 6–9

## CONTEXTO

Estamos desarrollando el motor cuantitativo V2.

Las fases 1–5 ya fueron corregidas y verificadas con datos reales. La ejecución ahora utiliza entrada en la apertura del día siguiente, evita look-ahead evidente y conserva la línea base histórica original.

Las fases 6–9 ya fueron implementadas, pero **todavía NO están aprobadas**.

La última validación fuera de muestra confiable produjo:

| Versión          |  CAGR | Sharpe | Máx. Drawdown |
| ---------------- | ----: | -----: | ------------: |
| Solo compras     |  5.9% |   0.74 |        -10.7% |
| Compras + cortos |  7.7% |   0.93 |         -9.1% |
| Buy & Hold SPY   | 16.2% |   0.99 |        -19.0% |

La estrategia solo superó a SPY en uno de los tres periodos evaluados y quedó por debajo en los otros dos.

Esto es un resultado válido y NO debe maquillarse.

El objetivo de esta iteración no es fabricar mejores métricas.

El objetivo es conseguir un motor **correcto, reproducible, auditable y estadísticamente honesto**.

---

# OBJETIVO PRINCIPAL

Antes de continuar con nuevas capacidades de alpha, optimización o sofisticación de la estrategia:

1. corregir completamente el control de riesgo;
2. garantizar que las salidas nunca puedan quedar bloqueadas por el límite de pérdida;
3. corregir cualquier inconsistencia entre motor, reportes y documentación;
4. garantizar que las fases 6–9 realmente hagan lo que dicen hacer;
5. crear pruebas automáticas de extremo a extremo;
6. demostrar que no existe look-ahead bias;
7. demostrar que los datos de prueba jamás contaminan datos reales;
8. demostrar que los resultados publicados corresponden exactamente a la ejecución que los generó;
9. conservar la línea base original y las versiones corregidas por separado;
10. NO avanzar a nuevas fases de alpha hasta que todo esto esté aprobado.

---

# REGLA CRÍTICA DE RIESGO

Actualmente existe un error grave:

Después de alcanzar aproximadamente un -5% de pérdida acumulada, el sistema entra en estado de bloqueo y posteriormente puede impedir incluso las órdenes de salida.

Esto es incorrecto.

## PRINCIPIO INNEGOCIABLE

Una regla de riesgo que impida abrir nuevas posiciones **NUNCA puede impedir cerrar o reducir una posición existente**.

Debe existir una jerarquía explícita:

### PRIORIDAD 1 — EMERGENCY EXIT

Puede cerrar una posición aunque:

* se haya alcanzado el daily loss limit;
* se haya alcanzado el total loss limit;
* el sistema esté en cooldown;
* el régimen sea desfavorable;
* el tamaño permitido sea 0;
* el límite de nuevas entradas esté bloqueado;
* cualquier otra regla preventiva esté activada.

### PRIORIDAD 2 — POSITION REDUCTION

Debe permitir reducir exposición.

### PRIORIDAD 3 — RISK BLOCK

Puede impedir:

* nuevas compras;
* nuevos cortos;
* aumento de posiciones;
* nuevas órdenes de riesgo.

Pero NO puede impedir:

* cerrar;
* reducir;
* liquidar;
* ejecutar stop-loss;
* ejecutar emergency exit.

Implementa esta jerarquía explícitamente en arquitectura y código.

No lo soluciones con un `if` aislado.

---

# 1. AUDITAR EL CONTROL DE RIESGO COMPLETO

Revisa todas las rutas relacionadas con:

* position sizing;
* max position size;
* max portfolio exposure;
* daily loss limit;
* cumulative loss limit;
* drawdown limit;
* stop loss;
* take profit;
* emergency exit;
* cooldown;
* kill switch;
* order validation;
* order rejection;
* signal generation;
* execution;
* portfolio state.

Determina exactamente:

```text
SIGNAL
  ↓
RISK ENGINE
  ↓
ORDER INTENT
  ↓
ORDER VALIDATION
  ↓
EXECUTION
  ↓
PORTFOLIO UPDATE
```

Documenta dónde puede ser rechazada una orden y por qué.

No asumas que está correcto porque una función tenga el nombre correcto.

---

# 2. CREAR UNA MÁQUINA DE ESTADOS EXPLÍCITA

El sistema debe tener estados inequívocos.

Por ejemplo:

```text
NORMAL
RISK_RESTRICTED
COOLDOWN
EMERGENCY
FLAT
```

No copies estos nombres ciegamente; adapta la arquitectura existente.

Define formalmente qué operaciones están permitidas en cada estado.

Ejemplo conceptual:

| Estado          | Abrir | Aumentar | Reducir | Cerrar |
| --------------- | ----: | -------: | ------: | -----: |
| NORMAL          |    Sí |       Sí |      Sí |     Sí |
| RISK_RESTRICTED |    No |       No |      Sí |     Sí |
| COOLDOWN        |    No |       No |      Sí |     Sí |
| EMERGENCY       |    No |       No |      Sí |     Sí |
| FLAT            |   No* |      No* |      No |     No |

El comportamiento real debe quedar cubierto por tests.

---

# 3. TEST CRÍTICO DE SALIDA

Crea obligatoriamente una prueba que reproduzca exactamente el bug actual.

Escenario:

```text
capital inicial = 100,000
posición abierta
pérdida acumulada >= 5%
risk lock = ACTIVE
```

Después intentar:

```text
CLOSE POSITION
```

Resultado esperado:

```text
ORDER ACCEPTED
POSITION -> 0
```

Nunca:

```text
ORDER REJECTED
```

Agrega también:

```text
PARTIAL EXIT
STOP LOSS
EMERGENCY EXIT
```

Todos deben poder ejecutarse durante `RISK_RESTRICTED`.

---

# 4. TEST DEL LÍMITE DE RIESGO

Prueba por separado:

### Caso A

Pérdida < límite:

```text
new entry = allowed
```

### Caso B

Pérdida >= límite:

```text
new entry = rejected
```

### Caso C

Pérdida >= límite + posición existente:

```text
new entry = rejected
close = allowed
reduce = allowed
stop loss = allowed
```

### Caso D

Después de cerrar:

```text
position = 0
```

Y el sistema debe permanecer consistente.

---

# 5. DIFERENCIAR LOSS LIMITS

Audita que no se estén mezclando:

* pérdida diaria;
* pérdida acumulada;
* drawdown desde peak equity;
* pérdida por posición;
* pérdida realizada;
* pérdida no realizada.

Cada métrica debe tener:

1. definición matemática;
2. fuente;
3. frecuencia de actualización;
4. comportamiento esperado;
5. test automatizado.

No permitas variables ambiguas como:

```text
loss_limit
risk_limit
max_loss
```

si no está claro exactamente qué representan.

---

# 6. AUDITORÍA DE FASE 7

La fase 7 afirma ser validación cruzada.

Comprueba si realmente existe:

```text
train
validation
test
```

y si existe separación temporal correcta.

No aceptes llamar "cross-validation" a una simple división de datos.

Para series temporales utiliza un esquema apropiado, por ejemplo:

```text
Train → Validation → Test
Train → Validation → Test
Train → Validation → Test
...
```

sin permitir que datos futuros entren en decisiones pasadas.

Documenta exactamente:

* número de folds;
* fechas;
* datos utilizados;
* parámetros seleccionados;
* parámetros evaluados;
* costos;
* slippage;
* ejecución;
* métricas.

---

# 7. AUDITORÍA DE FASE 8 — RIESGO

La fase 8 debe dejar de ser únicamente una fotografía del último día.

Debe demostrar comportamiento histórico.

Si actualmente existe una función que solamente responde:

```text
BUY / SELL / HOLD
```

para el último día, eso NO constituye validación histórica del sistema de riesgo.

Crea tests históricos donde se produzcan:

* volatilidad alta;
* drawdown;
* crash;
* tendencia alcista;
* tendencia bajista;
* mercado lateral;
* gaps;
* pérdida consecutiva;
* recuperación.

Comprueba que el risk engine responde correctamente.

---

# 8. AUDITORÍA DE FASE 9 — WALK-FORWARD

La fase 9 debe ser realmente walk-forward.

NO utilizar:

```text
train = 2021–2025
test = 2025–2026
```

como única prueba y llamarlo validación walk-forward.

Implementa múltiples ventanas temporales.

Ejemplo conceptual:

```text
Window 1
Train → Test

Window 2
Train → Test

Window 3
Train → Test

Window 4
Train → Test
```

Cada ventana debe:

1. entrenar/seleccionar parámetros únicamente con información disponible hasta ese momento;
2. congelar los parámetros;
3. ejecutar el periodo futuro;
4. registrar operaciones;
5. incluir comisiones;
6. incluir slippage cuando corresponda;
7. no reutilizar información futura.

---

# 9. PROHIBICIÓN ABSOLUTA DE LOOK-AHEAD

Audita todo el pipeline.

Busca especialmente:

* rolling calculations;
* normalization;
* standardization;
* feature engineering;
* regime detection;
* parameter optimization;
* thresholds;
* labels;
* signal generation;
* portfolio sizing.

Todo indicador utilizado para decidir una operación en `t` debe depender únicamente de información disponible antes de la ejecución de esa operación.

La ejecución debe respetar:

```text
signal at t
→ order at next available execution point
```

Nunca:

```text
signal using close[t]
→ execute using close[t]
```

si ese cierre todavía no estaba disponible al momento de la decisión.

Crea un test específicamente diseñado para detectar look-ahead.

---

# 10. RÉGIMEN DE MERCADO

Audita la detección de régimen.

Debe cumplirse:

```text
regime(t) = f(data <= t)
```

Nunca:

```text
regime(t) = f(data future)
```

Además:

* elimina etiquetas dependientes de semillas aleatorias;
* si existe ML/clustering, controla reproducibilidad;
* documenta cómo se determinan los estados;
* evita utilizar el rendimiento futuro para definir qué régimen era "bueno";
* separa identificación del régimen y evaluación posterior.

Crea un test que falle si se introduce deliberadamente información futura.

---

# 11. COSTOS DE TRANSACCIÓN

Audita:

* comisiones;
* spread;
* slippage;
* turnover;
* número de órdenes;
* tamaño de orden.

Verifica que los costos se apliquen:

```text
entrada
salida
reducción
rebalanceo
```

y no únicamente en algunas rutas.

Crea una prueba donde una estrategia con turnover artificialmente alto tenga costos claramente superiores.

---

# 12. EVITAR REBALANCEO DIARIO INNECESARIO

La versión anterior llegó a:

```text
38 operaciones → 577 operaciones
```

por reajustes diarios.

Determina por qué ocurrió.

El sistema debe distinguir entre:

```text
TARGET POSITION
CURRENT POSITION
DELTA
```

y únicamente generar una orden cuando:

```text
abs(target - current) > tolerance
```

La tolerancia debe ser configurable.

Prueba:

```text
target = 100
current = 100
→ 0 orders
```

```text
target = 100
current = 99
→ depende de tolerance
```

```text
target = 100
current = 50
→ reduction/increase required
```

---

# 13. CONFIGURACIÓN

Ninguna variable documentada puede ignorarse silenciosamente.

Cada parámetro debe tener:

```text
default
type
validation
range
effect
test
```

Si el usuario proporciona un valor inválido:

```text
FAIL FAST
```

No utilizar silenciosamente el valor default.

Crea tests para:

* parámetro válido;
* parámetro inválido;
* parámetro ausente;
* tipo incorrecto;
* rango inválido.

---

# 14. DATOS

Mantén separación absoluta entre:

```text
REAL DATA
TEST DATA
SYNTHETIC DATA
FIXTURES
```

Los tests nunca deben sobrescribir:

* SPY real;
* datasets descargados;
* cache de producción;
* archivos del usuario.

Cada test debe utilizar un directorio aislado.

Agrega una prueba que verifique que después de ejecutar toda la suite:

```text
hash(real_dataset_before)
==
hash(real_dataset_after)
```

cuando el test no tenga explícitamente autorización para modificarlo.

---

# 15. INTEGRIDAD DE RESULTADOS

Cada backtest debe generar un artefacto reproducible con:

```text
dataset identifier
dataset hash
date range
strategy version
git commit
configuration hash
parameters
commission model
slippage model
execution model
random seed
number of trades
equity curve
CAGR
Sharpe
Sortino
max drawdown
turnover
fees
```

El reporte debe poder rastrearse exactamente hasta la ejecución que lo generó.

No publiques números manualmente copiados.

Idealmente:

```text
BACKTEST RUN
    ↓
RESULT OBJECT
    ↓
VALIDATION
    ↓
REPORT GENERATION
```

---

# 16. PROHIBIR RESULTADOS IMPOSIBLES SIN ALERTA

El sistema NO debe asumir que un resultado extraordinario es correcto.

No establezcas un límite arbitrario que simplemente descarte buenos resultados.

En lugar de eso, agrega diagnostics:

```text
SUSPICIOUS PERFORMANCE
```

cuando existan condiciones como:

* CAGR extremo;
* número de operaciones inesperadamente bajo;
* ausencia de costos;
* fechas futuras;
* ejecución al mismo precio de la señal;
* equity discontinuity;
* retornos imposibles;
* dataset sintético;
* turnover anómalo.

La alerta debe explicar exactamente qué condición la activó.

---

# 17. REPRODUCIBILIDAD

Ejecuta el mismo backtest dos veces.

Debe producir resultados equivalentes.

Si existe aleatoriedad:

```text
seed
```

debe quedar registrada.

La segunda ejecución debe demostrar:

```text
same config
same dataset
same code
same seed
→ same result
```

---

# 18. PRUEBAS END-TO-END

No quiero únicamente unit tests.

Crea al menos una prueba que ejecute:

```text
download/load data
→ validate data
→ generate features
→ generate signal
→ risk engine
→ order generation
→ execution simulation
→ portfolio update
→ metrics
→ report
```

La prueba debe utilizar datos de prueba aislados.

Debe ejecutarse desde una instalación limpia.

---

# 19. PRUEBA DE INSTALACIÓN LIMPIA

Crear un entorno limpio.

Instalar dependencias desde cero.

Ejecutar los comandos oficiales del proyecto.

No modificar manualmente el entorno para hacer funcionar el sistema.

Si una dependencia rompe la aplicación:

1. identificar versión;
2. fijar versión compatible;
3. actualizar lockfile/requirements;
4. probar instalación desde cero;
5. documentar.

---

# 20. DOCUMENTACIÓN

Corrige cualquier documento que actualmente publique resultados antiguos como si fueran resultados nuevos.

Cada tabla debe especificar:

```text
Original baseline
Corrected baseline
Out-of-sample
Walk-forward
Diagnostic
```

Nunca mezclar resultados de diferentes motores.

Si un número fue obtenido manualmente fuera del motor oficial:

```text
MANUAL DIAGNOSTIC — NOT OFFICIAL
```

---

# 21. CRITERIOS DE APROBACIÓN

NO consideres las fases 6–9 aprobadas simplemente porque:

```text
tests = green
```

Deben cumplirse simultáneamente:

### A. Correctitud
El motor hace lo que especifica.

### B. Reproducibilidad
La misma entrada produce el mismo resultado.

### C. Integridad de datos
No existe contaminación entre datos reales y fixtures.

### D. Ejecución realista
No existe ejecución al precio de la señal cuando ese precio aún no estaba disponible.

### E. Riesgo
Los límites bloquean nuevas entradas pero nunca bloquean salidas.

### F. Validación temporal
No existe look-ahead.

### G. Walk-forward
Existen múltiples ventanas fuera de muestra.

### H. Costos
Las métricas incluyen costos de forma consistente.

### I. Trazabilidad
Cada resultado puede rastrearse a:

```text
commit + config + dataset + seed
```

### J. Documentación
Los documentos representan exactamente los resultados actuales.

---

# 22. FORMATO OBLIGATORIO DE ENTREGA

Cuando termines, NO digas simplemente:

> "Fases 6–9 completadas."

Entrega un reporte estructurado:

## 1. RESUMEN
```text
PASS / FAIL
```
para cada fase.

## 2. BUGS ENCONTRADOS
Para cada bug:
```text
Bug:
Root cause:
File:
Function:
Fix:
Regression test:
Status:
```

## 3. RISK ENGINE
Explica exactamente cómo funciona ahora:
```text
entry
increase
reduce
close
emergency exit
```
durante cada estado de riesgo.

## 4. TESTS
| Test | Qué verifica | Resultado |
| ---- | ------------ | --------- |
| ...  | ...          | PASS/FAIL |

## 5. BACKTEST
Reporta únicamente resultados generados por el motor oficial.
Incluye:
```text
period
CAGR
Sharpe
Sortino
Max Drawdown
Trades
Turnover
Fees
```

## 6. WALK-FORWARD
Mostrar TODAS las ventanas:
```text
Window
Train period
Test period
Parameters
CAGR
Sharpe
Max DD
Trades
Fees
```

## 7. DATA INTEGRITY
Mostrar:
```text
dataset hash
before
after
```
y confirmar que los tests no modificaron datos reales.

## 8. REPRODUCIBILITY
Ejecutar dos veces y comparar resultados.

## 9. INSTALLATION TEST
Demostrar instalación desde cero.

## 10. DOCUMENTATION AUDIT
Enumerar qué documentos fueron actualizados y qué números contienen.

---

# 23. REGLA FINAL

No optimices la estrategia para mejorar:

```text
CAGR
Sharpe
win rate
```

durante esta iteración.

No cambies parámetros simplemente para obtener mejores resultados.

No elimines resultados negativos.

No escondas fallos.

No redefinas métricas para hacerlas parecer mejores.

No declares una fase aprobada si una prueba importante falla.

Si el sistema termina con:

```text
CAGR inferior a SPY
```

eso es perfectamente aceptable para esta etapa.

La prioridad ahora es:

```text
CORRECTNESS
>
DATA INTEGRITY
>
EXECUTION REALISM
>
RISK CONTROL
>
STATISTICAL VALIDITY
>
REPRODUCIBILITY
>
PERFORMANCE OPTIMIZATION
```

---

# CONDICIÓN DE PARADA

Cuando termines estas correcciones:

**DETENTE.**

No implementes una nueva capa de alpha.

No optimices la estrategia.

No avances a una nueva fase.

Entrega únicamente el reporte de auditoría solicitado y espera revisión.

Si cualquier criterio de aprobación falla, marca:

```text
NOT APPROVED
```

y explica exactamente qué queda pendiente.

La prioridad absoluta es que **un resultado negativo sea confiable antes de intentar conseguir un resultado positivo**.
