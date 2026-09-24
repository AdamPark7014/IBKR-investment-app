### Fuentes de datos (qué provee IBKR y qué requiere externos)

Objetivo: no inventar datos. Toda métrica se registra con fuente, timestamp (UTC) y metodología. Esta tabla resume la cobertura para la fase 1 y planificación:

Qué provee IBKR (API oficial, vía IB Gateway/TWS):
- Datos de mercado:
  - Tiempo real nivel 1 (bid/ask/last/size) y suscripciones de mercado según bolsas. Requiere paquetes de datos de mercado (coste/licencia por bolsa/mercado).
  - Barras históricas (reqHistoricalData) con distintos `barSize`/`duration`. Límites de frecuencia y granularidad según suscripción.
  - Profundidad de mercado (MarketDepth) si la suscripción lo permite.
  - Corporate actions (splits/dividendos) reflejados en históricos; dividendos/datos corporativos accesibles de forma limitada.
- Cuenta/Posiciones/PnL/Órdenes:
  - `managedAccounts`, `accountValues`, `positions`, `executions`, `orderStatus`, PnL en vivo, estado de conexión/error.
- Fundamentos (Reuters/Refinitiv):
  - `reqFundamentalData` (p. ej. `ReportsFinStatements`, `ReportsOwnership`, `Snapshot`), sujeto a suscripciones de datos fundamentales (de pago). Licencia restringe redistribución.
- Noticias:
  - `reqNewsProviders`, `reqHistoricalNews`, `reqNewsArticle` (disponibilidad según proveedor y suscripción: Dow Jones, Briefing, etc.).
- Scanners:
  - `reqScannerSubscription` para universos dinámicos/criterios (requiere mercado y licencias).

Limitaciones/costos/licencias:
- La mayoría de flujos en tiempo real y fundamentales requieren suscripciones de pago. Revise su cuenta IBKR para paquetes aplicables por región/mercado. No se redistribuye contenido protegido.
- Límites de tasa y tamaño de ventana en históricos.
- Zona horaria: normalizar a UTC en ingestión. Campos de corporate actions varían por activo/mercado.

Fuentes externas (planeadas y opcionales por fase; detrás de interfaces):
- Precios para backtesting (gratuitos): `yfinance` (Yahoo Finance) — sólo para investigación/backtest, nunca para ejecución.
- Macro:
  - FRED (Federal Reserve) para tasas, inflación, curvas (`https://fred.stlouisfed.org/`).
  - BEA/BLS para PIB/empleo (EE. UU.).
- Fundamentos/SEC:
  - EDGAR (SEC 10-K/10-Q) para estados financieros crudos (`https://www.sec.gov/`), con límites de uso.
  - APIs comerciales (p. ej., Refinitiv, FactSet, Bloomberg) no incluidas; se exponen interfaces para integrar si se cuenta con licencia.
- Sentimiento/Noticias:
  - Proveedores comerciales (RavenPack, Bloomberg, Dow Jones) o ingesta de RSS/News APIs con límites/licencias.
- VIX y amplitud:
  - VIX desde IBKR (requiere suscripción) o como proxy para investigación con Yahoo (`^VIX`).
  - Amplitud (porcentaje de universo sobre MA200) a partir de la propia canasta configurada.

Metodología y linaje:
- Cada dataset se envuelve con metadatos: `source`, `source_url`, `fetched_at_utc`, `methodology`, `parameters`, `license`, `notes`.
- Validaciones: índices cronológicos estrictos, sin duplicados, NaNs controlados/etiquetados, timezone a UTC, auditoría de transformaciones.

Decisiones de diseño (fase 1):
- Live/paper market data: IBKR (cuando esté disponible localmente).
- Backtesting: `yfinance` como fuente gratuita; IBKR no es accesible desde este VM.
- Fundamentos/macro: se dejan interfaces y stubs; no se materializa sin credenciales/licencias del propietario.

Referencias:
- Documentación oficial IBKR API (TWS): [Interactive Brokers API](https://interactivebrokers.github.io/tws-api/)
- Fundamentos IBKR (Refinitiv): ver secciones de `reqFundamentalData` en la doc oficial.
- Noticias IBKR: `reqNewsProviders`, `reqHistoricalNews`.

