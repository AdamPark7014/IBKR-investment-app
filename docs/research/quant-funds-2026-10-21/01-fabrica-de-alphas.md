# Anexo 1 — Cómo producen señales los fondos gigantes (fábrica de alphas)

Reporte del agente de investigación (21-10-2026). 38 búsquedas, 27 lecturas completas. Varias fuentes primarias devolvieron 403 o certificado inválido (`hsgac.senate.gov`, `support.worldquantbrain.com`, `interactivebrokers.com`, `nber.org`); en esos casos se usa la cobertura secundaria más cercana y se marca.

## Hallazgos

### 1. WorldQuant: la fábrica de alphas

- **Qué es un alpha ahí**: una fórmula sobre campos de datos que produce un peso diario por acción dentro de un universo. "101 Formulaic Alphas" publica 101 fórmulas reales de precio-volumen: periodo medio de tenencia **0,6–6,4 días**, correlación media por pares **15,9 %**, retornos "fuertemente correlacionados con la volatilidad" y "sin dependencia significativa del turnover". No publica Sharpes. [arXiv 1601.00991, 5-ene-2016, Wilmott 84; **primaria**]
- **El estudio de 4.000 alphas reales** (Kakushadze y Tulchinsky): tenencia 0,7–19 días; los centavos por acción escalan como **C ~ 1/T** (T = turnover) y el retorno como **R ~ V^x, x ≈ 0,8–0,85**. Es la ley empírica que define el diseño: cuanto más rápido el alpha, menos gana por acción operada, así que solo sobrevive con costes de ejecución mínimos y escala. [arXiv 1509.08110, 2015-16, J. Investment Strategies 5(2); **primaria**]
- **Volumen con fecha**: ~**4 millones de alphas** en el repositorio "Alpha Factory" en abril de 2017; 125 investigadores PhD y 450 consultores pagados (WSJ 13-abr-2017, Bloomberg mar-2017, vía Wikipedia; **secundaria citando primarias**). Tulchinsky en 2018: 140 PhD, meta de "100 millones de alphas" y "miles de millones de simulaciones al mes" [Bloomberg/BQ 2018, fragmento; **primaria (entrevista)**]. En 2025: "millions and millions of alphas", 10.000 M$ gestionados para Millennium y >13.000 M$ externos; LLMs para descubrir alphas "en fase temprana" [Forbes AU, 16-may-2025; **primaria (perfil con citas)**].
- **BRAIN (crowdsourcing)**: lanzado 2-ago-2022 con >34.000 campos de datos [worldquant.com; **primaria**]. Hoy: 550.000+ usuarios, 16.000+ consultores, **400.000+ campos de datos de 12 regiones**; pago por mérito, "Grandmaster $8.000+/trimestre, Master $2.000+/trimestre" [worldquantbrain.com, 2026; **primaria**].
- **Umbrales de aceptación (no oficiales, concordantes entre terceros)**: Sharpe > 1,25; fitness ≥ 1,0; turnover entre 1 % y 70 %; Sharpe por sub-universo; peso máximo por acción 10 %; **autocorrelación < 0,7 con los alphas ya aceptados** (o Sharpe ≥10 % superior al alpha correlacionado) [repos GitHub QuantML-Research y PyPI brain-login-and-sim; **secundaria/terciaria**]. Un paper de agosto de 2026 que automatiza BRAIN con LLMs enumera los mismos checks [arXiv 2608.11250, 4-ago-2026; **primaria (académica, autoreportada)**].
- **Cómo combinan**: ninguna fuente primaria describe el combinador. Lo documentado es el filtro: cada alpha nuevo debe ser **poco correlacionado con el pool existente** y con turnover acotado; C ~ 1/T impone que los alphas rápidos solo aporten si el coste por acción es ínfimo.

### 2. Millennium y el modelo de pods

