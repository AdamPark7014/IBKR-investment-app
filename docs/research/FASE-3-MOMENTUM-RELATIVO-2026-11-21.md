# Fase 3 del plan maestro: momentum relativo (2026-11-21)

## Prueba definida antes de correrla

Escrito el 2026-11-21 antes de ver ningún resultado de esta señal.

**Señal (`relmom_1_3_12`).** Para cada ETF se toma el mismo momentum de 1, 3 y 12 meses que ya usa la
tendencia (retorno dividido por su volatilidad) y se le resta la media de sus pares ese día. Los pares
son los ETF de su misma clase: acciones (SPY, EFA, EEM), bonos (IEF, TLT, TIP) y activos reales (GLD,
DBC, VNQ). Positivo = subió más que sus pares. No tiene parámetros nuevos.

**Candidato único.** La configuración de paper (núcleo 60/40 al 25 % + tendencia al 75 %) con la parte
de señal repartida por familias: 50 % tendencia (sus cuatro reglas a partes iguales) y 50 % momentum
relativo. El reparto a partes iguales por familia se fija aquí y no se ajusta después.

**Comparación.** Contra la configuración de paper, en `config/universe-10etf-historia.json`, ventana
2004-2026, bootstrap por bloques de 21 sesiones, 2 000 remuestreos. Una sola comparación: intervalo
al 95 %.

**Criterios (los del plan maestro):**

1. IC positivo en las dos mitades de la muestra, a 21 y a 63 días.
2. Correlación menor a 0,7 entre el pronóstico de momentum relativo y el de la tendencia.
3. Veredicto «promover» en la prueba pareada.

Si falla el 3, la señal no entra a paper aunque pasen el 1 y el 2.

## Resumen

**La señal predice, pero no mejora la cartera lo suficiente. No entra a paper.**

- Criterio 1, poder predictivo: **pasa**. IC de 0,07 a 21 días y 0,10 a 63 días, positivo en las dos
  mitades de la muestra. Es igual o mejor que el de la tendencia.
- Criterio 2, independencia: **pasa**. Correlación de 0,50 con la tendencia.
- Criterio 3, prueba pareada: **no pasa**. Sharpe 0,66 contra 0,60 de paper; diferencia +0,05 con
  intervalo de −0,07 a +0,18. Veredicto «indistinguible».

Además, la caída máxima empeora de −10,9 % a −15,1 %. Para alguien que prioriza no perder capital, eso
solo ya la descarta.

## Términos

- **IC (coeficiente de información):** correlación entre lo que la señal predice y lo que pasa después.
  0 es no saber nada. En la industria, 0,05 es un valor normal.
- **Momentum relativo:** preferir, dentro de cada clase, lo que subió más que sus pares.
- **Rotación:** cuántas veces al año se compra y vende el equivalente al capital.

## Poder predictivo (diagnóstico)

Ventana 2004-01-27 → 2026-11-20, partida en dos en 2015-06-23.

| Señal | IC a 21 días (todo / 1.ª mitad / 2.ª mitad) | IC a 63 días (todo / 1.ª mitad / 2.ª mitad) |
|---|---|---|
| Momentum relativo | 0,07 / 0,07 / 0,07 | 0,10 / 0,12 / 0,07 |
| Tendencia (media de sus 4 reglas) | 0,04 / 0,02 / 0,04 | 0,08 / 0,06 / 0,10 |

Por ETF, a 63 días: EEM 0,22, GLD 0,19, IEF 0,12, EFA 0,09, DBC 0,05, TLT 0,02, TIP 0,00, VNQ −0,01,
SPY −0,07. Funciona en emergentes y oro. En SPY va al revés.

## Prueba pareada

| Estrategia | CAGR | Vol. | Sharpe | Caída máx. | Coste/año | Rotación | Dif. de Sharpe (intervalo 95 %) | Veredicto |
|---|---|---|---|---|---|---|---|---|
| **Paper** (núcleo 25 % + tendencia 75 %) | 5,6 % | 6,5 % | 0,60 | −10,9 % | 0,49 % | 11× | — | — |
| Paper + momentum relativo | 6,1 % | 6,6 % | 0,66 | −15,1 % | 0,78 % | 22× | +0,05 (−0,07 a +0,18) | Indistinguible |

| Crisis | Paper | Paper + momentum relativo |
|---|---|---|
| 2008 (retorno / peor caída) | −1,4 % / −9,7 % | −0,6 % / −12,0 % |
| Covid 2020 | −7,4 % / −8,5 % | −7,7 % / −9,8 % |
| 2022 | −10,8 % / −10,9 % | −14,1 % / −15,1 % |

## Por qué una señal que predice no mejora la cartera

- **Elige al menos malo.** En 2022 cayeron acciones y bonos a la vez. La tendencia dice «sal de todo».
  El momentum relativo dice «quédate con el que cae menos», y ese también cae. Por eso la peor caída
  sube a −15,1 %. La señal ordena bien los ETF entre sí, pero no dice si conviene estar invertido.
- **Solo en largo se usa la mitad de la señal.** Un fondo compra al mejor y vende en corto al peor de
  cada clase, y así cobra la diferencia sin exponerse al mercado. Nosotros solo podemos comprar al
  mejor; la otra mitad se pierde.
- **Opera el doble.** La rotación pasa de 11 a 22 veces al año y el coste de 0,49 % a 0,78 %. Ese
  0,29 % extra ya está descontado del resultado: la señal gana más antes de costes, pero una parte
  se va en operar.
- **Tres pares por clase es poco.** Con 3 ETF por grupo, «mejor que sus pares» cambia con facilidad.

## Qué se concluye de las tres fases

Llevamos tres intentos honestos (mezcla con 2008 dentro, 26 ETF, momentum relativo) y ninguno le gana
con claridad a lo que ya corre. Eso dice dónde está el techo: con 10 ETF, solo en largo, operación
diaria y sin apalancamiento, un Sharpe cercano a 0,6 con caída máxima cercana a −11 % es lo que hay.
Lo que tienen los fondos grandes y nosotros no es poder ponerse corto y operar cientos de mercados con
futuros. No es una fórmula mejor.

## Qué recomiendo

1. **Paper se queda como está.**
2. **No ajustar esta señal** (otros pesos, otro reparto) para hacerla pasar. Sería sobreajuste.
3. **Queda una familia por probar: carry** (preferir lo que paga más cupón o dividendo). Necesita bajar
   de Tiingo los dividendos pagados por cada ETF. Es la familia con más evidencia después de la
   tendencia y sí funciona solo en largo. Expectativa honesta: mejora pequeña o nula.
4. **Lo que más retorno da ahora es la fase 0.** Con el 87 % del capital sin invertir, cada mes que el
   sistema no ejecuta cuesta más que todo lo que estas señales podrían añadir.

## Límites

- El IC es un diagnóstico agrupado de todos los ETF y fechas; no cuenta como prueba.
- Datos ya vistos en parte (2008-2026 se usó en estudios anteriores).
- Una prueba más en el registro. No pasa, así que no hay ganador elegido por suerte.

## Código

- `pipeline/rules.py`: `relative_momentum` y `CROSS_SECTIONAL_RULES`.
- `pipeline/system.py`: `SystemConfig.peer_groups` y la regla `relmom_1_3_12`. Apagada por defecto; la
  configuración congelada no cambia.
- `research/challenger.py`: `PAPER_MIX`, `RELMOM_CHALLENGER`, `peer_groups_from_universe`.
- Pruebas en `tests/test_relative_momentum.py`.
