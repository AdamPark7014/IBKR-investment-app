from __future__ import annotations
from pathlib import Path
from typing import Any
import json


def build_paper_status(data_dir: str | Path = 'data') -> dict[str, Any]:
    root = Path(data_dir)
    names = {
        'freeze': 'paper_config_freeze.json',
        'equity': 'paper_equity.jsonl',
        'positions': 'paper_positions.json',
        'open_orders': 'paper_open_orders.json',
        'stack': 'paper_stack.sqlite',
        'slippage': 'slippage_ledger.jsonl',
    }
    files = {k: (root / v).is_file() for k, v in names.items()}
    summaries: dict[str, Any] = {}
    freeze_path = root / names['freeze']
    if files['freeze']:
        try:
            raw = json.loads(freeze_path.read_text(encoding='utf-8'))
            summaries['freeze_hash'] = raw.get('hash')
        except Exception:
            summaries['freeze_hash'] = None
    if files['equity']:
        try:
            from .paper_curve import load_equity_points, paper_max_drawdown
            pts = load_equity_points(root / names['equity'])
            summaries['equity'] = {'n_points': len(pts), 'max_dd': paper_max_drawdown(root / names['equity']), 'last': pts[-1]['equity'] if pts else None}
        except Exception as e:
            summaries['equity'] = {'error': str(e)}
    if files['open_orders']:
        try:
            from .open_orders import summary as oo_summary
            summaries['open_orders'] = oo_summary(root / names['open_orders'])
        except Exception as e:
            summaries['open_orders'] = {'error': str(e)}
    return {'orders_sent': 0, 'data_dir': str(root), 'files': files, 'summaries': summaries, 'notes': ['paper triage only', 'do not retune live']}


__all__ = ['build_paper_status']