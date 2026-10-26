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


#: Freeze schema. 1 = risk/costs/engine/universe only (did not see mode, trading or strategy).
FREEZE_SCHEMA = 2
_LEGACY_SECTIONS = ("universe", "benchmark", "risk", "commission", "slippage", "reg_fees", "engine")


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, Mapping):
        return dict(obj)
    return obj


def snapshot_settings(settings: Any) -> dict[str, Any]:
    """Everything that defines the frozen paper system.

    Universe, risk, costs and engine, plus ``mode`` / ``live_trading_confirmed`` (PAPER vs LIVE),
    ``trading`` (``allow_broker_orders``, ``direction``, hysteresis…) and ``strategy`` (rule and
    parameters): retuning the strategy or enabling orders is exactly what the freeze must catch.
    """
    universe = getattr(settings, "universe", None)
    return {
        "universe": list(getattr(universe, "symbols", []) or []),
        "benchmark": getattr(universe, "benchmark", None),
        "risk": _dump(getattr(settings, "risk", {})),
        "commission": _dump(getattr(settings, "commission", {})),
        "slippage": _dump(getattr(settings, "slippage", {})),
        "reg_fees": _dump(getattr(settings, "reg_fees", {})),
        "engine": _dump(getattr(settings, "engine", {})),
        "mode": str(getattr(settings, "mode", "PAPER")).upper(),
        "live_trading_confirmed": str(getattr(settings, "live_trading_confirmed", "no")),
        "trading": _dump(getattr(settings, "trading", {})),
        "strategy": _dump(getattr(settings, "strategy", {})),
    }


def config_hash(snapshot: Mapping[str, Any]) -> str:
    blob = json.dumps(snapshot, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _legacy_hash(snapshot: Mapping[str, Any]) -> str:
    return config_hash({k: snapshot.get(k) for k in _LEGACY_SECTIONS})


def _changed_sections(stored: Any, current: Mapping[str, Any]) -> list[str]:
    if not isinstance(stored, Mapping):
        return sorted(current)
    keys = set(stored) | set(current)
    norm = lambda v: json.dumps(v, sort_keys=True, default=str)  # noqa: E731
    return sorted(k for k in keys if norm(stored.get(k)) != norm(current.get(k)))


def write_freeze(path: str | Path, settings: Any) -> dict[str, Any]:
    snap = snapshot_settings(settings)
    payload = {"schema": FREEZE_SCHEMA, "hash": config_hash(snap), "snapshot": snap}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def verify_freeze(path: str | Path, settings: Any) -> dict[str, Any]:
    """Compare the current settings with the freeze on disk. Never writes.

    ``reason``: ``None`` (same config), ``missing_freeze``, ``invalid_freeze``, ``hash_mismatch``
    (something changed: see ``changed_sections``) or ``freeze_schema_outdated`` (a schema-1 freeze
    whose sections still match; it never covered mode/trading/strategy, so it must be rewritten once
    with ``ibtrader config-freeze --write``).
    """
    snap = snapshot_settings(settings)
    actual = config_hash(snap)
    p = Path(path)
    base: dict[str, Any] = {"actual": actual, "schema_expected": FREEZE_SCHEMA}
    if not p.is_file():
        return {**base, "ok": False, "reason": "missing_freeze", "expected": None, "changed_sections": []}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**base, "ok": False, "reason": "invalid_freeze", "expected": None, "changed_sections": []}
    if not isinstance(raw, dict):
        return {**base, "ok": False, "reason": "invalid_freeze", "expected": None, "changed_sections": []}
    expected = str(raw.get("hash") or "")
    schema = int(raw.get("schema") or 1)
    stored = raw.get("snapshot")
    out = {**base, "expected": expected, "schema": schema}
    if schema < FREEZE_SCHEMA:
        if expected == _legacy_hash(snap):
            return {**out, "ok": False, "reason": "freeze_schema_outdated", "legacy_match": True,
                    "changed_sections": []}
        legacy_stored = {k: stored.get(k) for k in _LEGACY_SECTIONS} if isinstance(stored, Mapping) else None
        current_legacy = {k: snap.get(k) for k in _LEGACY_SECTIONS}
        return {**out, "ok": False, "reason": "hash_mismatch", "legacy_match": False,
                "changed_sections": _changed_sections(legacy_stored, current_legacy)}
    if expected == actual:
        return {**out, "ok": True, "reason": None, "changed_sections": []}
    return {**out, "ok": False, "reason": "hash_mismatch", "changed_sections": _changed_sections(stored, snap)}


__all__ = [
    "FREEZE_SCHEMA",
    "config_hash",
    "load_assumed_sharpe",
    "snapshot_settings",
    "verify_freeze",
    "write_freeze",
]
