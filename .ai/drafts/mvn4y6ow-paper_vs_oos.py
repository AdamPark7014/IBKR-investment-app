def compare_paper_vs_oos(*, paper_max_dd: float | None, paper_n_points: int, assumed_sharpe: float = 0.8, expected_oos_sharpe: float | None = None, expected_oos_max_dd: float | None = None) -> dict:
    if paper_max_dd is not None and expected_oos_max_dd is not None:
        dd_ok = paper_max_dd <= expected_oos_max_dd * 1.25
        kill_recommend = not dd_ok
        notes = ["Paper max DD exceeds safety margin vs OOS expectations.", "Do not retune live parameters based on this single run."]
    elif paper_max_dd is not None and assumed_sharpe:
        threshold = min(0.35, 0.15 + 0.25 / assumed_sharpe)
        dd_ok = paper_max_dd <= threshold
        kill_recommend = paper_max_dd > threshold if not dd_ok else False
        notes = ["Using Sharpe-based alert threshold.", "Do not retune live parameters based on this single run."]
    else:
        dd_ok = None
        kill_recommend = False
        notes = ["Insufficient data for drawdown comparison.", "Do not retune live parameters."]
    
    if expected_oos_sharpe and paper_max_dd and assumed_sharpe:
        realized_vs_assumed_sharpe_ratio = assumed_sharpe / expected_oos_sharpe if expected_oos_sharpe else None
    elif expected_oos_sharpe is not None:
        realized_vs_assumed_sharpe_ratio = None
    else:
        realized_vs_assumed_sharpe_ratio = None

    return {
        "orders_sent": 0,
        "paper_max_dd": paper_max_dd,
        "paper_n_points": paper_n_points,
        "assumed_sharpe": assumed_sharpe,
        "expected_oos_sharpe": expected_oos_sharpe,
        "expected_oos_max_dd": expected_oos_max_dd,
        "realized_vs_assumed_sharpe_ratio": realized_vs_assumed_sharpe_ratio,
        "dd_ok": dd_ok,
        "kill_recommend": kill_recommend,
        "notes": notes
    }