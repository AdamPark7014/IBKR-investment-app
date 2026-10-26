"""Compare paper drawdown vs OOS / assumed Sharpe. Zero broker orders."""

from __future__ import annotations

from typing import Any


def compare_paper_vs_oos(
    *,
    paper_max_dd: float | None,
    paper_n_points: int,
    assumed_sharpe: float = 0.8,
    expected_oos_sharpe: float | None = None,
    expected_oos_max_dd: float | None = None,
    min_points: int = 0,
) -> dict[str, Any]:
    """``kill_recommend`` only when there are at least ``min_points`` points of real paper equity.

    Autopilot and the CLI pass ``paper_curve.MIN_POINTS_FOR_KILL``: a drawdown over a handful of
    points (or over a curve that is not money) must not recommend killing anything.
    """
    notes: list[str] = ["paper triage only; do not retune live from this JSON"]
    dd_ok: bool | None = None
    kill_recommend = False
    enough = int(paper_n_points) >= int(min_points)

    if paper_max_dd is not None and not enough:
        notes.append(f"kill check off: {int(paper_n_points)} paper points < {int(min_points)} required")
    elif paper_max_dd is not None and expected_oos_max_dd is not None:
        dd_ok = paper_max_dd <= float(expected_oos_max_dd) * 1.25
        kill_recommend = not dd_ok
        notes.append(
            "paper DD within 1.25× OOS max DD"
            if dd_ok
            else "paper DD exceeds 1.25× OOS max DD"
        )
    elif paper_max_dd is not None and assumed_sharpe > 0:
        threshold = min(0.35, 0.15 + 0.25 / max(float(assumed_sharpe), 0.1))
        dd_ok = paper_max_dd <= threshold
        kill_recommend = not dd_ok
        notes.append(
            f"Sharpe-based DD threshold={threshold:.4f} "
            + ("ok" if dd_ok else "breach")
        )
    else:
        notes.append("insufficient paper DD / OOS inputs")

    ratio: float | None = None
    if expected_oos_sharpe is not None and float(expected_oos_sharpe) != 0:
        # Placeholder ratio: assumed / expected (no realized paper Sharpe yet).
        ratio = float(assumed_sharpe) / float(expected_oos_sharpe)

    return {
        "orders_sent": 0,
        "paper_max_dd": paper_max_dd,
        "paper_n_points": int(paper_n_points),
        "min_points": int(min_points),
        "kill_check_active": bool(enough and paper_max_dd is not None),
        "assumed_sharpe": float(assumed_sharpe),
        "expected_oos_sharpe": expected_oos_sharpe,
        "expected_oos_max_dd": expected_oos_max_dd,
        "realized_vs_assumed_sharpe_ratio": ratio,
        "dd_ok": dd_ok,
        "kill_recommend": kill_recommend,
        "notes": notes,
    }


__all__ = ["compare_paper_vs_oos"]
