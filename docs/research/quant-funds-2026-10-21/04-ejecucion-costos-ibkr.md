# Anexo 4 — Ejecución, costos de transacción e Interactive Brokers

Reporte del agente de investigación (21-10-2026). 20+ búsquedas y ~25 fuentes completas (páginas de IBKR bajadas con curl; PDF académicos con PyMuPDF). Fecha de lectura de todo lo de IBKR: 2026-10-21. [P]=primaria, [S]=secundaria.

## Hallazgos

### 1. Modelos de ejecución óptima

- **Almgren & Chriss (2000/2001)** [P]: impacto permanente lineal `g(v)=γv`, temporal `h(v)=ε·sgn(n)+η·v`; objetivo `min E(x)+λV(x)`; trayectoria óptima `x_k = X·sinh(κ(T−t_k))/sinh(κT)`, `κ̃² = λσ²/(η−γτ/2)`. Ejemplo del paper: ε=0.0625 $/acc (medio spread), η=2.5·10⁻⁶ (operar 1 % del ADV cuesta un spread), γ=2.5·10⁻⁷.
- **Almgren, Thum, Hauptmann, Li (Citigroup, 2005)** [P]: 29.509 órdenes grandes. `I = γ·σ·(X/V)·(Θ/V)^{1/4}`, `J = I/2 + sgn(X)·η·σ·|X/(V·T)|^{3/5}`; **γ=0.314, η=0.142, β=0.600** ("el modelo raíz cuadrada β=1/2 se rechaza al 95 %"). Comprar 10 % del ADV en large-cap: **costo realizado 18–43 bp**.
- **Tóth et al. 2011 (arXiv 1105.1694)** [P]: `Δ(Q) = Y·σ·√(Q/V)`, "la constante Y es de orden unidad"; exponente δ en 0.4–0.7 según estudios.
- **Bouchaud, Substack 1-dic-2024** [S]: exponente ≈1/2 estable entre acciones; válido "si la tasa de participación no es demasiado alta".
- **Zarinelli, Treccani, Farmer, Lillo 2015 (arXiv 1412.2152)** [P]: Ancerno 2007-09, 6.94 M metaórdenes; **Y≈0.15, δ≈0.47** (impacto en unidades de σ diaria); 1 % del ADV ≈ 0.017–0.021 σ_D; 10 % ≈ 0.05 σ_D.
- **Bucci et al. 2018 (arXiv 1811.05230)** [P]: 8 M metaórdenes; **cruce de impacto lineal a raíz cuadrada en participación η*≈3.15·10⁻³**. Implicación: a escala individual (Q/V ≪ 10⁻³) la ley √ **sobreestima** el impacto.
- **Kyle 1985** [S]: impacto lineal y permanente `p = p₀ + λ·y`; 1/λ = profundidad.
- **Li, Chow, Pickard, Garg** (vía Quantpedia, 2019) [S]: índices FTSE RAFI: ≈**30 bp de impacto por cada 10 % del ADV** negociado colectivamente.

### 2. Cómo hacen TCA los fondos

- **Perold 1988** [S]: shortfall = retorno de la cartera "de papel" (precio de decisión) menos la real.
- **Frazzini, Israel, Moskowitz, *Trading Costs*** (AQR 1998-2011; SSRN 2018 extiende a 2016, $1.7 T) [P]: media **MI 12.18 bp, IS 13 bp**; mediana 7.98/10.34; ponderado por valor 18.65/20.20 bp; **vs VWAP sólo 3.7 bp**. Orden media 1.2 % del ADV. La variable con más poder es **√(fracción del ADV)**. Arrastre anual: UMD 3.51 %/año (rotación 127 %, 23 bp/trade); reversión de corto plazo 6.75 %/año.
- **IBKR, métricas julio 2026 (3-ago-2026)** [P vía Placera]: "costo total de ejecutar y liquidar acciones Reg-NMS para clientes IBKR Pro **≈4.0 bp** (vs VWAP diario) en julio; **2.5 bp** en 12 meses móviles"; trade medio $23.449. **Es el calibrador real del slippage all-in de un cliente IBKR.**
- Por qué HFT/Medallion ganan en ejecución: no hay cifra publicada; lo observable es que IS institucional ≈13 bp vs 2.5–4 bp del cliente IBKR típico, y la diferencia se explica por tamaño, no por tecnología. **Virtu/Abel Noser: sin cifras públicas.**

### 3. IBKR para un sistemático individual (2026-10-21, P)

