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
- Precios para backtesting: **Tiingo** (fuente de verdad desde 21-10-2026, ver sección abajo); `yfinance` y Stooq quedan como respaldo — sólo para investigación/backtest, nunca para ejecución.
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
- Backtesting: Tiingo (EOD ajustado + cierre crudo + metadatos de listado) cuando hay `DATA__TIINGO_TOKEN`; `yfinance`/Stooq como respaldo. IBKR no es accesible desde este VM.
- Fundamentos/macro: se dejan interfaces y stubs; no se materializa sin credenciales/licencias del propietario.

Referencias:
- Documentación oficial IBKR API (TWS): [Interactive Brokers API](https://interactivebrokers.github.io/tws-api/)
- Fundamentos IBKR (Refinitiv): ver secciones de `reqFundamentalData` en la doc oficial.
- Noticias IBKR: `reqNewsProviders`, `reqHistoricalNews`.

---

## Capa point-in-time (playbook fase 1, 21-10-2026)

Los fondos guardan cada dato con la fecha en que lo recibieron (ArcticDB en Man, Qlib PIT, la paridad research→producción de Jane Street) para poder reconstruir "qué sabíamos cuándo". Esta capa lo copia en pequeño: un proveedor serio con delistings, snapshots inmutables con hash, un universo que sabe cuándo nació cada instrumento y validadores que fallan en voz alta. Código: `src/ibtrader/data/{providers,service,vintage,universe,validators}.py`.

### Tiingo — fuente de verdad para precios EOD

- **Token**: variable de entorno `DATA__TIINGO_TOKEN` (o `tiingo_token` en `DataConfig`). Vacío = el proveedor **no se instancia** y queda un `WARNING tiingo_disabled`; la cadena sigue con los demás. Nunca se escribe el token en linaje, manifiesto ni logs.
- **Activar**: `DATA__PROVIDERS='["tiingo","yahoo","stooq"]'` (el orden es la prioridad de la cadena).
- **Tiers** (página oficial de precios, leída el 21-10-2026):
  - *Starter* (gratis): 500 símbolos únicos/mes, 50 peticiones/hora, 1.000/día; uso personal, no comercial.
  - *Power* ($30/mes): 30+ años de EOD, 110.341 símbolos, fundamentales 15+ años, límites mucho más altos.
  - *Commercial* ($50/mes): redistribución.
- **Endpoints usados**:
  - `GET https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate&endDate&format=json&token=…` → barras. Se mapean `adjOpen/adjHigh/adjLow/adjClose/adjVolume` a `open/high/low/close/volume` (serie **ajustada** por splits y dividendos); se conservan `close_raw` (cierre sin ajustar), `div_cash` y `split_factor`, y `adj_close` duplica `close` para el código que ya lo busca. Si el payload no trae campos `adj*`, se usan los crudos con un `WARNING tiingo_sin_ajustados`.
  - `GET https://api.tiingo.com/tiingo/daily/{ticker}` → `TiingoProvider.fetch_metadata(symbol)` devuelve `SymbolMetadata(start_date, end_date, name, exchange)`. `end_date` lejos de hoy = delistado o suspendido: es la base para rellenar `delisted_on` en el universo.
- **Comportamiento ante errores**: 429 → espera con backoff exponencial (2 s, 4 s, 8 s, o `Retry-After` si viene) y reintenta hasta 3 veces; después falla con "límite de tasa". 401/403 → `RuntimeError("token Tiingo inválido o ausente …")`. 404 → símbolo desconocido. Red caída → `error de red`. Payload vacío o con fechas duplicadas → error, nunca un DataFrame a medias.
- **Licencia**: datos para uso propio; el linaje registra `license="Tiingo TOS …"`. No se redistribuyen.

### Vintages inmutables y `manifest.json`

Cada carga exitosa (`load_universe_v2`) escribe, si `write_manifest=True` (por defecto):

```
<vintage_dir>/                          # DATA__VINTAGE_DIR, default ./data/vintages (ignorado por git)
  manifest.json
  vintage_date=2026-10-21/
    SPY_1d.parquet
    VEA_1d.parquet
```

`manifest.json`:

```json
{"schema_version": 1,
 "vintages": {"2026-10-21": {
    "created_at_utc": "...", "updated_at_utc": "...",
    "files": [{"symbol": "SPY", "bar_size": "1d", "path": "vintage_date=2026-10-21/SPY_1d.parquet",
               "sha256": "…", "rows": 1260, "first_bar": "2021-10-21", "last_bar": "2026-10-21",
               "provider": "tiingo"}],
    "dataset_hash": "sha256 de los sha256 ordenados"}}}
```

- **Para qué sirve**: un backtest de hoy se puede repetir dentro de un año con *exactamente* los mismos bytes aunque Tiingo o Yahoo hayan reajustado la historia. El `sha256` de cada símbolo viaja también en el sidecar de caché (`DataLineage.vintage_date / vintage_path / sha256`), así que un artefacto de experimento puede citar el vintage que usó.
- **Idempotencia**: si ya existe el archivo de ese día con el mismo SHA-256 no se reescribe. Si el contenido cambió el mismo día (p. ej. yfinance refrescó la barra parcial de hoy) se sobrescribe con `WARNING vintage_overwrite` y el hash anterior queda en `superseded`.
- **Recargar un snapshot**:

  ```python
  from ibtrader.data.vintage import list_vintages, load_vintage
  list_vintages("./data/vintages")                      # ['2026-10-20', '2026-10-21']
  data = load_vintage("./data/vintages", "2026-10-21")  # {'SPY': DataFrame, ...}
  ```

  `load_vintage` vuelve a calcular el SHA-256 de cada parquet y **falla con la lista completa de discrepancias** si alguno no coincide o falta; nunca devuelve un snapshot parcial.
- **Desactivar**: `DATA__WRITE_MANIFEST=false`. Si el vintage no se puede escribir (disco, permisos) la carga falla: si no podemos registrar lo que sabíamos, no fingimos que sí.
- **El proveedor `fixture` nunca entra al almacén** (`INFO vintage_skipped`): es dato sintético de CI y un `pytest` en la máquina de Adam no debe pisar ni hacerse pasar por el snapshot real del mismo día. Los tests que sí ejercitan vintages usan `DATA__VINTAGE_DIR` en `tmp_path`.

### Universo con ciclo de vida

`config/universe-10etf.json` describe el universo del playbook (SPY, VEA, VWO, IEF, TLT, TIP, GLD, PDBC, VNQ, BIL) con su caja de paridad de riesgo (`us_equity`, `developed_ex_us_equity`, `emerging_equity`, `treasuries_intermediate`, `treasuries_long`, `tips`, `gold`, `commodities`, `reit`, `cash`), `listed_from` (inception del emisor), `delisted_on` (`null` mientras siga listado), `spread_bps` (techo documentado: 2 pb, 5 pb para PDBC y TIP) y `notes`. Las entradas marcadas "verificar contra Tiingo metadata" se pusieron de memoria: contrastar con `fetch_metadata(symbol).start_date` antes de confiar.

- **Activar**: `DATA__UNIVERSE_FILE=config/universe-10etf.json` (JSON o YAML). `load_universe_v2` recorta cada símbolo con `clip_to_lifecycle`: fuera van las barras anteriores a `listed_from` y posteriores a `delisted_on`, y el log `universe_clip` dice cuántas quitó. El recorte se aplica también a la caché, y lo que se cachea/snapshotea es el DataFrame recortado.
- `UniverseSpec.active_symbols(as_of)` devuelve los instrumentos vivos en una fecha (ambos extremos inclusivos); los delistados **no se borran** de la historia: así el backtest no sufre sesgo de superviviente.
- Un símbolo pedido en `universe.symbols` que no está en el archivo se carga sin recorte con `WARNING universe_symbol_sin_ciclo_de_vida`.

### Validación ruidosa (auditoría P1-4)

`validate_pit(df, symbol, max_price_spike_pct=…, reject_future_bars=…)` devuelve **todas** las razones, no la primera: barras con fecha posterior a hoy (UTC), saltos de cierre día a día mayores que `DATA__MAX_PRICE_SPIKE_PCT` (25 % por defecto; 0 desactiva), duplicados, índice no monótono, NaN en OHLCV, columnas faltantes, cierres ≤ 0. `DATA__REJECT_FUTURE_BARS=false` permite barras futuras (solo para datos sintéticos).

Semántica en `load_universe_v2`:
- Caché: se sirve solo si tiene sidecar de linaje de una fuente cacheable (`yahoo`, `stooq`, `ibkr`, `tiingo`), no está vencida (`max_cache_age_days`) y pasa gate + PIT; si no, `WARNING cache_rechazada` con las razones y se vuelve a bajar.
- Proveedores: el que falla (excepción o datos rechazados) deja `WARNING provider_failed` / `provider_data_rechazada` y se prueba el siguiente.
- Si **todos** fallan para un símbolo: `ERROR symbol_excluido` con la lista completa de razones y el símbolo queda fuera del resultado; nada suyo se cachea ni entra al vintage.
- Si al final no queda ningún símbolo: `RuntimeError("Ningún símbolo cargó …")` con todas las razones. Nunca un dict vacío silencioso.
- Caché corrupta o sidecar ilegible: `ERROR cache_read_failed` / `lineage_read_failed` y se trata como fallo de caché (se vuelve a bajar), no como dato válido.

### Por qué yfinance (y Stooq) son respaldo y no fuente de verdad

- **Solo supervivientes**: Yahoo no sirve tickers delistados; un universo construido desde ahí tiene sesgo de superviviente por construcción.
- **Ajuste retroactivo**: cada dividendo o split reescribe toda la historia, así que el mismo `yf.download` da bytes distintos en fechas distintas y el `dataset_hash` de un experimento deja de ser reproducible. Los vintages mitigan esto, pero no arreglan el punto anterior.
- **Sin SLA ni contrato**: scraping de un endpoint no documentado que cambia de forma (MultiIndex, `auto_adjust` por defecto) entre versiones de `yfinance`.
- Stooq comparte las dos primeras limitaciones y además no entrega el cierre sin ajustar.

Se mantienen porque son gratuitos, no requieren token y sirven para arrancar un laboratorio en una máquina nueva; la cadena por defecto sigue siendo `["yahoo","stooq"]` hasta que haya token de Tiingo configurado.

