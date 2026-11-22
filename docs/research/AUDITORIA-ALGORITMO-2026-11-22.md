# Auditoría exigente del algoritmo (2026-11-22)

Pedido de Adam: «hazle auditoría mega exigente, encuentra fallos predictivos y mejóralo aún más, sin
preguntarme». Se buscó lo que suele inflar un backtest: usar datos del futuro, ejecutar a un precio que
en la realidad no se consigue, costes demasiado bajos, y diferencias entre lo que el backtest supone y
lo que hace paper. Ventana 2004-01-27 → 2026-11-20, configuración de paper (núcleo 25 % + tendencia 75 %).

## Resumen

1. **No hay fuga de datos del futuro.** Se recortó la historia en 5 fechas y los pesos de cada día
   salieron idénticos, al decimal, a los calculados con toda la historia.
2. **El resultado no depende de ejecutar en el minuto exacto.** Ejecutando un día tarde, el Sharpe pasa
   de 0,60 a 0,59.
3. **Aguanta costes más altos.** Con el triple de costes, el Sharpe baja de 0,60 a 0,52 y sigue siendo
   mejor que la tendencia sola con costes normales (0,48).
4. **Se encontró un fallo real entre backtest y paper, y quedó corregido.** El control previo a la orden
   rechazaba entera una compra que dejaba un ETF por encima del 40 %, en vez de comprar hasta el 40 %.
5. **Otro fallo, encontrado y corregido ayer:** el aviso de caída de paper no veía la curva real del
   bróker.

## Términos

- **Fuga de datos (sesgo de anticipación):** que el cálculo de un día use precios de días posteriores.
  Es el error más común y el que más infla un backtest.
- **Sharpe:** retorno por encima de las letras del Tesoro dividido por la volatilidad.
- **Paridad:** que el backtest y paper hagan exactamente lo mismo con los mismos datos.
- **Rotación:** cuántas veces al año se compra y vende el equivalente al capital.

## Pruebas

### 1. Fuga de datos: prueba de truncamiento

Para cada fecha de corte se calcularon los pesos con la historia hasta esa fecha y se compararon con
los de la corrida completa en todos los días anteriores.

| Corte | Diferencia máxima en el día | Diferencia máxima en todo el historial previo |
|---|---|---|
| 2008-10-10 (crisis) | 0 | 0 |
| 2013-06-21 (pánico de tasas) | 0 | 0 |
| 2020-03-20 (covid) | 0 | 0 |
| 2022-06-16 (inflación) | 0 | 0 |
| 2025-04-08 | 0 | 0 |

Además, el motor del backtest decide con el cierre de ayer y opera a la apertura de hoy, con costes.
Paper hace lo mismo: planea tras el cierre y ejecuta a la mañana siguiente.

### 2. Sensibilidad

| Escenario | CAGR | Sharpe | Caída máx. | Coste/año | Dif. de Sharpe contra paper (intervalo 95 %) |
|---|---|---|---|---|---|
| **Paper tal como está** | 5,61 % | 0,60 | −10,9 % | 0,49 % | — |
| Ejecutar un día tarde | 5,58 % | 0,59 | −11,2 % | 0,49 % | −0,01 (−0,04 a +0,02) |
| Costes al doble | 5,33 % | 0,56 | −11,0 % | 0,93 % | −0,04 |
| Costes al triple | 5,04 % | 0,52 | −11,3 % | 1,36 % | −0,09 |
| Con tope de 40 % por ETF dentro del modelo | 5,68 % | 0,62 | −11,0 % | 0,48 % | +0,01 (0,00 a +0,04) |
| Tendencia sola | 4,83 % | 0,48 | −12,7 % | 0,52 % | −0,12 |
| Tendencia sola, costes al triple | 4,20 % | 0,39 | −13,4 % | 1,45 % | −0,22 |

Lectura:

- Una señal sobreajustada al momento exacto de ejecución se cae al retrasarla un día. Esta no.
- Con costes al triple el sistema sigue ganando a las letras. El margen frente a errores en el modelo de
  costes es amplio. Los costes reales de paper se medirán con el registro de deslizamiento.
- La mezcla con núcleo pasivo es menos sensible a los costes que la tendencia sola, porque el núcleo
  casi no opera.

### 3. Paridad entre backtest y paper: el fallo encontrado

**Qué pasaba.** El modelo puede pedir más de 40 % en un ETF: en la historia SPY llegó a 62 % (15 % del
núcleo más la tendencia). El control previo a la orden tiene un tope de 40 % por ETF, pero en vez de
recortar la compra la **rechazaba entera**. Si el objetivo de SPY era 55 % y la cartera tenía 30 %, no
se compraba nada de SPY y ese capital quedaba en efectivo sin invertir. El backtest no modelaba ese
tope, así que paper iba a rendir distinto del backtest justo cuando el modelo más confiaba en un ETF.

**La corrección.** Antes de armar las órdenes, cada peso se recorta al 40 % y lo recortado va a letras
(`run_daily.cap_weights`). Se compra hasta el tope en vez de nada. El modelo de investigación tiene lo
mismo (`SystemConfig.symbol_cap`), y con él el Sharpe histórico es 0,62 contra 0,60: no cuesta nada.

**Por qué no hubo que volver a congelar la configuración.** No cambia ningún parámetro: el tope de 40 %
ya estaba en la configuración congelada. Cambia el código para que se cumpla de la forma correcta. El
freeze sigue vigente.

## Lo que la auditoría no encontró y por qué no se cambió nada más

- **La señal no tiene un fallo predictivo que corregir.** Las cuatro mejoras de señal probadas en estos
  días (mezcla con 2008, 26 ETF, momentum relativo y carry) quedaron indistinguibles o peores. Ajustar
  parámetros hasta que algo pase sería sobreajuste.
- **La rotación de 11 veces al año es alta para una tendencia lenta**, pero cuesta 0,49 % al año y con
  el triple de costes el sistema sigue ganando. Bajarla moviendo la banda de no operar es un parámetro
  más, con poca ganancia esperada (cerca de +0,02 de Sharpe).

## Límites

- La prueba de truncamiento cubre el cálculo de pesos. El motor del backtest se cubre con sus propias
  pruebas (`test_engine_no_future_leak`, `test_naive_same_bar_vs_next_open_diff`).
- Los costes al doble y al triple escalan todo el modelo de costes a la vez. No sustituyen medir el
  deslizamiento real, que todavía tiene pocas ejecuciones.
