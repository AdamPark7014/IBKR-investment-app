# Qué le falta al sistema para ser profesional (2026-11-22)

Pedido de Adam: «aún le falta muchísimo; ve qué más le puede faltar a todo el sistema, algo mucho más
profesional». Este documento revisa el sistema de punta a punta y ordena lo que falta por impacto.

## Resumen

1. **La parte que decide qué comprar ya está a nivel profesional para lo que opera.** Tres pruebas
   honestas (2008 dentro, 26 ETF, momentum relativo) no le ganaron. Con 10 ETF, solo compras y sin
   apalancamiento, el techo es un Sharpe cercano a 0,6. Seguir afinando la fórmula no lo sube.
2. **Lo que no es profesional es la operación.** El sistema ejecutó 2 de 9 sesiones y el 87 % del
   capital simulado sigue sin invertir. Un fondo no falla por su fórmula; falla por esto.
3. **Hoy se programó la pieza que más ataca ese problema: el vigía.** Recupera el plan o la ejecución
   cuando la laptop estaba apagada a la hora exacta. Falta instalarlo en el PC.

## Términos

- **Sharpe:** retorno por encima de las letras del Tesoro dividido por la volatilidad.
- **Conciliación:** comparar lo que el sistema cree que tiene con lo que el bróker dice que tiene.
- **Gateway:** el programa de IBKR que tiene que estar abierto para poder enviar órdenes.
- **Vigía:** tarea que corre cada 15 minutos y revisa si falta algo de la corrida del día.
- **Carry:** preferir lo que paga más cupón o dividendo por tenerlo.

## Revisión por capa

Estado: **bien** (a nivel profesional para este tamaño), **parcial** o **falta**.

| Capa | Estado | Qué tiene | Qué falta |
|---|---|---|---|
| Datos | Bien | Tiingo con contraste contra Yahoo, control de frescura, cada dato guardado con la fecha en que se conoció | Dividendos por ETF (para carry). Datos en vivo: paper usa precios con 15 minutos de retraso |
| Señal | Bien | Tendencia a tres velocidades y momentum, núcleo pasivo, más de 100 pruebas registradas | Carry, única familia sin probar |
| Cartera | Parcial | Riesgo igual por caja, volatilidad objetivo, banda para no operar de más | Tope por clase de activo (hoy solo hay tope de 40 % por ETF) |
| Riesgo | Bien | Interruptor de emergencia, límite de caída de 20 %, control previo a cada orden, sin apalancamiento | Simulacro de cada fallo en paper (fase 4 del plan) |
| Ejecución | Bien | Órdenes que no se duplican, reintento con Adaptive, conciliación antes y después | Calibrar el modelo de costes con ejecuciones propias; todavía hay muy pocas |
| **Operación** | **Falta** | Tareas a hora fija, latido diario, comando `chequeo` | Que corra aunque la laptop se apague a ratos, que el Gateway se abra solo, avisos al teléfono, respaldo del estado |
| Seguimiento | Parcial | Tablero de 9 métricas (`scorecard`), registro de deslizamiento | Comparar cada mes lo que paper hizo contra lo que el backtest esperaba |

## Qué se programó hoy: el vigía

**El problema.** Las tareas corren a una hora exacta (plan 18:00, ejecución 9:05, hora de Puebla). Si
la laptop está apagada o dormida en ese minuto, la corrida se pierde y no se recupera.

**La solución.** `ibtrader vigia` corre cada 15 minutos y pregunta qué falta:

- Si no hay plan de la última sesión cerrada, lo corre. Sirve también en fin de semana.
- Si hay órdenes pendientes y el mercado está abierto, las ejecuta, aunque ya no sean las 9:05.
- Si el Gateway está cerrado, no intenta nada y avisa una sola vez ese día.
- Deja de intentar 45 minutos antes del cierre y tras 4 intentos fallidos.

No decide nada de inversión. Llama a las mismas corridas de siempre, con todos sus controles. No toca
la configuración congelada. Se instala con `scripts/schedule-vigia.ps1 -Action Register`, que
desactiva las dos tareas de hora fija, y se quita con `-Action Unregister`, que las reactiva.

**Lo que no resuelve.** Si la laptop pasa apagada todo el horario de bolsa (8:30 a 15:00 de Puebla), no
hay nada que recuperar. Tampoco abre el Gateway ni hace la verificación en dos pasos de IBKR.

## Lo que falta, por orden de impacto

