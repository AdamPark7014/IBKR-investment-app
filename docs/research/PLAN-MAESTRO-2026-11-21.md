# Plan maestro: un algoritmo más predictivo (2026-11-21)

Pedido de Adam: que el algoritmo sea mucho más predictivo, que contemple sus fallos y que copie lo que
hacen los fondos más grandes. Este plan dice qué se puede copiar, en qué orden y con qué criterio se
avanza de una fase a la siguiente. La investigación de fondo está en
[`QUANT-FUNDS-PLAYBOOK-2026-10-21.md`](QUANT-FUNDS-PLAYBOOK-2026-10-21.md).

## La idea central

Los fondos grandes no predicen mejor que nosotros en cada apuesta. Predicen igual de poco, pero hacen
miles de apuestas independientes. La relación se llama ley fundamental de la gestión activa:

    calidad del resultado ≈ acierto por apuesta × √(número de apuestas independientes)

- **Acierto por apuesta (IC, coeficiente de información):** correlación entre lo que la señal predice y
  lo que pasa después. 0 es no saber nada, 1 es adivinar siempre.
- **Apuestas independientes:** mercados y señales que no se mueven juntos.

Medido hoy con 20 años de datos reales (`ibtrader.research.predictive`):

| Señal de tendencia | IC a 1 día | IC a 21 días | IC a 63 días |
|---|---|---|---|
| Muy rápida (2/8 días) | −0,02 | −0,01 | +0,02 |
| Media (16/64 días) | +0,01 | +0,04 | +0,09 |
| Lenta (32/128 días) | +0,02 | +0,05 | +0,10 |
| Muy lenta (64/256 días) | +0,02 | +0,04 | +0,07 |
| Momentum 1, 3 y 12 meses | +0,01 | +0,03 | +0,07 |

Lectura:

- Las señales lentas predicen algo (IC de 0,04 a 0,10) y lo hacen en las dos mitades de la muestra.
- Las rápidas no predicen o predicen al revés. Operar más seguido con ellas no aporta y sube el coste.
- Con un error estándar prudente (retornos solapados y mercados correlacionados), ningún IC suelto llega a
  t = 2. La evidencia es que el signo se repite en velocidades, horizontes y mitades, no un número aislado.
- Un IC de 0,05 es normal en la industria. El mejor modelo de aprendizaje automático publicado sobre
  30 000 acciones explica el 0,4 % del retorno mensual (Gu, Kelly y Xiu, 2020).
- Por mercado, el poder predictivo está en materias primas (0,12), oro (0,08) y acciones
  internacionales (0,05). En bonos del Tesoro y bienes raíces es cero o negativo.

Nuestro problema no es el acierto, es el número de apuestas: 9 ETF que se mueven bastante juntos y una
sola familia de señal. **El plan sube el número de apuestas independientes, no la complejidad del
modelo.**

## Qué se copia de los fondos y qué no

| Práctica | Quién | En nuestro sistema |
|---|---|---|
| Muchas señales débiles y poco correlacionadas (correlación menor a 0,7 con lo que ya hay) | WorldQuant | Fases 2 y 3 |
| Tendencia a varias velocidades, repartiendo riesgo por clase de activo | Man AHL | Ya está |
| Registrar cada prueba y exigir t ≥ 3 | Man AHL, Harvey y Liu | Ya está (102 pruebas registradas) |
| Guardar cada dato con la fecha en que se conoció | Jane Street, Man | Ya está (vintages) |
| Mismo código en investigación y en producción | Jane Street, Cubist | Ya está |
| Calibrar el modelo de costes con las ejecuciones propias | AQR | Fase 1 |
| Operar en real con poco capital antes de escalar | Man AHL | Fase 6 |
| Límites de pérdida que recortan riesgo solos | Millennium | Ya está (20 %); se prueba en la fase 4 |

Lo que no se puede copiar, y por qué:

- **Alta frecuencia.** Requiere latencia de milisegundos y coste por orden que una cuenta personal no tiene.
- **Datos alternativos.** Cuestan de 56 000 a 80 000 USD por conjunto y sirven para acciones sueltas, no para ETF.
- **Apalancamiento alto.** Ya medido: el interés del margen se come la ganancia.
- **Buscar entre millones de fórmulas.** Con 5 000 días de datos, casi todo lo que aparece es suerte.

## Fases

Cada fase tiene un criterio de salida. Si no se cumple, no se pasa a la siguiente.

### Fase 0. Que el sistema corra solo (1 a 2 semanas)

Hoy ejecutó 2 de 9 sesiones. Sin esto, nada de lo demás se puede medir.

