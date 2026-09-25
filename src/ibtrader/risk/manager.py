from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

from ..config import RiskConfig
from .state_machine import Intent, RiskFSM


@dataclass
class RiskState:
    starting_equity_today: float
    orders_today: int = 0
    halted: bool = False
    current_date: str | None = None
    first_equity: float | None = None
    peak_equity: float | None = None


class RiskManager:
    def __init__(self, cfg: RiskConfig, state: RiskState | None = None) -> None:
        self.cfg = cfg
        self.state = state or RiskState(starting_equity_today=0.0)
        # Explicit finite-state machine for risk permissions
        self.fsm = RiskFSM()

    def on_new_day(self, date_str: str, starting_equity: float) -> None:
        if self.state.current_date != date_str:
            self.state.current_date = date_str
            self.state.starting_equity_today = float(starting_equity)
            if self.state.first_equity is None:
                self.state.first_equity = float(starting_equity)
                self.state.peak_equity = float(starting_equity)
            else:
                if self.state.peak_equity is None or starting_equity > self.state.peak_equity:
                    self.state.peak_equity = float(starting_equity)
            self.state.orders_today = 0
            # Do not auto-clear halted; daily halt applies only to this day
            self.state.halted = False
            # Reset FSM to NORMAL at start of day; transitions may restrict later
            self.fsm.set_normal()

    def check_killswitch(self, intent: Intent) -> Tuple[bool, str]:
        if os.path.exists(self.cfg.killswitch_file):
            # Killswitch implies EMERGENCY state (but exits/reductions still allowed via FSM)
            self.fsm.set_emergency()
            # Do not block close/reduce/stop/emergency
            if intent in {Intent.CLOSE, Intent.REDUCE, Intent.STOP, Intent.EMERGENCY_EXIT}:
                return True, "OK"
            # For opens/increases, if action is block_new_only, veto; if flatten, veto too (engine will flatten)
            return False, "Kill switch activado."
        return True, "OK"

    def check_symbol_allowed(self, symbol: str) -> Tuple[bool, str]:
        if self.cfg.allowed_symbols and symbol not in self.cfg.allowed_symbols:
            return False, f"Símbolo no permitido: {symbol}"
        return True, "OK"

    def check_position_size(self, equity: float, price: float, resulting_position_qty: int) -> Tuple[bool, str]:
        notional = abs(resulting_position_qty) * price
        if notional > equity * (self.cfg.max_position_pct / 100.0):
            return False, "Tamaño de posición excede el máximo permitido."
        return True, "OK"

    def check_total_exposure(
        self, equity: float, current_positions_value: float, is_risk_reducing: bool
    ) -> Tuple[bool, str]:
        # Never block risk-reducing/orders de-risking exposure
        if is_risk_reducing:
            return True, "OK"
        if abs(current_positions_value) > equity * (self.cfg.max_total_exposure_pct / 100.0):
            return False, "Exposición total excede el máximo permitido."
        return True, "OK"

    def check_daily_loss(self, current_equity: float) -> Tuple[bool, str]:
        limit = self.state.starting_equity_today * (self.cfg.daily_loss_limit_pct / 100.0)
        if current_equity < self.state.starting_equity_today - limit:
            self.state.halted = True
            # Enter restricted state for new/increase orders
            self.fsm.set_restricted()
            return False, "Límite de pérdida diario excedido. Trading detenido."
        return True, "OK"

    def check_cumulative_loss(self, current_equity: float) -> Tuple[bool, str]:
        if self.state.first_equity is None:
            return True, "OK"
        limit = self.state.first_equity * (self.cfg.cumulative_loss_limit_pct / 100.0)
        if current_equity < self.state.first_equity - limit:
            self.fsm.set_restricted()
            return False, "Límite de pérdida acumulada excedido."
        return True, "OK"

    def check_drawdown(self, current_equity: float) -> Tuple[bool, str]:
        if self.state.peak_equity is None or self.state.peak_equity == 0:
            return True, "OK"
        dd = (current_equity - self.state.peak_equity) / self.state.peak_equity
        if dd < -abs(self.cfg.drawdown_limit_pct / 100.0):
            self.fsm.set_restricted()
            return False, "Límite de drawdown excedido."
        return True, "OK"

    def check_order_count(self, intent: Intent) -> Tuple[bool, str]:
        if intent in {Intent.CLOSE, Intent.REDUCE, Intent.STOP, Intent.EMERGENCY_EXIT}:
            return True, "OK"
        if self.state.orders_today >= self.cfg.max_orders_per_day:
            return False, "Máximo de órdenes diarias alcanzado."
        return True, "OK"

    def approve_order(
        self,
        symbol: str,
        equity: float,
        price: float,
        quantity: int,
        current_positions_value: float,
        current_position_qty: int,
        is_stop: bool = False,
        is_emergency: bool = False,
    ) -> Tuple[bool, str]:
        # Classify intent
        delta = int(quantity)
        is_reducing = (current_position_qty > 0 and delta < 0) or (current_position_qty < 0 and delta > 0)
        intent = RiskFSM.classify_intent(
            current_qty=int(current_position_qty),
            delta=delta,
            is_stop=is_stop,
            is_emergency=is_emergency,
        )
        # Special probe: no-op order used to probe risk state
        if delta == 0 and current_position_qty == 0:
            ok, msg = self.check_daily_loss(equity)
            if not ok:
                return ok, msg
            ok, msg = self.check_cumulative_loss(equity)
            if not ok:
                return ok, msg
            ok, msg = self.check_drawdown(equity)
            if not ok:
                return ok, msg
            return True, "OK"
        # Evaluate killswitch and loss limits BEFORE deciding permissions
        ok, msg = self.check_killswitch(intent)
        if not ok and not is_reducing:
            return ok, msg
        # Daily loss check updates FSM (restricted) but should not block reductions/exits
        _ok, _ = self.check_daily_loss(equity)
        _ok, _ = self.check_cumulative_loss(equity)
        _ok, _ = self.check_drawdown(equity)
        # If halted (daily loss), ensure FSM is in restricted state (defensive)
        if self.state.halted:
            self.fsm.set_restricted()
        # Detect flip (sign change across zero)
        resulting = current_position_qty + delta
        is_flip = (current_position_qty > 0 and resulting < 0) or (current_position_qty < 0 and resulting > 0)
        if is_flip:
            # CLOSE leg must be allowed; OPEN leg must obey restrictions/limits
            close_intent = Intent.CLOSE
            open_intent = Intent.OPEN
            # If restricted/emergency, open leg is not permitted
            if not self.fsm.allow(close_intent):
                return False, f"Operación no permitida en estado de riesgo ({self.fsm.state.name}): {close_intent.name}"
            # Check killswitch for the open leg as well
            ok_kill, msg_kill = self.check_killswitch(open_intent)
            if (not self.fsm.allow(open_intent)) or (not ok_kill):
                return False, (
                    "Flip requiere apertura nueva pero está bloqueada por "
                    f"estado de riesgo ({self.fsm.state.name})."
                )
            # Check size/exposure for the resulting open leg
            new_qty = resulting
            ok, msg = self.check_position_size(equity, price, new_qty)
            if not ok:
                return False, msg
            ok, msg = self.check_total_exposure(equity, current_positions_value, is_risk_reducing=False)
            if not ok:
                return False, msg
            # Order count should not block close; only counts when actually sent — engine sends a single order
            ok, msg = self.check_order_count(open_intent)
            if not ok:
                return False, msg
            return True, "OK"
        # Enforce FSM: allow REDUCE/CLOSE even if restricted/emergency; block OPEN/INCREASE when restricted
        if not self.fsm.allow(intent):
            return False, f"Operación no permitida en estado de riesgo ({self.fsm.state.name}): {intent.name}"
        for check in [
            lambda: self.check_killswitch(intent),
            lambda: self.check_symbol_allowed(symbol),
            # Do not block risk-reducing orders on position-size
            (lambda: (True, "OK"))
            if is_reducing
            else (lambda: self.check_position_size(equity, price, current_position_qty + delta)),
            lambda: self.check_total_exposure(
                equity,
                current_positions_value,
                is_risk_reducing=is_reducing,
            ),
            lambda: self.check_order_count(intent),
        ]:
            ok, msg = check()
            if not ok:
                return ok, msg
        return True, "OK"

    def update_equity(self, equity: float) -> None:
        # Update peak equity
        if self.state.first_equity is None:
            self.state.first_equity = float(equity)
        if self.state.peak_equity is None or equity > self.state.peak_equity:
            self.state.peak_equity = float(equity)

    def notify_order_sent(self) -> None:
        self.state.orders_today += 1

