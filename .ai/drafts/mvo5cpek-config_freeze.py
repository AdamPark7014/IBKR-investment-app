from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def load_assumed_sharpe(freeze_path: str | Path, default: float = 0.8) -> float:
    p = Path(freeze_path)
    if not p.is_file():
        return default
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default

    def get_float(v) -> float | None:
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and v.strip():
            try:
                return float(v)
            except ValueError:
                return None
        return None

    if isinstance(raw, dict) and 'assumed_sharpe' in raw:
        val = get_float(raw['assumed_sharpe'])
        if val is not None:
            return val
    if isinstance(raw, dict) and 'snapshot' in raw and isinstance(raw['snapshot'], dict):
        snap = raw['snapshot']
        if 'assumed_sharpe' in snap:
            val = get_float(snap['assumed_sharpe'])
            if val is not None:
                return val

    return default


def snapshot_settings(settings: Any) -> dict[str, Any]:
    '''Extrae subset estable de AppSettings (risk, commission, slippage, engine, universe symbols).'''
    def dump(obj: Any) -> Any:
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        if isinstance(obj, Mapping):
            return dict(obj)
        return obj
    out = {
        'universe': list(getattr(getattr(settings, 'universe', None), 'symbols', []) or []),
        'benchmark': getattr(getattr(settings, 'universe', None), 'benchmark', None),
        'risk': dump(getattr(settings, 'risk', {})),
        'commission': dump(getattr(settings, 'commission', {})),
        'slippage': dump(getattr(settings, 'slippage', {})),
        'reg_fees': dump(getattr(settings, 'reg_fees', {})),
        'engine': dump(getattr(settings, 'engine', {})),
    }
    return out

def config_hash(snapshot: Mapping[str, Any]) -> str:
    blob = json.dumps(snapshot, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:16]

def write_freeze(path: str | Path, settings: Any) -> dict[str, Any]:
    snap = snapshot_settings(settings)
    h = config_hash(snap)
    payload = {'hash': h, 'snapshot': snap}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return payload

def verify_freeze(path: str | Path, settings: Any) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        actual = config_hash(snapshot_settings(settings))
        return {'ok': False, 'reason': 'missing_freeze', 'expected': None, 'actual': actual}
    raw = json.loads(p.read_text(encoding='utf-8'))
    expected = str(raw.get('hash') or '')
    actual = config_hash(snapshot_settings(settings))
    return {
        'ok': expected == actual,
        'reason': None if expected == actual else 'hash_mismatch',
        'expected': expected,
        'actual': actual,
    }

__all__ = ['snapshot_settings', 'config_hash', 'write_freeze', 'verify_freeze', 'load_assumed_sharpe']