- **Regla de drawdown (WSJ, vía eFinancialCareers 5-dic-2025)**: un PM que pierde **5 % del capital asignado** ve su asignación "típicamente reducida a la mitad"; una pérdida **adicional de 2,5 %** "suele llevar al despido". [**secundaria citando WSJ**]
- Otras descripciones: de-risking a ~5 %, liquidación del libro y salida a **7,5–10 %**; límites típicos de pod: exposición neta ±10 %, 1–3 % del bruto por nombre, 5–15 % por industria, 5–10 % del ADV a 30 días; pods de 50–200 M$ brutos; el asignador central mueve capital hacia los flujos con mejor Sharpe y baja correlación [Quant Enthusiasts, 10-may-2026, sin fuentes citadas; **secundaria**].
- **Escala**: ~97.000 M$ AUM (Bloomberg, sep-2026); ~330 equipos (2024-25); JV con WorldQuant desde abr-2018 [Wikipedia + fuentes citadas; **secundaria**].
- **Por qué define el diseño**: el drawdown es un parámetro duro y ex ante, así que el tamaño de posición se calcula hacia atrás desde el 5 %; se paga solo el retorno idiosincrático (todo factor se cubre); eso empuja a estrategias de **alto Sharpe, baja volatilidad, neutralidad de factor y horizonte corto**.

### 3. Renaissance / Medallion

**Documentado por filings** (Subcomité del Senado, informe 21-jul-2014 y audiencia 22-jul-2014, vía Accounting Today; **primaria vía prensa**):
- Deutsche Bank y Barclays vendieron **199 "basket options"** desde 1999; **60 con plazo >1 año fueron a Medallion y generaron ~34.200 M$ de beneficio**.
- Una sola opción contenía **>129 millones de operaciones subyacentes en un año**; "muchas posiciones duraban minutos o segundos"; los bancos ejecutaban "en alrededor de un milisegundo".
- Apalancamiento: estructura de 10 % de efectivo del fondo y 90 % prestado por el banco (fragmento de hsgac.senate.gov).
- Peter Brown: "cuando se opera con apalancamiento, un solo error puede ser desastroso para la firma".
- Medallion: >9.000 M$ en 2014, casi exclusivo para empleados, >35 % anualizado en dos décadas.

**Documentado por Zuckerman (2019), vía dos reseñas**:
- 66,1 % bruto / 39,1 % neto anual 1988-2018; comisiones 5 % y 44 %; Simons devolvió capital externo porque el fondo no podía gestionar más de ~10.000 M$ [Ritholtz, Bloomberg Opinion, 28-oct-2019; **secundaria**].
- "Al combinar todas sus señales y requisitos de cartera en **un único modelo monolítico**, Renaissance podía probar y añadir señales nuevas" y ver si su ganancia superaba sus costes; acierto "aproximadamente 51 % de las operaciones"; "en 1997 más de la mitad de las señales eran no intuitivas" [Carlson vía Marcellus; **secundaria citando el libro**].

**Especulado o no verificado**: los múltiplos de apalancamiento que circulan (12,5x, 17x, 20x) no aparecen en ninguna fuente primaria leída; el número de señales nunca se ha publicado. "La ejecución como fuente de edge" solo tiene evidencia indirecta.

### 4. Two Sigma, D.E. Shaw, Jane Street, AQR, Man AHL

- **Two Sigma** (web oficial; **primaria**): cuatro etapas (datos → modelado → construcción de cartera → ejecución); "pronósticos independientes por instrumento" combinados en una "visión de consenso" ponderada contra costes y riesgo; 10.000+ fuentes de datos, 380+ PB, **48.000+ o 100.000+ simulaciones diarias** (la misma página da dos cifras), 250+ PhD. Un modelo nuevo se juzga por el valor que añade al "portfolio de modelos" (documento en Schroders; **secundaria**).
- **D.E. Shaw** (web oficial; **primaria**): "ineficiencias estadísticamente robustas" vía proceso científico; un Comité de Riesgo asigna capital; >115.000 M$ (1-sep-2026); 800+ ingenieros.
- **Jane Street, el caso distinto** (web + podcast; **primaria**): market maker en 200+ venues, ETFs primero; "el trading es una plataforma de experimentación de ML con feedback rápido"; OCaml. En *Signals and Threads* ep. 29 (2-sep-2026): guardan cada dato "con la hora en que lo recibimos" para "reconstruir qué sabíamos cuándo"; "es muy fácil colar información del futuro al pasado"; "los patrones se descubren y se compiten hasta desaparecer".
- **AQR** (*Craftsmanship Alpha*, 2017; **primaria**): "la captura hábil de primas de estilo puede constituir una forma de alpha por sí misma"; dos gestores del mismo factor obtienen resultados "significativamente distintos" por construcción, riesgo y ejecución.
- **Man AHL** (**primarias**): *Need for Speed* (4-ene-2023): cruces de medias exponenciales a 5 velocidades (4–24 semanas), 1995-2022, 50 futuros/FX, 25 % de riesgo por clase de activo; correlación 0,17 entre la más rápida y la más lenta; antes de costes el Sharpe sube al ir más lento; **después de costes (5.000 M$) el Sharpe de las rápidas cae materialmente**; los modelos MAC llevan ~30 años con la mayor asignación. Institutional Investor (2016): ML es "la mayor partida de gasto en investigación"; Ledford: "siempre corres el riesgo de sobreajustar".

