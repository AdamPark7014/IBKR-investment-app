# Anexo 2 — Validación estadística y control del overfitting

Reporte del agente de investigación (21-10-2026). 28 búsquedas, 17 fuentes completas; 6 papers descargados como PDF y extraídos localmente (SSRN devolvió 403; NBER y AMS fallaron por certificado). [P]=primaria, [S]=secundaria.

## Hallazgos

### 1. Marco de López de Prado

- **"Backtesting is not a research tool"**: texto exacto en *The 10 Reasons Most ML Funds Fail* (JPM 2018), Pitfall #2: «feature importance is a research tool, and backtesting is not». «Even large hedge funds constantly fall into this trap»; «it does not matter if the backtest is a walk-forward out-of-sample»; «it typically takes about 20 such iterations to discover a (false) investment strategy» al 5 % [P].
- **Purga y embargo** (Pitfall #8): purgar del train toda observación cuya etiqueta se solape en tiempo con etiquetas del test; embargo = eliminar también las que siguen inmediatamente al test; «a small value h ≈ 0.01·T often suffices» [P].
- **CPCV** (Pitfall #9): el walk-forward «tests a single scenario (the historical path), which can be easily overfit»; CPCV parte T observaciones en N grupos sin barajar, prueba k grupos por split, genera C(N,k) splits y φ = k·C(N,k)/N caminos de backtest [P].
- **PBO / CSCV** (Bailey, Borwein, LdP, Zhu; 2014, JCF 2017): PBO = probabilidad de que la configuración óptima IS quede por debajo de la mediana OOS. Matriz T×N de rendimientos de N pruebas, S submatrices (S par), todas las combinaciones C(S, S/2) como train (S=16 → 12.870 combinaciones); en cada una se toma la mejor IS, su rango relativo OOS ω̄, el logit λ = ln(ω̄/(1−ω̄)); PBO = proporción de logits ≤ 0. Umbral: «reject models for which PBO is estimated to be greater than 0.05». Recomiendan S=16 con ≥4 años diarios; hold-out no sirve con <1.000 observaciones («if a strategy trades on a weekly basis, hold-out should not be used on backtests of less than 20 years») [P].
- **PSR/DSR** (Bailey & LdP, JPM 2014): PSR(SR*) = Z[(SR̂ − SR*)·√(T−1) / √(1 − γ₃SR̂ + (γ₄−1)/4·SR̂²)], SR en la frecuencia original. DSR = PSR evaluado en SR* = √V{SR̂ₙ}·[(1−γ)Z⁻¹(1−1/N) + γZ⁻¹(1−1/(N·e))], γ = 0,5772, N = pruebas independientes, V = varianza de los SR entre pruebas [P].
- **Triple barrera y meta-labeling** (Pitfalls #5–#6): barreras de profit/stop en función de la volatilidad estimada más barrera vertical; meta-labeling = modelo secundario que predice si el primario acierta (tamaño, no lado); «the effects of overfitting are limited when you apply meta-labeling» [P].

### 2. Harvey, Liu & Zhu / Arnott, Harvey & Markowitz

- **HLZ (RFS 2016)**: ≥316 factores; «a newly discovered factor needs to clear a much higher hurdle, with a t-ratio greater than 3.0»; «most claimed research findings in financial economics are likely false» [P vía NBER w20592].
- **Harvey & Liu, *Evaluating Trading Strategies* (JPM 2014)**: «T-statistic = Sharpe Ratio × √(Number of years)». SR 0,92 en 10 años → t = 2,91; con 200 pruebas Bonferroni exige t ≥ 3,66 y el SR ajustado cae a 0,08 [P].
- **Harvey & Liu, *Backtesting* (JPM 2015)**: «it is a serious mistake to use the usual 50% haircut»; con SR anual <0,4 el haircut «is almost always more than 50%»; con SR >1,0 «at most 25%». «This trial and error approach is not truly OOS»; «there is no true OOS that uses historical data» [P].
- **Arnott, Harvey & Markowitz (JFDS 2019)**: 7 categorías: hipótesis ex-ante y «quién está al otro lado»; registrar variables y combinaciones probadas; no recortar la muestra; «There is no real "out of sample" at this point, save live trading data»; «Avoid "tweaking" a model based on live results»; el modelo más simple; «Reward good processes, not good results» [S].

### 3. Prácticas de fondos

- **Man AHL** (mesa redonda, mayo 2015, con Harvey, Barberis, Shephard): usaron PBO para «enforce data partitioning with in-samples and out-of-samples more strongly»; «you now have to write down the data partitioning and the methodology and expectations»; «we do keep a record of the things we try»; «all strategies are first traded with the firm's capital». Test-trading de «2-3 months», insuficiente para significancia pero caza errores; «a 20% drawdown over the first three months would certainly look inconsistent with an assumed SR of 3». Shephard: con SR esperado 1, «I would be surprised if I didn't achieve 0.8 in trading» [P, man.com].
- **AQR** (Asness, *Lies, Damned Lies and Data Mining*, 2017): exige intuición económica y evidencia «out-of-sample through time, across geography, across asset class» [P].
- **WorldQuant BRAIN** (umbrales compilados por usuarios): Sharpe >1,25 (Delay-1) / >2 (Delay-0); Fitness = Sharpe·√(|Returns|/max(Turnover,0,125)) >1; turnover 1–70 %; peso máximo <10 %; **autocorrelación de PnL con tus alphas <0,7**; solo las que pasan IS entran a seguimiento OOS [S]. AgonAlpha (arXiv 2608.11250) confirma 0,70 y la fase OS [P].
- **Two Sigma**: ninguna fuente primaria sobre su protocolo. Hueco.

### 4. Herramientas abiertas

- **mlfinlab (Hudson & Thames)**: «licensed under an all rights reserved licence», acceso por compra [P, GitHub].
- **skfolio**: BSD; `CombinatorialPurgedCV(n_folds=10, n_test_folds=8, purged_size=0, embargo_size=0)` [P].
- **vectorbt PRO**: splits rolling/expanding/purged, walk-forward y DSR; de pago [P parcial].
- **purgedcv** (eslazarev): purged k-fold + CPCV + PSR/DSR compatibles con scikit-learn [S].
- **QuantConnect** (Research Guide): hipótesis «A change in {cause} leads to an {effect}», walk-forward, paper trading, time-box de 8–32 h por idea [P].

### 5. Ángulo contrario

- **Decaimiento post-publicación**: McLean & Pontiff (JF 2016): 97 predictores; retorno mensual 0,582 % IS → 0,402 % OOS pre-publicación → 0,264 % post-publicación; «26% lower out-of-sample and 58% lower post-publication» [P].
- **Réplica**: Jensen, Kelly & Pedersen (JF 2023): 153 factores, 93 países; tasa de réplica 82,4 % con alfa CAPM, 75,6 % tras corrección BY [P]. Chen (arXiv 2206.15365, nov-2025): FDR ≤ 25 % (cota simple) y ≤ 9 % (refinada) [P].
- **Críticas a LdP**: PBO es relativo (un factor verdadero pero dominado «will rarely be considered significant») [Harvey & Liu 2015, P]; Man AHL llama «a bit strong» al supuesto de reversión a la media del PBO [P]; DSR depende de N «the most important piece of information missing from virtually all backtest reports» [Bailey 2014]; no se encontró crítica publicada de CPCV; meta-labeling puede mejorar métricas solo por reducir exposición [S, débil].

## Contradicciones y huecos

1. **Hold-out vs. sin OOS real**: BBLZ dicen que el hold-out es «unreliable» y CPCV genera distribuciones OOS; Harvey-Liu y AHM replican que con datos históricos no existe OOS verdadero. Man AHL usa ambas cosas: particiones escritas de antemano + test-trading.
2. **PBO ≤ 0,05** es el único umbral primario; las librerías no lo imponen.
3. **t > 3 (HLZ) vs. FDR ≤ 9–25 % (Chen) vs. 82 % de réplica (JKP)**: el mismo cuerpo de evidencia da «mayoría falsa» o «mayoría verdadera» según el prior.
4. **Haircut 50 %**: rechazado por Harvey-Liu (no lineal).
5. Umbrales de WorldQuant compilados por usuarios; Two Sigma: cero fuentes.

## Protocolo mínimo para un individuo (Python + IBKR)

1. **Hipótesis escrita antes de tocar datos**, con causa→efecto y quién pierde al otro lado [AHM 2019; QuantConnect]. Escribe también la partición de datos y la expectativa de SR [Man AHL 2015].
2. **Registro de pruebas**: cada configuración probada cuenta como N; sin N no hay FWER, FDR, PBO ni DSR [LdP 2018; Bailey 2014].
3. **Presupuesto de pruebas vs. longitud**: con SR objetivo 1 y pruebas independientes, años mínimos ≈ E[max Zₙ]² ≤ 2 ln N: ~2 años → ≤7 pruebas; 5 años → ≤45; 10 años → ~200; 14 años → ~1.000. LdP: ~20 iteraciones ya producen una falsa al 5 %.
4. **Validación**: purged k-fold con embargo h ≈ 1 % de T; CPCV (N=6–10 grupos, k=2); CSCV con S=16 sobre ≥4 años diarios para PBO; **rechazar si PBO > 0,05** [BBLZ 2014]. Hold-out solo si hay ≥1.000 observaciones.
5. **Significancia**: t = SR·√años ≥ 3 [HLZ 2016]; además DSR ≥ 0,95 con N real y V entre pruebas [Bailey-LdP 2014]. Regla de dedo (10 años diarios, pruebas independientes): el SR anual observado debe superar ~1,0 / 1,3 / 1,55 para N = 10 / 100 / 1.000. Un SR anual <0,4 pierde >50 % tras el haircut; no vale la pena [HL 2015].
6. **Hold-out congelado** (último 1–2 años) se usa una vez; si falla, se descarta la idea [HL 2015].
7. **Paper trading / capital mínimo 2–3 meses** para cazar errores de implementación, no para significancia (con SR 1 hacen falta 9 años para t=3); matar si el drawdown es inconsistente con el SR asumido; esperar ~0,8× el SR de backtest [Man AHL]. **No retocar con resultados en vivo** [AHM 2019].
8. **Diversificación de alphas**: correlación de PnL < 0,7 con lo que ya operas [WorldQuant, S].

## Fuentes

**Primarias**
- Bailey, Borwein, López de Prado, Zhu, *The Probability of Backtest Overfitting* (2014; JCF 2017): https://carmamaths.org/jon/backtest2.pdf · https://papers.ssrn.com/abstract=2326253
- López de Prado, *The 10 Reasons Most Machine Learning Funds Fail* (JPM 2018): https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf
- Bailey & López de Prado, *The Deflated Sharpe Ratio* (JPM 2014): https://papers.ssrn.com/abstract=2460551
- Bailey, *FAQs on backtest overfitting* (2014): https://mathinvestor.org/2014/04/faqs-on-backtest-overfitting/
- Harvey & Liu, *Evaluating Trading Strategies* (JPM 2014): https://people.duke.edu/~charvey/Research/Published_Papers/P116_Evaluating_trading_strategies.pdf
- Harvey & Liu, *Backtesting* (JPM 2015): https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- Harvey, Liu & Zhu, *…and the Cross-Section of Expected Returns* (RFS 2016): https://www.nber.org/papers/w20592
- Arnott, Harvey & Markowitz, *A Backtesting Protocol in the Era of Machine Learning* (JFDS 2019): https://papers.ssrn.com/abstract=3275654
- McLean & Pontiff (JF 2016): https://www.gwern.net/doc/economics/2016-mclean.pdf
- Jensen, Kelly & Pedersen, *Is There a Replication Crisis in Finance?* (JF 2023): https://research-api.cbs.dk/ws/portalfiles/portal/95651880/theis_ingerslev_jensen_et_al_is_there_a_replication_crisis_in_finance_publishersversion.pdf
- Chen (arXiv 2206.15365): https://arxiv.org/abs/2206.15365
- Man AHL, *Overfitting and Its Impact on the Investor* (2015): https://www.man.com/maninstitute/overfitting-and-its-impact-on-the-investor
- Asness/AQR, *Lies, Damned Lies, and Data Mining* (2017): https://www.aqr.com/insights/perspectives/lies-damned-lies-and-data-mining
- Ye et al., *AgonAlpha* (arXiv 2608.11250): https://arxiv.org/html/2608.11250
- mlfinlab: https://github.com/hudson-and-thames/mlfinlab · skfolio: https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html · vectorbt PRO: https://vectorbt.pro/features/optimization · QuantConnect Research Guide: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide

**Secundarias**
- Resumen AHM: https://alphaarchitect.com/2018/12/protocol-to-prevent-quants-gone-wild
- Resumen JKP (CXO): https://www.cxoadvisory.com/big-ideas/re-examining-equity-factor-research-replicability/
- Criterios BRAIN compilados: https://github.com/QuantML-Research/wq-alpha-research/blob/main/SKILL.md
- Chen & Zimmermann, *Open Source Cross-Sectional Asset Pricing*: https://www.federalreserve.gov/econres/feds/files/2021-037pap.pdf
- DSR (Wikipedia): https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio · purgedcv: https://github.com/eslazarev/purged-cross-validation · R `pbo`: https://cran.r-project.org/package=pbo

Textos extraídos de los PDF (pbo, harvey-liu-backtesting, harvey-liu-evaluating, mclean-pontiff-2016, ldp-10-reasons, jkp) quedaron en el scratchpad de la sesión, carpeta `pdftxt`.
