from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class Alert:
    code: str
    severity: str  # 'info'|'warn'|'kill_recommend'
    message: str

def evaluate_paper_alerts(*, max_drawdown: float|None, assumed_sharpe: float=0.8, n_drift: int=0, orders_sent: int=0, days_observed: int|None=None) -> list[Alert]:
    alerts = []
    
    if orders_sent > 0:
        alerts.append(Alert(code='orders_unexpected', severity='warn', message='broker orders unexpected in paper triage'))
        
    if n_drift >= 5:
        alerts.append(Alert(code='paper_drift', severity='warn', message='detected significant paper drift'))

    if max_drawdown is not None and assumed_sharpe > 0:
        threshold = min(0.35, 0.15 + 0.25 / max(assumed_sharpe, 0.1))
        if max_drawdown > threshold:
            alerts.append(Alert(code='dd_vs_sharpe', severity='kill_recommend', message='DD inconsistent with assumed Sharpe (review; do not retune live)'))

    alerts.append(Alert(code='triage_disclaimer', severity='info', message='this is paper triage only'))
    
    return alerts

__all__ = ['Alert', 'evaluate_paper_alerts']