# Modelo de costos de ejecución de `ibtrader`

Código: `src/ibtrader/execution/costs.py` (funciones puras) · parámetros: `src/ibtrader/config.py`
(`CommissionConfig`, `RegFeesConfig`, `SlippageConfig`) · consumo: `backtest/engine.py`,
`backtest/metrics.py`, `backtest/report.py`, `research/report.py`, `research/cost_stress.py`.

Fuente de los valores por defecto: anexo 4 del playbook,
`docs/research/quant-funds-2026-10-21/04-ejecucion-costos-ibkr.md` (páginas de IBKR leídas el
**21-10-2026**; SEC/FINRA/CAT a esa fecha). Si IBKR cambia su tarifario, se actualiza `config.py` y
este archivo, no el motor.

Convención: `shares > 0` compra, `shares < 0` venta; `notional = |shares| × precio`. Todos los costos
se devuelven en USD, nunca negativos. Nada aquí tiene estado: misma entrada, misma salida.

## 1. Fórmulas

### Comisión (`commission`)

| Modelo | Fórmula |
|---|---|
| `fixed` (default) | `min( max(min_per_order, per_share·\|shares\|) + percent_of_value/100·notional , max_percent_of_value/100·notional )` |
| `tiered` | `max(tiered_min_per_order, tiered_per_share·\|shares\|) + (tiered_exchange_per_share + clearing_per_share)·\|shares\| + pass_through_pct_of_commission · comisión_broker` |

- `max_percent_of_value <= 0` desactiva el tope del 1 %.
- `percent_of_value` es un ad-valorem legado (0 por defecto).
- El pass-through (NYSE 0,0175 % + FINRA 0,056 %) se aplica solo sobre la comisión del broker, no sobre bolsa ni clearing.
- Se cobra sobre el **precio de llenado**, igual que antes.

### Cuotas regulatorias (`reg_fees`, solo ventas)

```
sec   = sec_fee_rate · notional                      # Section 31: 20,60 USD por millón (desde 04-04-2026)
taf   = 0                                            si fecha_operación <= finra_taf_paused_until
      = min(finra_taf_per_share·|shares|, finra_taf_max_per_order)   en otro caso
cat   = cat_per_share · |shares|
reg_fees = sec + taf + cat
```

La TAF está en pausa de oct a dic 2026 (`finra_taf_paused_until = "2026-12-31"`); vuelve el 01-01-2027
a 0,000195 USD/acción con tope 9,79 USD/orden. Las compras pagan 0.

### Medio spread (`half_spread`)

```
spread_bps(símbolo) = spread_bps_by_symbol.get(símbolo, spread_bps_default)
half_spread = half_spread_mult · 0,5 · spread_bps/1e4 · notional
```

`half_spread_mult = 1.0` cruza el spread (market / Adaptive urgente); `0.5` modela una limit paciente
a mid (sin modelar el no-fill).

### Impacto (`impact`)

```
impact = impact_y · sigma_daily · (|shares| / ADV_shares)^impact_exponent · notional
```

Ley raíz cuadrada (Tóth 2011, Bouchaud 2024, Zarinelli 2015): `impact_y = 0,5` conservador,
`impact_exponent = 0,5`. `sigma_daily` y `ADV_shares` salen de `rolling_adv_and_sigma(df, 20, 20)`:
media móvil del volumen y desviación de los retornos de cierre, **desplazadas una barra** (la barra que
se ejecuta no se mira). Si faltan (calentamiento, sin columna `volume`, ADV ≤ 0) el impacto es **0** y el
motor lo registra una vez por símbolo. Con participación > 100 % del ADV la raíz extrapola hacia arriba:
es una cota superior deliberada. Bucci 2018: por debajo de 0,3 % del ADV el impacto real es lineal y
menor; la raíz queda como cota superior.

### Precio de llenado en el backtest

| `slippage.model` | Llenado | `total_slippage` | `total_impact` |
|---|---|---|---|
| `spread_impact` (default) | `ref · (1 + lado · (half_spread_frac + impact_frac))` | medio spread en USD | impacto en USD |
| `bps` (legado) | `ref · (1 + lado · bps/1e4)` — **idéntico al motor anterior** | `\|shares\|·ref·bps/1e4` | 0 |

`ref` es la apertura del día de ejecución. La comisión y, en ventas, las cuotas regulatorias se restan del
efectivo y del P&L del trade. El tamaño de la orden se estima con `ref ± half_spread` (sin impacto, que
necesita la cantidad).

