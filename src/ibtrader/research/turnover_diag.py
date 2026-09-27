"""Turnover / holding-cost diagnostics for research candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence


def diagnose_turnover(
    candidates: Sequence[Mapping[str, Any]],
    *,
    high_turnover_threshold: float = 8.0,
) -> Dict[str, Any]:
    """Flag candidates whose OOS turnover looks incompatible with modest edge.

    Threshold is a research heuristic (annualized turnover multiple of equity),
    not a hard risk limit. High turnover + weak/failed gates ⇒ cost-fragile.
    """
    rows: List[Dict[str, Any]] = []
    flagged = 0
    for c in candidates:
        oos = c.get("oos") or {}
        turn = oos.get("turnover")
        try:
            turn_f = float(turn) if turn is not None else float("nan")
        except (TypeError, ValueError):
            turn_f = float("nan")
        sharpe = oos.get("sharpe")
        try:
            sh_f = float(sharpe) if sharpe is not None else float("nan")
        except (TypeError, ValueError):
            sh_f = float("nan")
        high = bool(turn_f == turn_f and turn_f >= high_turnover_threshold)
        fragile = bool(high and (not c.get("gate_passed") or (sh_f == sh_f and sh_f < 0.25)))
        if fragile:
            flagged += 1
        rows.append(
            {
                "candidate_id": c.get("candidate_id"),
                "turnover": turn_f if turn_f == turn_f else None,
                "oos_sharpe": sh_f if sh_f == sh_f else None,
                "gate_passed": bool(c.get("gate_passed")),
                "high_turnover": high,
                "turnover_fragile": fragile,
            }
        )
    return {
        "n_candidates": len(rows),
        "n_turnover_fragile": flagged,
        "high_turnover_threshold": float(high_turnover_threshold),
        "rows": rows,
        "note": (
            "High turnover with weak OOS Sharpe is a classic AQR-style reject: "
            "gross looks fine, net dies. Research diagnostic only."
        ),
    }
