from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass
class Alert:
    code: str
    severity: str  # 'info'|'warn'|'kill_recommend'
    message: str

def evaluate_paper_alerts(*, max_drawdown: float | None, assumed_sharpe: float = 0.8, n_drift: int = 0, orders_sent: int = 0, days_observed: int | None = None) -> list[Alert]:
    alerts: list[Alert] = []
    
    if orders_sent > 0:
        alerts.append(Alert(code='orders_unexpected', severity='warn', message='broker orders unexpected in paper triage'))
        
    if n_drift >= 5:
        alerts.append(Alert(code='paper_drift', severity='warn', message=f'paper drift detected: {n_drift} units vs desired stability'))
        
    threshold = min(0.35, 0.15 + 0.25 / max(assumed_sharpe, 0.1))
    if max_drawdown is not None and assumed_sharpe > 0 and max_drawdown > threshold:
        alerts.append(Alert(code='dd_vs_sharpe', severity='kill_recommend', message='DD inconsistent with assumed Sharpe (review; do not retune live)'))
        
    alerts.append(Alert(code='triage_disclaimer', severity='info', message='this is paper triage only, not advice, no live retune from alerts'))
    
    return alerts

__all__ = ['Alert', 'evaluate_paper_alerts']