- **Comisiones US acciones/ETF**: **Fixed USD 0.005/acc, mín. 1.00/orden, máx. 1 % del valor**. **Tiered**: ≤300k acc/mes 0.0035; 300k–3M 0.0020; …; **mín. 0.35**; + bolsa + clearing 0.00020/acc + pass-through (NYSE comisión×0.000175; FINRA comisión×0.00056). Regulatorios: **SEC 0.0000206 × ventas** (desde 4-abr-2026); **FINRA TAF $0.00** (pausa oct–dic 2026; tasa normal $0.000195/acc, máx. $9.79; vuelve 1-ene-2027); CAT 0.000003/acc. "Las órdenes API con ruteo directo no pueden usar Tiered; las SmartRouted sí". IBKR Lite $0 sólo residentes EE. UU.
- **Datos de mercado**: gratis streaming **no consolidado** Cboe One + IEX (no es NBBO); 100 snapshots gratis/mes, luego $0.01/consulta; **US Securities Snapshot and Futures Value Bundle USD 10/mes, exento con USD 30 de comisiones**; para NBBO streaming: Network A/B/C o bundle + Add-On (precio no extraído; foros dicen $4.50).
- **Algos vía API**: `algoStrategy` = **AD**, **Adaptive** (`adaptivePriority`), **ArrivalPx**, **BalanceImpactRisk**, **ClosePx**, **DarkIce**, **MinImpact**, **PctVol**, **Twap**, **Vwap**. **"Los IB ALGO sólo operan en horario regular; outsideRth=true se rechaza"**.
- **Límites TWS API**: **50 requests/s** (= líneas de datos/2; 100 líneas por defecto); con rechazo, error 100 y **a la 3.ª violación se termina la sesión**. Histórico: barras de 1 s máx. 2000 S por request; resto 86400 S/365 D/52 W/12 M/68 Y. **La regla "60 requests/10 min" NO está en la documentación oficial actual.**
- **Read-Only API**: hay que **desactivar "Read-Only API"** y activar "ActiveX and Socket Clients"; por defecto está activo y las órdenes simplemente no llegan. **Paper** (30-ene-2026): "fills simulados desde el tope del libro, sin libro profundo"; **no soporta VWAP, Auction, RFQ, Pegged to Market**; puertos 7497 paper/7496 live.
- **ib_async**: PyPI **2.1.0 el 2025-12-08** (Python ≥3.10); GitHub "Latest" 2.0.1; último commit 2026-10-15; **102 issues abiertos**; autor de ib_insync (Ewald de Wit) falleció 2024-03-11; mantenedor mattsta. IBC 3.24.2 (2026-08-21).

### 4. Costo real de rebalancear 10 ETFs al mes (cálculo del agente con parámetros citados)

Supuesto: cartera $50k, 10 órdenes/mes de ~$1.000, rotación 20 %/mes.
- Comisión Fixed: 10×0.005=$0.05 → **mínimo $1.00 = 10 bp** por orden (el mínimo domina hasta órdenes de $20k). Tiered: ≈$0.38–0.40 (≈4 bp).
- Spread: SPY 30-day median **0.00 %** (SSGA, 20-oct-2026), IVV **0.01 %** [P]; etf.com: SPY 0.3–0.4 bp, QQQ 0.7, IWM 0.9; **mediana del universo ETF 20 bp** [S]. Medio spread core: 0.5–2 bp; nicho: 5–10 bp.
- Impacto: $1.000 vs ADV SPY ~$30 B → ≈0.02 bp; $10k en un ETF de $50 M/día → 0.7–1.4 bp. **Despreciable.**
- Regulatorio: SEC 0.2 bp sobre ventas; TAF ~0.02 bp.
- Total: **≈12 bp por orden con Fixed (~$12/mes) → 0.29 %/año**; con órdenes de $5k: ≈4 bp. Compara con el 2.5–4 bp all-in que IBKR reporta.
- **Frecuencia que mata**: costo anual = c × rotación × n. Diario con 5 % rotación: ≈ **1.5 %/año**; semanal 10 %: 0.62 %; mensual 20 %: 0.29 %. SigTech/Quantpedia (2022) [S]: GTAA diario con "low single-digit bps" por trade pierde **hasta 6.2 %/año**; con umbral de rebalanceo la brecha cae a 0.5 %/año. Frazzini: reversión de corto plazo pierde 6.75 %/año.

### 5. Reglas y restricciones

