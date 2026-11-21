# Fases 1 y 2 del plan maestro: 2008 dentro de la ventana y universo de 26 ETF (2026-11-21)

## Pruebas definidas antes de correrlas

Escrito el 2026-11-21 antes de ver ningún resultado de estos datos (historia de Tiingo desde 2002).

**Fase 1.** La misma lista de 7 retadores de `research-retador`, sin cambios, sobre
`config/universe-10etf-historia.json`. Mismo método: bootstrap por bloques de 21 sesiones, 2 000
remuestreos, Bonferroni con 7 comparaciones. Pregunta: ¿la mezcla núcleo 25 % + tendencia 75 % sigue
ganándole a la tendencia sola cuando 2008 entra en la ventana?

**Fase 2.** Un solo cambio: el universo. `config/universe-26etf.json` contra
`config/universe-10etf-historia.json`, con el mismo sistema en los dos lados y el spread que declara
cada universo. Dos comparaciones (Bonferroni con 2, intervalo al 97,5 %):

1. Principal: configuración de producción (núcleo 60/40 al 25 % + tendencia al 75 %).
2. Secundaria: tendencia sola.

Criterio para cambiar el universo de paper: «promover» en la principal y coste anual menor a un tercio
del retorno bruto. Ventanas de estrés fijas: 2007-10-09 a 2009-03-09, 2020-02-19 a 2020-03-23 y
2022-01-03 a 2022-10-14.

## Resumen

1. **Con 2008 dentro, la ventaja de la mezcla se achica y deja de ser concluyente.** Sharpe 0,60 contra
   0,48 de la tendencia sola: diferencia de +0,12, con intervalo de −0,06 a +0,32. El veredicto pasa de
   «promover» a «indistinguible». La mezcla sigue rindiendo más y cayendo menos en el total, pero ya no
   se puede afirmar que sea mejor.
2. **El universo de 26 ETF no mejora nada.** Sharpe 0,52 contra 0,60 del universo actual con la misma
   configuración. Veredicto «indistinguible», con el número por debajo. No se cambia el universo.
3. **Lo que sí queda firme:** la tendencia protegió en las tres crisis. En 2008 ganó 9 % mientras el
   60/40 perdía 32 %.

Ninguna configuración de paper se tocó.

## Términos

- **Sharpe:** retorno por encima de las letras del Tesoro dividido por la volatilidad.
- **Caída máxima:** peor pérdida desde un máximo anterior.
- **Intervalo:** rango donde cae la diferencia verdadera con la confianza pedida. Si incluye el cero, no
  se puede decir cuál de las dos es mejor.
- **Núcleo:** parte del capital que se queda fija en 60 % SPY y 40 % IEF.
- **Caja:** grupo de ETF que comparten fuente de riesgo. El sistema da el mismo riesgo a cada caja.

## Fase 1: los 7 retadores con 2008 dentro

Datos de Tiingo desde 2002. Ventana evaluada 2004-01-28 → 2026-11-20 (5 742 sesiones, casi 23 años).
Universo de historia larga: EFA por VEA, EEM por VWO, DBC por PDBC y SHY como efectivo.

| Estrategia | CAGR | Vol. | Sharpe | Caída máx. | Coste/año | Dif. de Sharpe contra la tendencia (intervalo 99,3 %) | Veredicto |
|---|---|---|---|---|---|---|---|
| **Tendencia sola** (lo que corría antes del 21-11) | 4,8 % | 6,7 % | 0,48 | −12,7 % | 0,52 % | — | — |
| Tendencia EWMAC + HRP | 5,1 % | 7,0 % | 0,49 | −13,1 % | 0,51 % | +0,01 (−0,13 a +0,16) | Indistinguible |
| Paridad de riesgo sin timing | 5,2 % | 6,6 % | 0,55 | −18,3 % | 0,04 % | +0,07 (−0,35 a +0,51) | Indistinguible |
| Núcleo de paridad + tendencia | 4,9 % | 6,3 % | 0,52 | −13,4 % | 0,34 % | +0,04 (−0,10 a +0,19) | Indistinguible |
| Perfil equilibrado | 5,1 % | 7,3 % | 0,48 | −12,2 % | 0,54 % | 0,00 (−0,14 a +0,14) | Indistinguible |
| Perfil crecimiento | 5,4 % | 7,6 % | 0,48 | −11,8 % | 0,53 % | 0,00 (−0,20 a +0,22) | Indistinguible |
| **Núcleo 25 % + tendencia 75 %** (en paper desde el 21-11) | 5,6 % | 6,5 % | 0,60 | −10,9 % | 0,49 % | +0,12 (−0,06 a +0,32) | Indistinguible |
| Núcleo 50 % + tendencia 50 % | 6,3 % | 7,2 % | 0,63 | −16,2 % | 0,44 % | +0,15 (−0,19 a +0,50) | Indistinguible |
| 60/40 pasivo (referencia) | 7,6 % | 10,5 % | 0,56 | −32,6 % | — | +0,08 (−0,46 a +0,66) | Indistinguible |

### Las tres crisis

Retorno total dentro de cada ventana, y entre paréntesis la peor caída dentro de ella.