### 5. Ángulo contrario

- **Factor zoo**: Harvey, Liu y Zhu (RFS 2016): 316 factores; exigir **t ≥ 3,0**; **33–50 % de los factores publicados probablemente falsos**. Contrapuntos: Jensen, Kelly y Pedersen (JF 2023): 153 factores en 93 países, "la mayoría replica"; Chen (arXiv 2206.15365, nov-2025): FDR ≤25 % en 8 de 9 estudios.
- **Decaimiento post-publicación**: McLean y Pontiff (JF 2016): 97 predictores; **−26 % fuera de muestra, −58 % tras publicación**; decaen más los de alto retorno en muestra y horizonte corto. Falck, Rej y Thesmar (QF 2022): 72 estrategias conservan **~50 %** fuera de muestra; sobreajuste y arbitraje "igualmente importantes".
- **Quant quake**: Khandani y Lo (2011; **primaria**): desapalancamiento del 1-ago-2007 y 6-ago-2007 arrancando en estrategias de valor/momentum apalancadas; origen probablemente exógeno. Acadian (abr-2026): la ansiedad por crowding es "excesiva", pero apalancamiento de hedge funds en máximos en 2025.
- **Capacidad intrínseca**: C ~ 1/T y la caída post-costes de las velocidades rápidas muestran que el decaimiento no es solo competencia: es aritmética de costes.

## Contradicciones y huecos

- Millennium: 5 % → mitad; +2,5 % → despido (WSJ) vs 7,5–10 % de liquidación (Substack). Mandato de WorldQuant: 7.000 M$ vs 10.000 M$.
- Two Sigma: 48.000 vs 100.000 simulaciones/día en la misma página.
- Medallion: 66,1 % vs 69 % bruto; apalancamiento sin fuente primaria.
- BRAIN: Sharpe 1,25 vs 1,58, turnover 70 vs 40; la doc oficial no se pudo leer.
- Factor zoo: HLZ (33–50 % falsos) vs JKP (la mayoría replica) vs Chen (FDR ≤ 9–25 %).
- Nadie publica cómo se construye el combinador de alphas.

## Replicable vs no replicable para un individuo

**Replicable con Python + IBKR**: la disciplina (hipótesis previa, datos point-in-time con hora de recepción, prueba fuera de muestra con t ≥ 3, control de turnover y costes antes de aceptar una señal, correlación < 0,7 contra lo que ya tienes, drawdown como parámetro ex ante); alphas transversales diarios con tenencia 2–20 días; seguimiento de tendencia con cruces de medias a 4–24 semanas y riesgo igualado por clase de activo (las velocidades lentas sobreviven a costes); participar en BRAIN.

**No replicable**: escala de búsqueda (millones de alphas, 400.000 campos); costes y latencia (C ~ 1/T condena a retail en alphas rápidos); apalancamiento tipo basket options; capital y organización (300 flujos de PnL); datos alternativos de pago.

## Fuentes