- Mover la operación a un equipo siempre encendido, o dejar la laptop enchufada en horario de bolsa.
- Arranque y reinicio automático del Gateway; aviso al teléfono si falla el plan o la ejecución.
- Encontrar por qué el plan se queda colgado en la comprobación cruzada con Yahoo y ponerle tiempo límite.
- Subir el tope por orden solo para BIL, para invertir el efectivo en días y no en 60 sesiones.

**Criterio de salida:** 20 sesiones seguidas con plan y ejecución sin intervención.

### Fase 1. Medir sin engañarse (2 semanas, en paralelo con la fase 0)

- Hecho: prueba pareada contra la estrategia en producción (`research-retador`) e IC por señal.
- Bajar historia desde 2002 para incluir 2008 en la ventana evaluada.
- Calibrar el modelo de costes con las ejecuciones reales de paper (registro de deslizamiento).
- Pruebas de estrés fijas: 2008, marzo de 2020 y 2022, con el peor mes y la peor caída de cada una.

**Criterio de salida:** un informe por candidato con retorno, caída, coste real y comportamiento en las
tres crisis.

### Fase 2. Más mercados (3 a 4 semanas)

Es el paso con mejor relación entre ganancia esperada y riesgo de sobreajuste, porque no añade
parámetros: aplica la misma señal a más mercados poco correlacionados.

- Universo de 25 a 35 ETF líquidos: acciones por región, bonos de otros países y de crédito, materias
  primas por grupo (energía, metales, agrícolas), divisas.
- Se elige por liquidez, coste y correlación, antes de mirar cómo rindió cada uno.
- Cuenta como una sola prueba: el universo entero contra el actual, con la prueba pareada.

**Criterio de salida:** veredicto «promover» contra la estrategia en producción y coste anual menor
a un tercio del retorno bruto.

### Fase 3. Más familias de señal (6 a 8 semanas)

Una prueba por familia, definida por escrito antes de correrla. Cada familia debe tener IC positivo en
las dos mitades de la muestra y correlación menor a 0,7 con la tendencia.

1. **Carry:** preferir lo que paga más por tenerlo (cupón, dividendo, pendiente de la curva de tipos).
   Es la familia con más evidencia después de la tendencia. Necesita datos de rendimiento por ETF.
2. **Momentum relativo:** dentro de cada clase, sobreponderar lo que más subió frente a sus pares.
3. **Valor a largo plazo:** lo que cayó mucho en 5 años tiende a recuperar. Señal lenta y débil, pero
   poco correlacionada con la tendencia.

**Criterio de salida:** al menos una familia nueva con «promover» en la prueba pareada.

### Fase 4. Riesgo y fallos (en paralelo con las fases 2 y 3)

- Lista escrita de modos de fallo y qué hace el sistema en cada uno: dato malo, dato tardío, orden a
  medias, Gateway caído, precio fuera de rango, ETF suspendido, desconexión durante la ejecución.
- Simulacro de cada uno en paper, con el interruptor de emergencia incluido.
- Límite por clase de activo, además del límite por ETF.
- Comparación mensual entre lo que el backtest esperaba y lo que paper hizo.

**Criterio de salida:** cada modo de fallo probado una vez en paper con el resultado anotado.

### Fase 5. Aprendizaje automático, solo para combinar (después de la fase 3)

Tiene sentido cuando haya al menos tres familias de señal. Antes no hay nada que combinar.

- Modelos sencillos (regresión regularizada, árboles poco profundos) que decidan cuánto peso dar a
  cada familia según el régimen de volatilidad.
- Validación cruzada con purga y embargo, que ya existe en el repo.
- Expectativa honesta: mejora pequeña. Si no supera a los pesos iguales en la prueba pareada, se descarta.

### Fase 6. Dinero real (tras 6 meses de paper con operación limpia)

- Capital pequeño primero, con el mismo código y la configuración congelada.
- Datos de mercado en vivo contratados y comisiones Tiered.
- El paso a real lo ejecuta Adam; Claude prepara el script y las verificaciones.

## Qué esperar

- Hoy: Sharpe de 0,55 con solo tendencia y 0,76 con la mezcla activada este mismo día.
- Objetivo realista con las fases 2 y 3: Sharpe entre 0,8 y 1,0 después de costes. Los fondos de
  tendencia diversificados llevan décadas en torno a 0,8.
- Un Sharpe de 2 o más con ETF diarios no existe fuera de un backtest sobreajustado. Si algún resultado
  lo muestra, lo primero es buscar el error.

## Reglas que no se rompen

1. Ninguna señal entra a producción sin «promover» en la prueba pareada.
2. Cada prueba se define por escrito antes de correrla y queda en el registro.
3. La configuración en producción solo cambia con el sí de Adam y se vuelve a congelar.
4. Sin apalancamiento, sin intradía y sin IA enviando órdenes.
