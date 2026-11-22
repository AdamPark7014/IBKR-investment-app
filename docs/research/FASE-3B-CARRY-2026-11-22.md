# Fase 3 del plan maestro: carry (2026-11-22)

## Prueba definida antes de correrla

Escrito el 2026-11-22 antes de ver ningún resultado de esta señal.

**Señal (`carry_12m`).** Para cada ETF: lo que pagó en los últimos 12 meses (suma de sus repartos
dividida por su precio sin ajustar), menos lo mismo del ETF de efectivo, dividido por su volatilidad
anual. Positivo = paga más que el efectivo por unidad de riesgo. Usa los repartos que ya vienen en los
datos de Tiingo. No tiene parámetros que ajustar.

**Límite conocido de antemano.** El oro y las materias primas no reparten nada, así que su carry sale
negativo siempre que el efectivo pague algo. En un fondo, el carry de materias primas se mide con la
curva de futuros; con ETF no se puede.

**Candidato único.** La configuración de paper (núcleo 60/40 al 25 % + tendencia al 75 %) con la señal
repartida por familias: 50 % tendencia y 50 % carry. Es el mismo reparto fijado para el momentum
relativo.

**Comparación.** Contra la configuración de paper, en `config/universe-10etf-historia.json`, ventana
2004-2026, bootstrap por bloques de 21 sesiones, 2 000 remuestreos. Una comparación: intervalo al 95 %.

**Criterios:** IC positivo en las dos mitades a 21 y 63 días; correlación menor a 0,7 con la
tendencia; «promover» en la prueba pareada. Si falla el tercero, no entra a paper.

## Resumen

**El carry no funciona con estos ETF. No entra a paper.** Falla dos de los tres criterios.

- Criterio 1, poder predictivo: **no pasa**. IC de −0,03 a 21 días y −0,05 a 63 días. Fue positivo en
  la primera mitad (+0,05) y negativo en la segunda (−0,14).
- Criterio 2, independencia: pasa. Correlación de −0,11 con la tendencia.
- Criterio 3, prueba pareada: **no pasa**. Sharpe 0,59 contra 0,64 de paper; diferencia −0,05 con
  intervalo de −0,24 a +0,13. La caída máxima empeora de −10,9 % a −15,7 %.

## Prueba pareada

Ventana 2004-12-27 → 2026-11-20 (el carry necesita un año más de historia para arrancar).

| Estrategia | CAGR | Vol. | Sharpe | Caída máx. | Coste/año | Dif. de Sharpe (intervalo 95 %) | Veredicto |
|---|---|---|---|---|---|---|---|
| **Paper** (núcleo 25 % + tendencia 75 %) | 5,9 % | 6,4 % | 0,64 | −10,9 % | 0,49 % | — | — |
| Paper + carry | 5,1 % | 5,7 % | 0,59 | −15,7 % | 0,35 % | −0,05 (−0,24 a +0,13) | Indistinguible |

En 2022 perdió 15,6 % contra 10,8 % de paper.

## Por qué falla

- **Con ETF, el carry es casi una apuesta fija por bonos.** La señal media es fuerte y positiva en IEF,
  TLT, TIP y VNQ, y negativa en oro. El peso medio en bonos sube de 42 % a 53 %. En 2022, cuando los
  bonos cayeron, eso costó.
- **Castiga al oro, que fue de lo mejor del periodo.** El oro no reparte nada, así que la señal lo
  evita siempre. El IC del carry en GLD es −0,42: predijo al revés.
- **El carry de verdad no se ve en un ETF.** Los fondos lo miden con la curva de futuros de cada
  mercado y entre divisas. El reparto de un ETF es una aproximación pobre.

## Conclusión de la fase 3

Las tres familias del plan quedaron probadas o descartadas: momentum relativo (predice, no mejora),
carry (no predice) y valor a largo plazo (no se probó: exige 5 años más de calentamiento y es la más
débil de las tres). La señal de paper se queda como está.

## Código

- `pipeline/rules.py`: `trailing_yield`, `carry_forecast`, `EXTERNAL_RULES`.
- `pipeline/system.py`: `run_system(..., extra_raw=...)` para reglas que no salen del precio.
- `strategy/pipeline_strategy.py`: calcula el carry con los repartos de los datos.
- `research/challenger.py`: `CARRY_CHALLENGER`. Pruebas en `tests/test_carry_rule.py`.
- Todo apagado por defecto. La configuración congelada no cambia.