### Costo todo-incluido por orden (`OrderCost`)

```
total      = commission + reg_fees + half_spread + impact
notional   = |shares| · fill_price
bps_all_in = total / notional · 1e4
```

## 2. Parámetros por defecto (21-10-2026)

| Variable `.env` | Default | Fuente |
|---|---|---|
| `COMMISSION__MODEL` | `fixed` | IBKR Fixed (API con ruteo directo no puede usar Tiered) |
| `COMMISSION__PER_SHARE` | 0.005 | IBKR Fixed USD/acción |
| `COMMISSION__MIN_PER_ORDER` | 1.00 | mínimo por orden |
| `COMMISSION__MAX_PERCENT_OF_VALUE` | 1.0 | tope 1 % del valor |
| `COMMISSION__TIERED_PER_SHARE` / `TIERED_MIN_PER_ORDER` | 0.0035 / 0.35 | tramo ≤ 300k acc/mes |
| `COMMISSION__TIERED_EXCHANGE_PER_SHARE` | 0.0030 | **no verificado** (remover liquidez) |
| `COMMISSION__CLEARING_PER_SHARE` | 0.0002 | clearing |
| `COMMISSION__PASS_THROUGH_PCT_OF_COMMISSION` | 0.000735 | NYSE 0.000175 + FINRA 0.00056 |
| `COMMISSION__SANITY_MIN_ALL_IN_BPS` | 2.5 | IBKR Pro: 2,5 pb (12 m) – 4,0 pb (jul-2026) |
| `REG_FEES__SEC_FEE_RATE` | 0.0000206 | SEC desde 04-04-2026 |
| `REG_FEES__FINRA_TAF_PER_SHARE` / `FINRA_TAF_MAX_PER_ORDER` | 0.000195 / 9.79 | FINRA TAF |
| `REG_FEES__FINRA_TAF_PAUSED_UNTIL` | 2026-12-31 | SR-FINRA-2026-021 |
| `REG_FEES__CAT_PER_SHARE` | 0.000003 | CAT |
| `SLIPPAGE__MODEL` | `spread_impact` | `bps` reproduce el motor anterior |
| `SLIPPAGE__BPS` | 1.0 | solo con `model=bps` |
| `SLIPPAGE__SPREAD_BPS_DEFAULT` | 2.0 | ETF desconocido (mediana del universo ETF ≈ 20 pb; core 0–2) |
| `SLIPPAGE__SPREAD_BPS_BY_SYMBOL` | SPY 0.5, QQQ 0.7, IWM 0.9, IVV/VTI/TLT/GLD 1.0, … DBC/PDBC 5.0 | 30-day median SSGA/iShares/etf.com |
| `SLIPPAGE__HALF_SPREAD_MULT` | 1.0 | 1 = cruzar; 0.5 = limit a mid |
| `SLIPPAGE__IMPACT_Y` / `IMPACT_EXPONENT` | 0.5 / 0.5 | Tóth (Y de orden 1 → 0,5 conservador) |
| `SLIPPAGE__ADV_WINDOW_DAYS` / `SIGMA_WINDOW_DAYS` | 20 / 20 | ventanas móviles |

Cambiar por `.env` (pydantic-settings, delimitador `__`):

```ini
COMMISSION__MODEL=tiered
SLIPPAGE__HALF_SPREAD_MULT=0.5
SLIPPAGE__SPREAD_BPS_BY_SYMBOL={"SPY": 0.5, "VEA": 2.5}
REG_FEES__FINRA_TAF_PAUSED_UNTIL=
SLIPPAGE__MODEL=bps          # vuelve al motor legado (solo para comparar)
```

## 3. Reglas de sanidad

1. **Piso de 2,5–4 pb.** Si `avg_cost_bps_per_order` del backtest es menor que
   `COMMISSION__SANITY_MIN_ALL_IN_BPS` (2,5), el honest report marca `cost_model_suspicious=True` y lo
   explica en `cost_model_note`. IBKR publicó que sus clientes Pro pagaron ≈ 4,0 pb all-in en julio de
   2026 y 2,5 pb en 12 meses (trade medio 23.449 USD). Si el modelo sale más barato que la realidad, el
   modelo miente. Es diagnóstico: **no cambia `gate_passed` ni el veredicto**.
2. **Modelo `bps` legado = sospechoso siempre.** No distingue spread, impacto ni cuotas regulatorias.
3. **Arrastre anual y rotación se reportan siempre.** `cost_drag_annual_pct = Σ costos / equity inicial /
   años · 100` y `turnover = Σ notional / equity inicial`. Con Fixed y órdenes < 5.000 USD el mínimo de
   1 USD domina.
