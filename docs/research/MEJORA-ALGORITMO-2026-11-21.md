# Mejora del algoritmo: qué se probó y qué sí funciona (2026-11-21)

Pedido de Adam: «mejora e hiper perfecciona el algoritmo». Este documento dice qué se midió, con qué
método y qué conviene cambiar. Nada de lo que corre en paper se tocó.

## Resumen

1. **Afinar la señal no sirve.** Cinco variantes contra la estrategia actual, con 18 años de datos
   reales y costes: ninguna se distingue de ella. Seguir probando parámetros sería sobreajuste.
2. **Una mejora sí pasa la prueba:** dejar el 25 % del capital en un núcleo pasivo 60/40 y el 75 % en
   la tendencia. Sube el retorno de 4,7 % a 6,0 % al año y baja la caída máxima de −11,0 % a −9,5 %.
3. **El problema mayor no es el algoritmo, es que casi no corre.** En 9 sesiones de bolsa solo hubo
   2 ejecuciones. El 87 % del millón simulado sigue en efectivo sin invertir.

## Términos

- **Sharpe:** retorno por encima de las letras del Tesoro dividido por la volatilidad. Aquí se calcula
  contra BIL (el ETF de letras), no contra cero.
- **CAGR:** retorno anual compuesto.
- **Caída máxima:** peor pérdida desde un máximo anterior.
- **Tendencia:** comprar lo que viene subiendo y salir de lo que viene bajando.
- **60/40:** 60 % acciones de EE. UU. (SPY) y 40 % bonos del Tesoro a 7-10 años (IEF), sin moverlo.
- **Sobreajuste:** elegir parámetros que calzan con el pasado por casualidad y fallan después.
- **Prueba pareada:** comparar dos estrategias día a día en vez de comparar sus dos promedios.
- **Bonferroni:** exigir más confianza cuantas más comparaciones se hacen en la misma tanda.

## Por qué «hiper perfeccionar» la señal es mala idea

Con 18 años de datos diarios, el error estándar de un Sharpe es de unos 0,24. Dos variantes que
difieren en 0,05 o 0,10 de Sharpe no se pueden ordenar: la diferencia es ruido. El registro de pruebas
ya tenía 102 intentos; cada intento nuevo sube la probabilidad de elegir un ganador por suerte.

Por eso se cambió la pregunta. Ya no es «¿qué variante tiene el mejor Sharpe?», sino «¿alguna le gana
a la que ya corre, comparada día a día?». Las dos operan los mismos ETF los mismos días y sus retornos
tienen correlación de hasta 0,98, así que la diferencia diaria tiene mucho menos ruido que cada
Sharpe por separado.

## Método (`ibtrader research-retador`)

- Mismo motor, costes de IBKR y gestor de riesgo que `research-portfolio`.
- Datos de Tiingo, ventana evaluada 2008-12-09 → 2026-11-06 (4 506 sesiones).
- La lista de retadores se fijó antes de mirar resultados: 3 variantes que ya estaban en el registro,
  2 perfiles de riesgo y 2 mezclas con núcleo pasivo.
- Bootstrap por bloques de 21 sesiones sobre los pares de retornos, 2 000 remuestreos.
- Bonferroni con 7 comparaciones: el intervalo se calcula al 99,3 %.
- «Promover» solo si todo el intervalo de la diferencia de Sharpe queda por encima de cero.

## Resultados (universo de 10 ETF que corre en paper)

| Estrategia | CAGR | Vol. | Sharpe | Caída máx. | Coste/año | Dif. de Sharpe contra la actual (intervalo) | Veredicto |
|---|---|---|---|---|---|---|---|
| **Actual en paper** (tendencia, riesgo igual por ETF) | 4,7 % | 6,4 % | 0,55 | −11,0 % | 0,48 % | — | — |
| Tendencia EWMAC + HRP | 5,3 % | 6,7 % | 0,62 | −10,9 % | 0,45 % | +0,07 (−0,03 a +0,17) | Indistinguible |
| Paridad de riesgo sin timing | 5,6 % | 6,5 % | 0,68 | −17,8 % | 0,04 % | +0,12 (−0,27 a +0,58) | Indistinguible |
| Núcleo de paridad + tendencia | 4,6 % | 6,1 % | 0,57 | −12,1 % | 0,33 % | +0,01 (−0,14 a +0,18) | Indistinguible |
| Perfil equilibrado (50 % del riesgo en acciones) | 5,0 % | 6,9 % | 0,55 | −10,8 % | 0,49 % | 0,00 (−0,16 a +0,16) | Indistinguible |
| Perfil crecimiento (60 % del riesgo en acciones) | 5,1 % | 7,3 % | 0,55 | −10,9 % | 0,48 % | 0,00 (−0,24 a +0,25) | Indistinguible |
| **Núcleo 60/40 al 25 % + tendencia al 75 %** | **6,0 %** | 6,3 % | **0,76** | **−9,5 %** | 0,46 % | **+0,21 (+0,01 a +0,41)** | **Promover** |
| Núcleo 60/40 al 50 % + tendencia al 50 % | 7,3 % | 7,0 % | 0,85 | −12,7 % | 0,43 % | +0,30 (−0,07 a +0,68) | Indistinguible |
| 60/40 pasivo (referencia) | 9,8 % | 10,2 % | 0,84 | −21,3 % | — | +0,28 (−0,31 a +0,92) | Indistinguible |