- **PDT**: **FINRA Regulatory Notice 26-10 (20-abr-2026)** [P]: SEC aprobó 14-abr-2026; **efectivo 4-jun-2026**; implementación hasta **20-oct-2027**; **elimina el mínimo de $25.000 y el conteo de day trades**, sustituidos por "intraday margin standards". Cuándo migra IBKR: no verificado.
- **Reg T**: 50 % inicial / 25 % mantenimiento [S]. **Portfolio Margin**: $110.000 (KB) vs $100.000 (calculadora) [snippets].
- **T+1**: compliance 28-may-2024 [P]. Overnight IBKR 8:00 pm–3:50 am ET.
- **México**: W-8BEN obligatorio [P]: válido el año de firma + 3 años; sin W-8 retención **30 %**. **IRS Tax Treaty Table 1 (may-2023)** [P]: México → dividendos **10 %**, intereses 15 %. Finantres.mx [S]: la retención US no agota el ISR mexicano; posible 10 % adicional de la LISR; acreditamiento. **Entidad que atiende a México: no encontrada en fuente primaria.**

### 6. Ángulo contrario

- Quejas documentadas [S salvo GitHub]: reinicio diario del Gateway, re-login semanal con 2FA, gateways que dejan de procesar requests tras el reinicio; soluciones: IBC con auto-restart, Docker + healthcheck. **Issues abiertos de ib_async** [P]: #169 conexión cae tras conectar; #207 `disconnectedEvent` dispara dos veces; #216 requests concurrentes huérfanos; #220 datos NaN tras horas; **#240 (15-oct-2026) orden ligada a clientId muerto, incancelable, se llena horas después**.
- **Alpaca**: Trading API **200 req/min**; datos Free (sólo IEX, 15 min de retraso) vs **Algo Trader Plus $99/mes**; sólo acciones US y cripto.
- **Tradier**: 120/min, **60/min trading**; Lite $0/mes con **$0.35/trade**, Pro $10/mes $0.

## Contradicciones y huecos

1. **Exponente del impacto**: Almgren 2005 rechaza 1/2 (β=0.6); Tóth/Bouchaud ≈0.5; Zarinelli 0.47 pero el log ajusta mejor; Bucci: lineal por debajo de 3·10⁻³. **Y**: "orden 1" (Tóth) vs 0.15 (Zarinelli).
2. **Pacing histórico IBKR**: la regla 60/10 min sólo sobrevive en terceros.
3. **ib_async**: PyPI 2.1.0 vs GitHub Releases 2.0.1.
4. **Tope Tiered**: "1 % of Trade Value" y "capped at 0.5 %" en la misma página.
5. **Portfolio Margin**: $110k vs $100k; PDT eliminada a nivel FINRA sin fecha de IBKR.
6. Huecos: entidad IBKR para México; cifras de Virtu/Abel Noser; precio del Add-On Streaming Bundle; tabla de fees por bolsa.

## Modelo de costos recomendado para ibtrader (paper-first, ib_async 2.1)

Por orden, en USD, `notional = shares × price`:

```
commission_fixed  = min(max(1.00, 0.005*shares), 0.01*notional)          # IBKR Fixed, 2026-10-21
commission_tiered = max(0.35, 0.0035*shares) + 0.0002*shares              # + fee de bolsa (asumir 0.0030/acc al remover liquidez; NO verificado)
                    + commission*(0.000175+0.00056)                       # pass-through NYSE/FINRA
reg_fees (solo ventas) = 0.0000206*notional + 0.000195*shares (0 hasta 2026-12-31) + 0.000003*shares
half_spread       = 0.5 * spread_pct * notional   # spread_pct por ETF: 30-day median de la gestora; defaults: core 0.02 %, mid 0.05 %, nicho 0.20 %
                    # market/Adaptive urgente: 1.0×; limit a mid con paciencia: 0.5× (y modelar no-fill)
impact            = Y * sigma_daily * sqrt(shares/ADV_shares) * notional  # Y = 0.5 (conservador), exponente 0.5
                    # alternativa Almgren-2005: J = I/2 + 0.142*σ*|X/(V·T)|^0.6, I = 0.314*σ*(X/V)*(Θ/V)^0.25
                    # Bucci: si shares/ADV < 1e-3 el impacto real es lineal y menor; dejar la √ como cota superior
```

