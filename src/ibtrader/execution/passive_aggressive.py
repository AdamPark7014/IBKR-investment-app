from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UrgencyDecision:
    mode: str  # passive | aggressive
    reason: str


def decide_urgency(
    *,
    age_seconds: float,
    max_passive_seconds: float = 60.0,
    touchable: bool = True,
) -> UrgencyDecision:
    """Paper-only urgency. Conceptual map to IBKR algoOriginalBest; does not place orders."""
    if not touchable:
        return UrgencyDecision(mode="aggressive", reason="not touchable")
    if float(age_seconds) >= float(max_passive_seconds):
        return UrgencyDecision(mode="aggressive", reason="aged past passive window")
    return UrgencyDecision(mode="passive", reason="within passive window")


__all__ = ["UrgencyDecision", "decide_urgency"]