Con el universo largo (DBC en lugar de PDBC) los números cambian en la segunda cifra y los veredictos
son los mismos.

## Lectura

**La tendencia sola rinde poco.** En promedio tuvo 27 % en acciones, 41 % en bonos y 15 % en letras.
Recorta las caídas a la mitad, pero deja pasar buena parte de la subida de las acciones. El 60/40
pasivo ganó 5 puntos más al año en esta ventana, y esa diferencia de retorno sí es significativa
(intervalo de +0,1 a +10,0 puntos).

**Por qué funciona la mezcla.** El núcleo cobra la prima de tener acciones y bonos. La tendencia cobra
por seguir movimientos largos y protege en caídas largas. La correlación entre las dos fue de 0,39.
Dos fuentes de retorno positivas y poco correlacionadas dan, juntas, más retorno por unidad de riesgo
que cada una sola. Es un efecto de diversificación, no un parámetro afinado.

**Por qué el 25 % y no el 50 %.** El 25 % es la única mezcla que pasa la prueba. El 50 % rinde más en
el papel, pero su intervalo incluye el cero y se parece menos a la estrategia actual, así que hay
menos certeza. Además, con el 50 % SPY puede superar el tope de 40 % por símbolo del control previo a
la orden, que el backtest no modela.

## Límites que hay que tener presentes

- **La ventana empieza en diciembre de 2008, justo después del desplome.** Es el mejor arranque posible
  para el 60/40. Con 2007-2009 incluido, el 60/40 cayó −32,6 %, no −21,3 %. La tendencia no se pudo
  medir en 2008 porque el sistema necesita dos años de calentamiento y los datos empiezan en 2006.
- **El margen es estrecho.** El límite inferior del intervalo es +0,01. Pasa, pero por poco.
- **Son datos ya vistos.** La prueba limpia es el periodo de paper que viene.
- **Ninguna estrategia pasa la compuerta absoluta** (t ≥ 3 y percentil 95). La mezcla le gana a la
  actual; eso no la convierte en una estrategia aprobada para dinero real.
- **Los costes están calculados con 100 000 USD.** La comisión mínima de 1 USD por orden pesa más ahí
  que en la cuenta de un millón, así que el coste real en paper será menor.

## Estado de la operación en paper

| Fecha de los datos | Plan | Ejecución en la sesión siguiente |
|---|---|---|
| 09-11 | Sí | Sí, 5 de 10 órdenes llenadas |
| 10-11 | Sí | Sí, 8 de 8 (4 tras escalar a Adaptive) |
| 11-11 | Sí | No |
| 12-11 y 13-11 | No | No |
| 16-11 | Sí | No: el Gateway no respondió el 17-11 y el plan caducó |
| 17-11 a 20-11 | No | No |

- El paso de reintento (escalar a Adaptive) funcionó el 11-11. El fallo al archivar las órdenes quedó
  corregido ese día, pero no ha habido otra ejecución que lo confirme.
- La corrida de plan de hoy sábado a las 10:26 quedó sin terminar después de la comprobación cruzada
  de datos. No se tocó.
- Posiciones: unos 128 000 USD invertidos de 1 000 000. El objetivo actual pide 65 % en BIL, pero con
  el tope de 10 000 USD por orden llenar BIL tomaría más de 60 sesiones.
- Consecuencia: los meses de paper todavía no miden el algoritmo. Miden una cartera casi vacía.

## Qué se dejó hecho en el código

- `SystemConfig.core_weights` y `core_frac`: núcleo pasivo dentro del mismo sistema, de modo que la
  investigación y la producción usan el mismo cálculo. Por defecto está apagado.
- `SystemConfig.box_budgets`: reparto del riesgo por caja. Por defecto, igual que antes.
- `ibtrader research-retador`: la prueba pareada de este documento.
- Pruebas en `tests/test_research_challenger.py`. La configuración congelada no cambia.

## Decisiones de Adam

1. **Pasar el paper a núcleo 25 % + tendencia 75 %.** Requiere volver a congelar la configuración.
   Como solo ha habido 2 ejecuciones, reiniciar el conteo de paper casi no cuesta nada.
2. **Dónde corre el sistema.** Mientras dependa de una laptop que se apaga, el paper no acumula
   historia útil. Opciones: dejar la laptop encendida y enchufada en horario de bolsa, o moverlo a un
   equipo siempre encendido.
3. **Tope por orden para BIL.** Subirlo solo para el ETF de letras permite estacionar el efectivo en
   pocos días. También requiere volver a congelar.

## Siguiente paso de investigación

Bajar de Tiingo la historia desde 2002 para los ETF que la tienen (SPY, IEF, TLT, GLD, VNQ) y repetir
la prueba con 2008 dentro de la ventana. Es la pieza que falta para saber cuánto protege la tendencia
cuando el núcleo cae fuerte.
