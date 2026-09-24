from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from ..config import AppSettings
from ..ensemble.combiner import (
    EnsembleWeights,
    apply_regime_filter,
    enforce_stops,
    score_strategies,
    score_to_position,
)
from ..intelligence.features import build_features
from ..intelligence.regime import detect_regime
from ..logging import setup_logging
from ..ops.journal import get_engine as get_journal_engine
from ..strategy.mean_reversion import MeanReversion
from ..strategy.sma_crossover import SMACrossover

log = setup_logging()


@dataclass
class Decision:
    symbol: str
    action: str  # BUY/SELL/HOLD/WATCH/NO_TRADE
    score: float
    confidence: float
    position_size: float
    reason: str
    regime: dict


class DecisionEngine:
    """
    Phase-1 skeleton: compute signals and scores, but always output NO_TRADE.
    Records decisions into the journal with full context for post-mortem.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.journal = get_journal_engine(settings.data.journal_db)

    def generate(self, prices: Dict[str, pd.DataFrame]) -> List[Decision]:
        # Features/regime
        feats = build_features(prices)
        regime = detect_regime(
            self.settings.universe, self.settings.engine, self.settings.data, prices
        )
        # Strategies
        sma = SMACrossover(
            fast_window=int(self.settings.strategy.params.get("fast_window", 10)),
            slow_window=int(self.settings.strategy.params.get("slow_window", 30)),
        )
        mr = MeanReversion(window=20, num_std=2.0)
        sma_sig = sma.generate_signals(prices)
        mr_sig = mr.generate_signals(prices)
        combined = {sym: {"sma": sma_sig.get(sym), "mr": mr_sig.get(sym)} for sym in prices.keys()}
        weights = EnsembleWeights(strategy_weights={"sma": 0.6, "mr": 0.4})
        scores = score_strategies(combined, weights)
        scores = apply_regime_filter(scores, regime)
        # Convert to desired positions with stops (but do not place orders in phase 1)
        decisions: List[Decision] = []
        for sym, df in prices.items():
            sc = float(scores[sym].iloc[-1]) if not scores[sym].empty else 0.0
            pos_series = score_to_position(scores[sym])
            _ = enforce_stops(pos_series, df["close"], feats[sym]["atr_14"])
            # Phase-1: force NO_TRADE; set confidence modestly based on |score|
            dec = Decision(
                symbol=sym,
                action="NO_TRADE",
                score=sc,
                confidence=float(min(0.8, max(0.0, abs(sc)))),
                position_size=0.0,
                reason="Fase 1: política NO_TRADE. Decisión registrada para post-mortem.",
                regime={
                    "risk_on": int(regime["risk_on"].iloc[-1]) if not regime.empty else 0,
                    "breadth": float(regime["breadth"].iloc[-1]) if not regime.empty else 0.0,
                    "trend": int(regime["trend"].iloc[-1]) if not regime.empty else 0,
                },
            )
            decisions.append(dec)
            # Journal (fase 1)
            try:
                from ..ops.journal import record_decision  # local import to avoid cycles

                record_decision(
                    self.journal,
                    symbol=dec.symbol,
                    action=dec.action,
                    score=dec.score,
                    confidence=dec.confidence,
                    position_size=dec.position_size,
                    reason=dec.reason,
                    regime_json=json.dumps(dec.regime),
                    source_json=json.dumps(
                        {
                            "features": "technical (SMA/EMA/ATR/RSI/breadth)",
                            "regime_method": "VIX<MA50 + breadth + trend proxy",
                        }
                    ),
                )
            except Exception as e:
                log.error("journal_write_failed %s", str(e))
        return decisions

