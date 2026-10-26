"""Day-by-day P&L from walk-forward OOS folds. Zero broker orders."""
from __future__ import annotations

import json
from pathlib import Path


def analyze_fold_equity(eq: list) -> dict:
    vals = [float(x[1]) for x in eq]
    dates = [str(x[0])[:10] for x in eq]
    daily = []
    for i in range(1, len(vals)):
        daily.append(
            {
                "date": dates[i],
                "equity": vals[i],
                "ret": vals[i] / vals[i - 1] - 1.0,
                "pnl": vals[i] - vals[i - 1],
            }
        )
    rets = [d["ret"] for d in daily]
    pnls = [d["pnl"] for d in daily]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {
        "n_days": len(daily),
        "start": vals[0],
        "end": vals[-1],
        "total_pnl": vals[-1] - vals[0],
        "total_return": vals[-1] / vals[0] - 1.0,
        "win_days": len(wins),
        "loss_days": len(losses),
        "flat_days": len(pnls) - len(wins) - len(losses),
        "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
        "best_day_pnl": max(pnls) if pnls else 0.0,
        "worst_day_pnl": min(pnls) if pnls else 0.0,
        "avg_daily_ret": sum(rets) / len(rets) if rets else 0.0,
    }


def main() -> None:
    # Re-read CLI dump is huge; use artifact if thin, else parse from walk-forward stdout file
    camp = sorted(Path("reports").glob("sim_campaign_*/walk-forward.json"))
    text = ""
    if camp:
        text = camp[-1].read_text(encoding="utf-8", errors="ignore")
    # Find the big JSON line with folds
    payload = None
    for line in text.splitlines():
        if line.startswith("{") and '"folds"' in line and "asctime" not in line:
            payload = json.loads(line)
            break
    if payload is None:
        # fallback: reconstruct from known artifact path in campaign terminal is not available;
        # re-run light parse of artifact_wf
        art = Path("reports/artifact_wf_sim_wf.json")
        if not art.is_file():
            print(json.dumps({"error": "no walk-forward data", "orders_sent": 0}))
            return
        payload = json.loads(art.read_text(encoding="utf-8"))

    folds_out = []
    for fd in payload.get("folds") or []:
        eq = fd.get("oos_equity") or []
        if not eq:
            continue
        folds_out.append(
            {
                "fold": fd.get("fold"),
                "params": fd.get("chosen_params"),
                "test_window": (fd.get("dates") or {}).get("test"),
                "oos_metrics": {
                    "cagr": (fd.get("oos") or {}).get("cagr"),
                    "sharpe": (fd.get("oos") or {}).get("sharpe"),
                    "max_dd": (fd.get("oos") or {}).get("max_drawdown"),
                    "expectancy": (fd.get("oos") or {}).get("expectancy"),
                    "trade_count": (fd.get("oos") or {}).get("trade_count"),
                },
                "daily": analyze_fold_equity(eq),
            }
        )

    stitched = payload.get("oos") or {}
    out = {
        "orders_sent": 0,
        "capital_assumed": 100_000.0,
        "stitched_oos": {
            "cagr": stitched.get("cagr"),
            "sharpe": stitched.get("sharpe"),
            "max_dd": stitched.get("max_dd") or stitched.get("max_drawdown"),
            "expectancy": stitched.get("expectancy"),
            "trade_count": stitched.get("trade_count"),
            "total_costs": stitched.get("total_costs"),
        },
        "buy_hold_oos": payload.get("buy_hold_oos"),
        "folds": folds_out,
        "improvement_discipline": [
            "Do NOT retune SMA windows from these OOS folds (playbook / gates).",
            "Cost model ~0.55 bp/order is below IBKR sanity floor 2.5 bp — P&L is optimistic.",
            "Walk-forward expectancy is negative; buy&hold OOS Sharpe/CAGR dominate.",
            "Next real improvement: raise cost realism + multi-ETF research with Tiingo/hold-out, not curve-fit.",
        ],
    }
    path = Path("reports/sim_daily_pnl_summary.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