| Estrategia | 2008 (oct-2007 a mar-2009) | Covid (feb a mar de 2020) | 2022 (ene a oct) |
|---|---|---|---|
| Tendencia sola | **+9,2 %** (−6,7 %) | −3,2 % (−6,8 %) | −7,6 % (−10,3 %) |
| Núcleo 25 % + tendencia 75 % | −1,4 % (−9,7 %) | −7,4 % (−8,5 %) | −10,8 % (−10,9 %) |
| Núcleo 50 % + tendencia 50 % | −11,6 % (−16,2 %) | −11,5 % (−11,6 %) | −14,1 % (−14,0 %) |
| Paridad de riesgo sin timing | −8,0 % (−17,4 %) | −9,3 % (−11,9 %) | −17,9 % (−17,4 %) |
| 60/40 pasivo | −32,3 % (−32,6 %) | −18,6 % (−18,9 %) | −21,0 % (−20,9 %) |

### Lectura

- **El estudio anterior le favorecía a la mezcla.** Su ventana empezaba en diciembre de 2008, justo
  después del desplome. Ahí el núcleo solo aportó subida. Con 2008 dentro, el núcleo cuesta en las
  crisis: en 2008 la tendencia sola ganó 9,2 % y la mezcla perdió 1,4 %.
- **La mezcla no queda refutada.** En 23 años rinde 0,8 puntos más al año y su caída máxima es menor
  (−10,9 % contra −12,7 %), porque la peor caída de la tendencia sola no fue en una crisis de acciones.
  Pero la diferencia de Sharpe ya no se distingue del ruido.
- **La tendencia cumple su función.** Es la única que termina 2008 en positivo. Un sistema sin timing
  (paridad de riesgo) perdió 8 % y el 60/40 perdió 32 %.
- **El 50 % de núcleo queda descartado para alguien que prioriza no perder:** −16,2 % de caída.

## Fase 2: universo de 26 ETF contra el actual

Misma ventana (desde 2004-01-27). Intervalo al 97,5 % por las dos comparaciones.

| Configuración | Universo | CAGR | Vol. | Sharpe | Caída máx. | Coste/año | Dif. de Sharpe (intervalo) | Veredicto |
|---|---|---|---|---|---|---|---|---|
| Núcleo 25 % + tendencia 75 % | 10 ETF | 5,6 % | 6,5 % | 0,60 | −11,0 % | 0,47 % | — | — |
| Núcleo 25 % + tendencia 75 % | 26 ETF | 4,8 % | 5,7 % | 0,52 | −12,8 % | 0,55 % | −0,09 (−0,23 a +0,07) | Indistinguible |
| Tendencia sola | 10 ETF | 4,8 % | 6,7 % | 0,48 | −12,7 % | 0,50 % | — | — |
| Tendencia sola | 26 ETF | 3,8 % | 5,6 % | 0,36 | −11,5 % | 0,58 % | −0,12 (−0,32 a +0,08) | Indistinguible |

### Por qué no ayudó ampliar

- **Los ETF nuevos no son apuestas nuevas.** La correlación entre el universo de 26 y el de 10 fue de
  0,91 a 0,94. Brasil, India, Europa y Japón caen juntos con SPY cuando hay crisis. Los fondos grandes
  consiguen independencia con futuros de tipos, divisas y materias primas de muchos países, con
  posiciones cortas. Con ETF solo en largo esa independencia no aparece.
- **El reparto por cajas movió riesgo a donde no hay prima.** El universo amplio tiene más cajas de
  bonos y de divisas. Las acciones bajaron de 27 % a 16 % del peso medio y los bonos subieron de 42 % a
  60 %. Las divisas (UUP, FXE, FXY) no pagan nada por tenerlas: sin poder ponerse corto, su tendencia
  casi no aporta.
- **Cuesta más.** 0,55 % al año contra 0,47 %, por ETF menos líquidos.
- Único punto a favor: en 2022 el universo amplio perdió menos (−4,9 % contra −10,8 %), por energía y
  dólar. No compensa el resto.

Esto corrige el plan maestro: la fase 2, tal como estaba escrita, no da el salto esperado. Añadir
mercados solo sirve si son de verdad independientes, y con ETF en largo hay pocos.

## Qué recomiendo

1. **Dejar el paper como está** (núcleo 25 % + tendencia 75 %, 10 ETF). No hay evidencia de que sea
   peor que la tendencia sola, y cambiar otra vez reinicia el conteo sin motivo. Lo que cambia es la
   expectativa: Sharpe cercano a 0,6, no a 0,76, y en una crisis como 2008 la mezcla pierde algo
   mientras la tendencia sola ganaba.
2. **No ampliar el universo.** Se queda en 10 ETF.
3. **Siguiente prueba (fase 3):** una familia de señal distinta sobre los mismos 10 ETF. La primera,
   momentum relativo dentro de cada clase, porque solo necesita precios. Carry necesita datos de
   rendimiento por ETF que todavía no tenemos.
4. **Lo que más pesa sigue siendo la fase 0.** Ningún resultado de estos se puede confirmar si el
   sistema no ejecuta cada día.

## Límites

- Datos ya vistos en parte: 2008-2026 se usó en el estudio anterior. Lo nuevo es 2004-2008.
- El efectivo de referencia es SHY (bonos de 1 a 3 años), que rinde algo más que las letras. Baja un
  poco todos los Sharpe por igual; no cambia las diferencias.
- Los ETF del universo amplio entran según se listan: INDA en 2012 y BNDX en 2013. Antes de 2007 el
  universo amplio tenía unos 17 ETF.
- Los spreads del universo de 26 son estimaciones, no medidas propias.
- Dos pruebas más en el registro. Ninguna pasa, así que no hay ganador elegido por suerte.

## Código

- `research/challenger.py`: `stress_report` (las tres ventanas de crisis en cada fila del estudio),
  `run_universe_study` (mismo sistema en dos universos) y `settings_with_universe_spreads`.
- Pruebas en `tests/test_research_stress.py`.