Primarias (P) / secundarias (S):
- (P) Kakushadze, 101 Formulaic Alphas, 2016: https://arxiv.org/abs/1601.00991
- (P) Kakushadze & Tulchinsky, Performance v. Turnover: 4,000 Alphas: https://arxiv.org/abs/1509.08110
- (P) WorldQuant, lanzamiento BRAIN, 2-ago-2022: https://www.worldquant.com/ideas/worldquant-launches-brain-platform-and-inaugural-global-alphathon-competition
- (P) BRAIN consultores (2026): https://worldquantbrain.com/
- (P) AgonAlpha, arXiv ago-2026: https://arxiv.org/abs/2608.11250
- (P, perfil con citas) Forbes AU, 16-may-2025: https://www.forbes.com.au/news/billionaires/how-a-soviet-refugee-became-a-hedge-fund-billionaire/
- (S) Wikipedia WorldQuant: https://en.wikipedia.org/wiki/WorldQuant
- (S) Umbrales BRAIN no oficiales: https://github.com/QuantML-Research/wq-alpha-research · https://pypi.org/project/brain-login-and-sim/
- (S, cita WSJ) eFinancialCareers, 5-dic-2025: https://www.efinancialcareers.com/news/pratik-madhvani-glen-scheinberg
- (S) Quant Enthusiasts, 10-may-2026: https://youngandcalculated.substack.com/p/risk-management-inside-a-pod-how
- (S) Wikipedia Millennium: https://en.wikipedia.org/wiki/Millennium_Management
- (P) Senado EE. UU., basket options 2014: https://www.hsgac.senate.gov/subcommittees/investigations/rep/subcommittee-finds-basket-options-misused-to-dodge-billions-in-taxes-and-bypass-federal-leverage-limits/
- (S) Accounting Today, 22-jul-2014: https://www.accountingtoday.com/news/renaissance-avoided-more-than-6-billion-tax-senators-say
- (S) Ritholtz/Bloomberg, 28-oct-2019: https://www.wealthmanagement.com/alternative-investments/jim-simons-built-the-best-hedge-fund-ever
- (S) Carlson vía Marcellus: https://marcellus.in/story/non-intuitive-lessons-from-the-man-who-solved-the-market/
- (P) Two Sigma: https://www.twosigma.com/businesses/investment-management
- (P) D.E. Shaw: https://www.deshaw.com/what-we-do
- (P) Jane Street: https://www.janestreet.com/what-we-do · Signals and Threads ep. 29: https://signalsandthreads.com/wrestling-the-world-into-rows
- (P) AQR, Craftsmanship Alpha, 2017: https://www.aqr.com/Insights/Research/Journal-Article/Craftsmanship-Alpha-An-Application-to-Style-Investing
- (P) Man AHL, Need for Speed, 4-ene-2023: https://www.man.com/maninstitute/need-for-speed-trend-following · Korgaonkar, 25-nov-2025: https://www.man.com/insights/the-big-innovation-imperative
- (S) Institutional Investor, 30-may-2016: https://www.institutionalinvestor.com/article/2bsy6ojiod6j0xv8okhz4/corner-office/quant-hedge-funds-balance-computer-and-brain-power
- (S) CXO sobre Harvey-Liu-Zhu: https://www.cxoadvisory.com/big-ideas/taming-the-factor-zoo/
- (S) CFA Digest sobre McLean-Pontiff 2016: https://rpc.cfainstitute.org/research/cfa-digest/2016/06/does-academic-research-destroy-stock-return-predictability-digest-summary · PDF: https://www.gwern.net/doc/economics/2016-mclean.pdf
- (P) Chen, arXiv 2206.15365: https://arxiv.org/abs/2206.15365
- (S) Jensen-Kelly-Pedersen, NBER w28432: https://nber.org/system/files/working_papers/w28432/w28432.pdf
- (S) Falck-Rej-Thesmar vía Harbourfront, dic-2024: https://harbourfrontquant.substack.com/p/why-and-how-systematic-trading-strategies
- (P) Khandani & Lo: https://web.mit.edu/Alo/www/Papers/august07b.html
- (P, industria) Acadian, abr-2026: https://www.acadian-asset.com/investment-insights/systematic-methods/misplaced-anxiety-a-reassessment-of-crowding-in-systematic-investing
