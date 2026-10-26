"""Summarize sim campaign P&L metrics from artifacts (no broker orders)."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _extract_json_objects(text: str) -> list[dict]:
    objs: list[dict] = []
    # Prefer lines that are pure JSON
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("{") or "asctime" in s:
            continue
        try:
            objs.append(json.loads(s.replace("'", '"')))
        except json.JSONDecodeError:
            pass
    # Also try whole-file JSON after last log line
    m = re.search(r"\{[^{].*\"oos\".*\}", text, re.DOTALL)
    if m:
        try:
            objs.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            pass
    return objs


def _metrics_from_artifact(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    stats = raw.get("stats") or raw.get("metrics") or {}
    if not stats and "cagr" in raw:
        stats = raw
    equity = raw.get("equity") or raw.get("equity_curve")
    start = end = total_ret = None
    if isinstance(equity, list) and len(equity) >= 2:
        # [[ts, v], ...] or list of values
        def _val(x):
            return float(x[1] if isinstance(x, (list, tuple)) else x)

        start = _val(equity[0])
        end = _val(equity[-1])
        if start:
            total_ret = end / start - 1.0
    return {
        "source": str(path),
        "cagr": stats.get("cagr"),
        "sharpe": stats.get("sharpe"),
        "max_dd": stats.get("max_dd") or stats.get("max_drawdown"),
        "trade_count": stats.get("trade_count"),
        "total_commission": stats.get("total_commission") or stats.get("fees"),
        "expectancy": stats.get("expectancy"),
        "profit_factor": stats.get("profit_factor"),
        "equity_start": start,
        "equity_end": end,
        "total_return": total_ret,
    }


def main() -> None:
    reports = Path("reports")
    summary: dict = {"orders_sent": 0, "note": "simulation only; not advice; do not retune live"}
    arts = {
        "backtest": reports / "artifact_sim_bt.json",
        "walk_forward": reports / "artifact_wf_sim_wf.json",
        "risk": None,
    }
    for p in reports.glob("artifact_risk_*.json"):
        arts["risk"] = p
        break
    out = {}
    for name, p in arts.items():
        if p and p.is_file():
            out[name] = _metrics_from_artifact(p)
    # research smoke
    rs = reports / "sim_research_smoke.json"
    if rs.is_file():
        text = rs.read_text(encoding="utf-8", errors="ignore")
        for line in reversed(text.splitlines()):
            if line.startswith("{") and "honest_report" in line:
                try:
                    j = json.loads(line)
                    c = (j.get("candidates") or [{}])[0]
                    oos = c.get("oos") or {}
                    out["research_smoke_oos"] = {
                        "gate": c.get("gate"),
                        "cagr": oos.get("cagr"),
                        "sharpe": oos.get("sharpe"),
                        "max_dd": oos.get("max_dd"),
                        "expectancy": oos.get("expectancy"),
                        "trade_count": oos.get("trade_count"),
                        "verdict": (j.get("honest_report") or {}).get("verdict"),
                        "cost_model_suspicious": (j.get("honest_report") or {}).get(
                            "cost_model_suspicious"
                        ),
                    }
                    bh = c.get("buy_hold_oos") or {}
                    out["buy_hold_oos"] = {
                        "cagr": bh.get("cagr"),
                        "sharpe": bh.get("sharpe"),
                        "max_dd": bh.get("max_dd"),
                    }
                except json.JSONDecodeError:
                    pass
                break
    summary["runs"] = out
    # Day-level P&L from walk-forward stitched oos equity if present in wf artifact
    wf = reports / "artifact_wf_sim_wf.json"
    if wf.is_file():
        raw = json.loads(wf.read_text(encoding="utf-8"))
        # try common shapes
        eq = None
        for key in ("stitched_oos_equity", "oos_equity", "equity"):
            if key in raw:
                eq = raw[key]
                break
        summary_path = reports / "sim_campaign_summary.json"
        if eq and isinstance(eq, list) and len(eq) > 1:
            vals = [float(x[1] if isinstance(x, (list, tuple)) else x) for x in eq]
            daily = []
            for i in range(1, len(vals)):
                daily.append(vals[i] / vals[i - 1] - 1.0)
            wins = sum(1 for r in daily if r > 0)
            losses = sum(1 for r in daily if r < 0)
            summary["oos_daily"] = {
                "n_days": len(daily),
                "win_days": wins,
                "loss_days": losses,
                "flat_days": len(daily) - wins - losses,
                "avg_daily_ret": sum(daily) / len(daily),
                "best_day": max(daily),
                "worst_day": min(daily),
                "start_equity": vals[0],
                "end_equity": vals[-1],
                "total_return": vals[-1] / vals[0] - 1.0,
            }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
