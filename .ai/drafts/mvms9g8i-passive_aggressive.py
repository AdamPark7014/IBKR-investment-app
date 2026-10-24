from __future__ import annotations
from dataclasses import dataclass

@dataclass
class UrgencyDecision:
    mode: str  # 'passive' | 'aggressive'
    reason: str

def decide_urgency(*, age_seconds: float, max_passive_seconds: float = 60.0, touchable: bool = True) -> UrgencyDecision:
    """Decide passive vs aggressive urgency for paper/sim.

    Maps conceptually to IBKR algoOriginalBest. Does NOT place orders.
    """
    if not touchable:
        return UrgencyDecision(mode="aggressive", reason="not touchable")
    if age_seconds >= max_passive_seconds:
        return UrgencyDecision(mode="aggressive", reason="aged past passive window")
    return UrgencyDecision(mode="passive", reason="within passive window")