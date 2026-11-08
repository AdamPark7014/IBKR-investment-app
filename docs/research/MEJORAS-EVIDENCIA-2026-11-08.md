# Mejoras con evidencia (2026-11-08)

Pregunta: ¿qué cambios suben de verdad la **rentabilidad neta ajustada por riesgo** de una persona que opera
ETF una vez al día con IBKR? "Neta" significa después de comisiones, spread e impuestos de operar; "ajustada por
riesgo" significa por cada unidad de volatilidad o de caída que se soporta.

## Lo primero, sin adornos

- **Nadie gana en cada operación.** Los mejores fondos sistemáticos aciertan la dirección algo más de la mitad de
  las veces. Su ventaja viene de ganar más cuando aciertan que lo que pierden cuando fallan, repetido durante años.
- **La ganancia realista "por operación" está en el coste, no en predecir mejor.** Cada punto básico (pb, 0,01 %)
  de spread o comisión que no se paga es rentabilidad segura. Una "señal más lista" sin validar es casi siempre
  sobreajuste: funciona en el pasado y falla con dinero real.
- **Nada de esto está medido todavía con datos reales.** Ni la nube ni el PC llegan a Yahoo/Tiingo. Todo lo de
  abajo está implementado y probado con datos sintéticos; la validación de verdad espera el token de Tiingo.

## Ranking (impacto esperado × solidez de la evidencia)

| # | Cambio | Estado | Evidencia | Impacto esperado |
|---|---|---|---|---|
| 1 | **Ejecutar 30 min después de la apertura** | Hecho (`EXECUTION__MIN_MINUTES_AFTER_OPEN=30`, tarea a las 10:05) | Fuerte: el spread intradía tiene forma de U, más ancho en la apertura (literatura de microestructura; también lo dicen los emisores de ETF) | Varios pb menos por orden, seguro |
| 2 | **Órdenes límite al punto medio, ventas antes que compras** | Hecho (rondas anteriores) | Fuerte: en ETF líquidos el límite al medio se llena casi siempre | Ahorra medio spread por orden |
| 3 | **Buffer de no operar** (no tocar posiciones que apenas se movieron) | Hecho (pysystemtrade, `buffering`) | Fuerte (Carver, pysystemtrade): reduce mucho la rotación con poca pérdida de señal | Menos coste anual |
| 4 | **Barrido de efectivo a BIL** | Hecho | Fuerte y mecánica: el efectivo ocioso cobra el tipo de las letras del Tesoro | ≈ tipo de corto plazo sobre la parte sin invertir |
| 5 | **Núcleo + tendencia** (50 % posición larga constante, 50 % reglas de tendencia) | Candidato añadido a la investigación, no en producción | Media: suaviza el coste de oportunidad de la tendencia pura en mercados alcistas; en sintéticos nunca fue el peor | Mejor Sharpe esperado que tendencia pura; hay que probarlo |
| 6 | **Universo más amplio** (`config/universe-16etf.json`) | Archivo opcional, no por defecto | Fuerte en general (más mercados poco correlacionados = más diversificación), pero depende de qué ETF | Mayor Sharpe si pasa la compuerta |
| 7 | **Carry y valor** (otras familias de señales) | No implementado | Fuerte en la literatura, pero necesita datos que no tenemos (curvas, rendimientos) | Pendiente de datos |

Términos:

- **Spread:** la diferencia entre el precio de compra y el de venta.
- **Tendencia:** comprar lo que viene subiendo y reducir lo que viene bajando.
- **Sharpe:** rentabilidad extra dividida por la volatilidad.
- **Compuerta de investigación:** prueba estadística que una estrategia debe pasar antes de llegar a producción. Pide DSR ≥ 0,95, t ≥ 3 y ≥ 252 observaciones.

## Lo que NO se hizo, y por qué

- **Apalancamiento para alcanzar el 10 % de volatilidad.** Multiplica también las caídas, y para una persona el
  riesgo de ruina importa más que el Sharpe.
- **Más reglas o parámetros "optimizados".** Cada prueba extra sube la probabilidad de un falso positivo. La
  compuerta ya cuenta todos los intentos.
- **IA decidiendo órdenes.** Claude revisa código e incidentes, pero nunca toca órdenes.

## Qué falta para medir

1. Token gratis de Tiingo en `.env`: `DATA__TIINGO_TOKEN=...`
2. `ibtrader research-portfolio --profile full` compara 60/40, All Weather, paridad de riesgo sin timing,
   núcleo + tendencia y el sistema completo con compuertas estrictas.
3. Si algo pasa la compuerta: seis meses en modo sombra/paper (`scorecard`) antes de dinero real.