4. **La escalera de costos** (`research/cost_stress.py`) multiplica spread, impacto y comisión a la vez
   (1×/2×/3×); los topes, pass-through y cuotas regulatorias no se escalan porque son estatutarios.
5. El paper trading de IBKR llena desde el tope del libro sin profundidad: **subestima** el slippage real.
   Este modelo es el que manda en investigación.

## 4. Ejemplos numéricos (modelo por defecto, precio 100 USD, 21-10-2026)

| Orden | Compra | Venta | Promedio |
|---|---|---|---|
| SPY, 1.000 USD (10 acc) | comisión 1,00 + ½spread 0,025 = 1,025 USD = **10,25 pb** | + SEC 0,0206 + CAT 0,00003 = 1,046 USD = 10,46 pb | 10,35 pb |
| SPY, 5.000 USD (50 acc) | 1,00 + 0,125 = 1,125 USD = 2,25 pb | 1,228 USD = 2,46 pb | 2,35 pb |
| ETF desconocido (spread 2 pb), 5.000 USD | 1,00 + 0,50 = 1,50 USD = 3,00 pb | 1,603 USD = 3,21 pb | **3,10 pb** |
| SPY, 100.000 USD (1.000 acc) | 5,00 + 2,50 = 7,50 USD = 0,75 pb | + SEC 2,06 = 9,56 USD = 0,96 pb | 0,85 pb |

- El mínimo de 1 USD manda hasta ≈ 200 acciones (20.000 USD a 100 USD): por eso una orden de 1.000 USD
  cuesta ~10 pb y una de 5.000 USD ~2,5–3 pb (el anexo estima ~4 pb con spreads algo mayores).
- Impacto: 10.000 USD en un ETF con 50 M USD/día (100 acc vs ADV 500.000) y σ = 1 %:
  `0,5 · 0,01 · √(100/500.000) · 10.000 = 0,71 USD = 0,71 pb`. Para SPY (ADV ≈ 30 B USD) es ≈ 0,02 pb.
- Tiered, 1.000 acc a 100 USD: `max(0,35; 3,50) + (0,0030 + 0,0002)·1.000 + 3,50·0,000735 = 6,70 USD` (0,67 pb).
- Tope Fixed: 10 acc a 5 USD → `min(1,00; 1 % · 50) = 0,50 USD`.
- TAF: 1.000 acc vendidas el 21-10-2026 → 0; el 04-01-2027 → 0,195 USD (tope 9,79).
- **Frecuencia que mata:** costo anual ≈ c × rotación × n. Con 12 pb por orden y 5 % de rotación
  diaria: `0,0012 · 0,05 · 252 = 1,51 %/año`; semanal 10 %: 0,62 %; mensual 20 %: 0,29 %. Las órdenes
  de 100.000 USD del motor (0,85 pb) salen más baratas que la media de IBKR; por eso el reporte las marca.

## 5. Métricas que salen del backtest

`PerformanceStats` (artefacto JSON vía `stats_to_dict`, tabla en el HTML de `save_equity_report`, bloque
`<script id="ibtrader-stats">` con todos los campos):

| Campo | Significado |
|---|---|
| `total_commission` | comisiones IBKR |
| `total_reg_fees` | SEC + TAF + CAT (ventas) |
| `total_slippage` | medio spread pagado (o bps planos en modo legado) |
| `total_impact` | impacto raíz cuadrada |
| `total_costs` | suma de los cuatro |
| `n_orders`, `notional_traded` | llenados y notional ejecutado |
| `avg_cost_bps_per_order` | `total_costs / notional_traded · 1e4` |
| `cost_drag_annual_pct` | `total_costs / equity inicial / años · 100` |
| `turnover` | `notional_traded / equity inicial` |

`research/report.py` resume por suite: `cost_model_suspicious`, `cost_model_note`, `cost_summary`
(modelo, piso, pb observados o estimados, rotación máxima/mediana, arrastre máximo), `turnover`,
`cost_drag_annual_pct`. Cuando las filas de la suite no traen `avg_cost_bps_per_order`, el reporte tasa el
modelo configurado con una orden de referencia (`suite["typical_order_usd"]`, default 100.000 USD a
`suite["reference_price"]`, default 100 USD) y lo dice en `avg_cost_bps_source = "model_estimate"`.
