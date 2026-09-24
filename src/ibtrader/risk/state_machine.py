from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict


class RiskState(Enum):
    NORMAL = auto()
    RISK_RESTRICTED = auto()
    COOLDOWN = auto()
    EMERGENCY = auto()
    FLAT = auto()


class Intent(Enum):
    OPEN = auto()
    INCREASE = auto()
    REDUCE = auto()
    CLOSE = auto()
    STOP = auto()
    EMERGENCY_EXIT = auto()


# Allowed-operation matrix by state
ALLOWED: Dict[RiskState, Dict[Intent, bool]] = {
    RiskState.NORMAL: {
        Intent.OPEN: True,
        Intent.INCREASE: True,
        Intent.REDUCE: True,
        Intent.CLOSE: True,
        Intent.STOP: True,
        Intent.EMERGENCY_EXIT: True,
    },
    RiskState.RISK_RESTRICTED: {
        Intent.OPEN: False,
        Intent.INCREASE: False,
        Intent.REDUCE: True,
        Intent.CLOSE: True,
        Intent.STOP: True,
        Intent.EMERGENCY_EXIT: True,
    },
    RiskState.COOLDOWN: {
        Intent.OPEN: False,
        Intent.INCREASE: False,
        Intent.REDUCE: True,
        Intent.CLOSE: True,
        Intent.STOP: True,
        Intent.EMERGENCY_EXIT: True,
    },
    RiskState.EMERGENCY: {
        Intent.OPEN: False,
        Intent.INCREASE: False,
        Intent.REDUCE: True,
        Intent.CLOSE: True,
        Intent.STOP: True,
        Intent.EMERGENCY_EXIT: True,
    },
    RiskState.FLAT: {
        Intent.OPEN: False,
        Intent.INCREASE: False,
        Intent.REDUCE: False,
        Intent.CLOSE: False,
        Intent.STOP: False,
        Intent.EMERGENCY_EXIT: False,
    },
}


@dataclass
class RiskFSM:
    state: RiskState = RiskState.NORMAL

    def allow(self, intent: Intent) -> bool:
        return bool(ALLOWED.get(self.state, {}).get(intent, False))

    def set_restricted(self) -> None:
        self.state = RiskState.RISK_RESTRICTED

    def set_emergency(self) -> None:
        self.state = RiskState.EMERGENCY

    def set_cooldown(self) -> None:
        self.state = RiskState.COOLDOWN

    def set_normal(self) -> None:
        self.state = RiskState.NORMAL

    def set_flat(self) -> None:
        self.state = RiskState.FLAT

    @staticmethod
    def classify_intent(current_qty: int, delta: int, is_stop: bool = False, is_emergency: bool = False) -> Intent:
        if is_emergency:
            return Intent.EMERGENCY_EXIT
        if is_stop:
            return Intent.STOP
        if current_qty == 0:
            return Intent.OPEN if delta != 0 else Intent.CLOSE
        if (current_qty > 0 and delta > 0) or (current_qty < 0 and delta < 0):
            return Intent.INCREASE
        if (current_qty > 0 and delta < 0) or (current_qty < 0 and delta > 0):
            return Intent.REDUCE
        if current_qty + delta == 0:
            return Intent.CLOSE
        return Intent.OPEN

