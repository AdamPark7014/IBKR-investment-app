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
from ..ops.journal import record_decision
from ..ops.paper_policy import apply_stop_veto, classify_paper_action, size_paper_positions
from ..portfolio.sizing import volatility_target_weights
from ..risk.manager import RiskManager
from ..strategy.mean_reversion import MeanReversion
from ..strategy.sma_crossover import SMACrossover

log = setup_logging()


@dataclass
class Decision:
    symbol: str
    action: str  # BUY/SELL/WATCH/NO_TRADE
    score: float
    confidence: float
    position_size: float
    reason: str
    regime: dict


class DecisionEngine:
    """
    Paper policy engine: compute signals, scores and issue PAPER BUY/SELL/WATCH/NO_TRADE.
    Does NOT execute broker orders. Records decisions into the journal for post-mortem review.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.journal = record_decision.__globals__["journal_db"] if hasattr(record_decision, '__globals__') else None
        try:
            from ..ops.journal import get_engine as get_journal_engine
            self.journal = get_journal_engine(settings.data.journal_db)
        except ImportError:
            pass

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

        # Risk and sizing setup (no execution)
        risk = RiskManager(self.settings.risk)
        killswitch_active = risk.killswitch_active()
        vol_w = volatility_target_weights(
            prices.values(), target_annual_vol=float(self.settings.risk.target_vol_annual)
        )

        decisions: List[Decision] = []
        for sym, df in prices.items():
            # Basic data sanity check
            data_ok = isinstance(df, pd.DataFrame) and not df.empty and "close" in df.columns
            score_last = float(scores[sym].iloc[-1]) if scores[sym].empty else float(scores[sym].iloc[-1]) if scores[sym].isna().any() else float(scores[sym].iloc[-1])
            try:
                score_val = score_last if not pd.isna(score_last) else 0.0
            except Exception:
                score_val = 0.0

            allowed, _ = risk.check_symbol_allowed(sym)

            # Classify paper action
            direction = self.settings.trading.direction
            killswitch_active = killswitch_active  # Ensure scope
            action, reason = classify_paper_action(
                score=score_val, direction=direction, killswitch=killswitch_active, symbol_allowed=allowed, data_ok=data_ok
            )

            pos_series = score_to_position(scores[sym]) if scores[sym].notempty else pd.Series([], dtype=float)
            if isinstance(pos_series, dict) or not hasattr(pos_series, 'iloc'):
                try:
                    pos_series = score_to_position(scores[sym])
                except Exception:
                    pos_series = pd.Series([], dtype=float)

            # Apply stop logic if features available and alignment ok
            effective = None
            veto_reason = None
            if data_ok and "atr_14" in feats.get(sym, {}):
                # Ensure series alignment
                if isinstance(pos_series, pd.Series) and not pos_series.empty:
                    try:
                        effective = enforce_stops(pos_series, df["close"], feats[sym]["atr_14"])
                        desired_sign = int(pos_series.iloc[-1])
                        effective_series = effective if isinstance(effective, pd.Series) else pd.Series([effective], index=[0])
                        effective_sign = int(effective_series.iloc[-1])
                    except Exception:
                        desired_sign = 0
                        effective_sign = 0
                        effective = pos_series
                else:
                    desired_sign = 0
                    effective_sign = 0
                    effective = pos_series
            else:
                desired_sign = int(pos_series.iloc[-1]) if not pos_series.empty and isinstance(pos_series, pd.Series) else 0
                effective_sign = desired_sign
                effective = pos_series

            # Apply veto
            action, veto_reason = apply_stop_veto(action, desired_sign, effective_sign)
            if veto_reason:
                reason = veto_reason

            # Size paper position (no execution)
            size_val = 0.0
            confidence = 0.0
            try:
                if not pos_series.empty and isinstance(pos_series, pd.Series):
                    if len(pos_series) > 0:
                        size_val = float(pos_series.iloc[-1])
                    else:
                        size_val = 0.0
                if score_val != 0.0 and not pd.isna(score_val):
                    confidence = min(0.9, abs(score_val))
            except Exception:
                pass

            # Prepare regime dict for serialization
            regime_dict = {}
            try:
                regime_dict["risk_on"] = int(regime["risk_on"].iloc[-1]) if not regime.empty else 0
                regime_dict["breadth"] = float(regime["breadth"].iloc[-1]) if not regime.empty else 0.0
                regime_dict["trend"] = int(regime["trend"].iloc[-1]) if not regime.empty else 0
            except Exception:
                pass

            dec = Decision(
                symbol=sym,
                action=action,
                score=score_val,
                confidence=confidence,
                position_size=size_val,
                reason=reason if veto_reason else (f"Score={score_val:.2f}, Vol={size_val:.4f}" if size_val > 0.0 else "No trade signal"),
                regime=regime_dict,
            )
            decisions.append(dec)

            # Journal record
            try:
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
                            "methodology": "paper_policy v1",
                        }
                    ),
                )
            except Exception as e:
                log.error("journal_write_failed %s", str(e))

        return decisions