| # | Qué | Por qué importa | Quién | Esfuerzo |
|---|---|---|---|---|
| 1 | Instalar el vigía en el PC | Pasa de «se pierde el día» a «se recupera cuando enciendes» | Claude, con tu sí | 10 minutos |
| 2 | Avisos al teléfono (Telegram) | Hoy las alertas se escriben en un archivo que nadie lee | Tú creas el bot (5 minutos); Claude lo conecta | Bajo |
| 3 | Gateway que se abra solo (IBC) | Sin Gateway no hay órdenes. Guarda tu usuario y contraseña de IBKR en un archivo local: es tu decisión | Tú decides | Medio |
| 4 | Equipo siempre encendido | Una mini PC usada (unos 3 000 MXN) o un servidor en la nube quita la dependencia de la laptop | Tú decides | Medio |
| 5 | Respaldo diario de `data/` | Si se daña el disco se pierde el libro, la curva y el historial de órdenes | Claude | Bajo |
| 6 | Comparación mensual paper contra backtest | Es la única forma de saber si el backtest dice la verdad | Claude | Medio |
| 7 | Tope por clase de activo | Evita que una sola clase concentre la cartera. Cambia la configuración: requiere tu sí | Claude, con tu sí | Bajo |
| 8 | Simulacros de fallo en paper | Probar una vez cada fallo (Gateway caído, orden a medias, dato malo) antes de dinero real | Claude y tú | Medio |
| 9 | Probar carry | Última familia de señal pendiente. Expectativa: mejora pequeña o nula | Claude | Medio |
| 10 | Datos en vivo y comisiones Tiered | Solo antes de dinero real | Tú | Bajo |

## Lo que no vale la pena

- **Afinar parámetros de la señal.** Ya se probó y es ruido.
- **Más ETF.** Probado: se mueven con los que ya hay.
- **Aprendizaje automático.** Con una sola familia de señal no hay nada que combinar.
- **Operar dentro del día.** Más coste y la señal rápida no predice.
- **Apalancamiento.** Medido: el interés se come la ganancia.

## Lo que de verdad nos separa de un fondo grande

Poder vender en corto y operar futuros de muchos países. Eso da apuestas independientes de verdad y es
lo que sube el Sharpe de 0,6 hacia 1,0. Pero es otro nivel de riesgo: con futuros se puede perder más
de lo invertido, y los micro futuros exigen una cuenta con margen y capital mayor. No lo recomiendo
ahora. Tiene sentido volver a mirarlo después de 6 meses de paper con operación limpia.

## Actualización del 2026-11-22: qué quedó hecho

| # | Qué | Estado |
|---|---|---|
| 1 | Vigía | Instalado en la laptop. Cada 15 minutos; sustituye a las tareas de hora fija |
| 2 | Avisos al teléfono | Código listo: resumen de cada corrida y `ibtrader probar-aviso`. Falta que Adam cree el bot |
| 3 | Gateway automático (IBC) | Sin hacer: necesita el sí explícito de Adam para guardar su contraseña |
| 5 | Respaldo diario | Hecho. En la laptop, por decisión de Adam |
| 6 | Paper contra el modelo | Hecho: `ibtrader seguimiento` |
| 7 | Tope por clase de activo | Programado y medido, **apagado**. Ver abajo |
| 8 | Modos de fallo | Lista con la prueba de cada uno en [`docs/MODOS-DE-FALLO.md`](../MODOS-DE-FALLO.md). Falta el simulacro con el Gateway real |
| 9 | Carry | Probado y descartado |

### Tope por clase de activo: medido

Sin tope, la cartera llegó a tener 83 % en acciones y 82 % en bonos en algún momento de 2004 a 2026.
Con tope de 60 % en acciones, 70 % en bonos y 40 % en activos reales (lo que sobra va a letras):

| Estrategia | CAGR | Sharpe | Caída máx. | 2008 | 2022 |
|---|---|---|---|---|---|
| Paper | 5,61 % | 0,60 | −10,9 % | −1,4 % | −10,8 % |
| Paper con tope por clase | 5,64 % | 0,61 | −11,0 % | −1,3 % | −10,8 % |

Diferencia de Sharpe +0,01 (−0,01 a +0,03): indistinguible. **No costó nada y tampoco protegió**, porque
en las crisis de esta historia la cartera no estaba concentrada. Es un seguro contra una concentración
que todavía no ha hecho daño. Activarlo cambia la configuración congelada (`STRATEGY__PARAMS`,
`group_caps`) y requiere el sí de Adam.