Reglas de sanidad: (a) el costo all-in medio por orden del backtest **no debe ser menor que 2.5–4 bp** (IBKR, jul-2026); si lo es, el modelo miente. (b) Reportar **arrastre anual = Σ costos / NAV** y **turnover**; con Fixed y órdenes <$5k el mínimo de $1 es el término dominante. (c) Simular rebalanceo por **umbral** (6.2 % → 0.5 %/año) y comparar mensual vs semanal. (d) En paper no usar `Vwap`/Pegged; el slippage de paper subestima el real. (e) Medir IS vs precio de decisión (Perold) y vs VWAP, como Frazzini. (f) Ventas: SEC 0.2 bp; TAF vuelve en 2027.

## Fuentes

- (P) Almgren & Chriss 2000 — https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf
- (P) Almgren, Thum, Hauptmann, Li 2005 — https://www.cis.upenn.edu/~mkearns/finread/costestim.pdf
- (P) Tóth et al., arXiv 1105.1694 — https://arxiv.org/pdf/1105.1694
- (P) Zarinelli et al., arXiv 1412.2152 — https://ar5iv.labs.arxiv.org/html/1412.2152
- (P) Bucci et al., arXiv 1811.05230 — https://arxiv.org/pdf/1811.05230
- (S) Bouchaud, 1-dic-2024 — https://bouchaud.substack.com/p/the-square-root-law-of-market-impact
- (P) Frazzini, Israel, Moskowitz, *Trading Costs* — https://conference.nber.org/conf_papers/f68262/f68262.pdf · https://papers.ssrn.com/abstract=3229719
- (S) Kyle 1985 — https://www.quantt.co.uk/resources/kyle-model-and-kyles-lambda
- (S) Perold / IS — https://quantitativebrokers.com/blog/a-brief-history-of-implementation-shortfall
- (S) Quantpedia, *The Price of Transaction Costs* (2022) — https://quantpedia.com/the-price-of-transaction-costs/ · *Transaction Costs of Factor Strategies* (2019) — https://quantpedia.com/transaction-costs-of-factor-strategies/
- (P) IBKR comisiones — https://www.interactivebrokers.com/en/pricing/commissions-stocks.php
- (P) IBKR datos de mercado — https://www.interactivebrokers.com/en/pricing/research-news-marketdata.php
- (P) IBKR TWS API pacing — https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction.md
- (P) IBKR historical bars — https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars.md · TWS settings — https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/introduction.md
- (P) IBKR algos API — https://www.interactivebrokers.com/docs/general/order-types/algorithmic-orders/introduction.md
- (P) IBKR paper trading (30-ene-2026) — https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm
- (P) IBKR fiscalidad no-US — https://www.interactivebrokers.com/en/accounts/taxNonUS.php
- (P) IBKR métricas julio 2026 — https://www.placera.se/pressmeddelanden/interactive-brokers-group-a-interactive-brokers-group-reports-brokerage-metrics-and-other-financial-information-for-july-2026-includes-reg-nms-execution-statistics-20260803
- (P) ib_async — https://pypi.org/pypi/ib_async/json · https://github.com/ib-api-reloaded/ib_async · (P) IBC — https://github.com/IbcAlpha/IBC/releases
- (P) FINRA RN 26-10 — https://www.finra.org/rules-guidance/notices/26-10 · SR-2026-021 (TAF) — https://www.finra.org/sites/default/files/2026-09/SR-FINRA-2026-021.pdf · SEC fee rate FY2026 — https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2
- (P) SEC T+1 — https://www.sec.gov/newsroom/press-releases/2023-29
- (P) IRS Tax Treaty Table 1 — https://www.irs.gov/pub/irs-lbi/tax-treaty-table-1.pdf · (S) Finantres — https://finantres.mx/dividendos-interactive-brokers/
- (P) SSGA SPY — https://www.ssga.com/us/en/intermediary/etfs/spdr-sp-500-etf-trust-spy · iShares IVV — https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf · (S) etf.com spreads — https://www.etf.com/sections/news/etfs-highest-lowest-trading-spreads
- (P) Alpaca datos — https://alpaca.markets/data · órdenes — https://docs.alpaca.markets/docs/orders-at-alpaca
- (P) Tradier — https://docs.tradier.com/docs/rate-limiting · https://tradier.com/individuals/pricing
- (S) Quejas Gateway: https://www.elitetrader.com/et/threads/solution-to-keep-ib-gateway-alive.342798/ · https://support.quantrocket.com/t/ib-gateways-error-ib-gateway-should-be-running-but-is-not-accepting-connections/1787 · https://www.multicharts.com/trading-software/index.php/Interactive_Brokers_Pacing_Violation
