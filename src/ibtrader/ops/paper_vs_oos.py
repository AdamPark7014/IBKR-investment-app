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
) -> dict[str, Any]:
    notes: list[str] = ["paper triage only; do not retune live from this JSON"]
    dd_ok: bool | None = None
    kill_recommend = False

    if paper_max_dd is not None and expected_oos_max_dd is not None:
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
        "assumed_sharpe": float(assumed_sharpe),
        "expected_oos_sharpe": expected_oos_sharpe,
        "expected_oos_max_dd": expected_oos_max_dd,
        "realized_vs_assumed_sharpe_ratio": ratio,
        "dd_ok": dd_ok,
        "kill_recommend": kill_recommend,
        "notes": notes,
    }


__all__ = ["compare_paper_vs_oos"]
