### Motor de decisiones (fase 1)

Meta: producir decisiones explicadas, no sólo BUY/SELL. Cada decisión incluye: ACTIVO, TESIS (evidencia), FUNDAMENTALS, VALUATION, QUANT, TECHNICAL, MACRO, SENTIMENT, RIESGO, CATALYSTS, INVALIDACIÓN, HORIZONTE, EXPECTED RETURN/DOWNSIDE, CONFIDENCE, POSITION SIZE, ACTION (BUY/HOLD/SELL/WATCH/NO_TRADE).

Papel (recomendación, sin órdenes):
- Flujo:
  1) Ingesta de datos (con linaje y validación).
  2) Features técnicas y detección de régimen (trend vs range, risk-on/off).
  3) Ensemble de señales: combinación de estrategias técnicas/quant con pesos configurables.
  4) Portfolio sizing por volatilidad objetivo, con tope por nombre y por exposición bruta.
  5) Risk Manager: kill switch, lista de símbolos y stop ATR vetan aperturas.
  6) Acción de papel: BUY / SELL / WATCH / NO_TRADE. `paper-run` no envía órdenes. NO_TRADE si faltan datos, hay kill switch, el símbolo no está permitido o el stop ATR anula la entrada. Sin VIX el régimen no es risk-on y los largos se apagan.
- Journal: se persiste cada decisión en `decisions` (SQLite) con:
  - `timestamp`, `symbol`, `action`, `score`, `confidence`, `regime`, `risk_flags`, `position_size`, `source_metadata` (JSON con fuentes/timestamps/metodologías).

Evitando sobreajuste:
- La ruta ML es opcional y no se activa hasta que supere baselines fuera de muestra. CV temporal purgado + walk-forward.
- Comparación con reglas simples (SMA/mean reversion) y “no-trade/buy&hold” como líneas base.

Explicabilidad:
- El ensemble conserva los componentes (trend/momentum/vol/valoración/etc.), su contribución al score y el porqué de la acción (o “NO_TRADE”).

Promoción de cambios:
- Bucle post-mercado: leer journal del día, post-mortem, detectar deriva de estrategia/modelo, proponer cambios con validación OOS. Nunca se promueve a LIVE de forma automática.

