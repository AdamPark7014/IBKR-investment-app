from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path
from typing import Any, Dict

import plotly.graph_objects as go

from .engine import BacktestResult
from .metrics import cost_metrics_dict, stats_to_dict

_COST_ROWS = (
    ("n_orders", "Orders", "{:d}"),
    ("notional_traded", "Notional traded (USD)", "{:,.2f}"),
    ("turnover", "Turnover (x initial equity)", "{:.4f}"),
    ("total_commission", "Commission (USD)", "{:,.2f}"),
    ("total_reg_fees", "Regulatory fees, sells (USD)", "{:,.2f}"),
    ("total_slippage", "Half-spread / slippage (USD)", "{:,.2f}"),
    ("total_impact", "Market impact (USD)", "{:,.2f}"),
    ("total_costs", "All-in costs (USD)", "{:,.2f}"),
    ("avg_cost_bps_per_order", "Avg all-in cost per order (bps)", "{:.2f}"),
    ("cost_drag_annual_pct", "Cost drag (% of initial equity / year)", "{:.3f}"),
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def stats_json(result: BacktestResult) -> Dict[str, Any]:
    """All metrics as a JSON-safe dict (NaN/inf -> null)."""
    return {k: _json_safe(v) for k, v in stats_to_dict(result.stats).items()}


def _cost_table_html(result: BacktestResult) -> str:
    costs = cost_metrics_dict(result.stats)
    rows = []
    for key, label, fmt in _COST_ROWS:
        raw = costs.get(key)
        text = "n/a"
        if raw is not None:
            try:
                text = fmt.format(int(raw) if fmt == "{:d}" else float(raw))
            except (TypeError, ValueError):
                text = "n/a"
        rows.append(f"<tr><td>{escape(label)}</td><td style=\"text-align:right\">{escape(text)}</td></tr>")
    note = (
        "Costs per COST_MODEL.md: IBKR commission + SEC/FINRA/CAT fees on sells + half-spread + "
        "square-root impact. IBKR Pro clients' observed all-in cost is 2.5-4 bps (jul-2026); a lower "
        "average is a sign the model is too cheap."
    )
    return (
        "<section id=\"ibtrader-costs\" style=\"font-family:sans-serif;max-width:720px;margin:1em auto\">"
        "<h2>Execution costs</h2>"
        "<table style=\"border-collapse:collapse;width:100%\">"
        + "".join(rows)
        + "</table>"
        f"<p style=\"color:#555;font-size:0.9em\">{escape(note)}</p>"
        "</section>"
    )


def save_equity_report(result: BacktestResult, out_dir: str, name: str = "report") -> str:
    """Write ``<out_dir>/<name>.html``: equity curve + execution-cost table + embedded stats JSON."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=result.equity_curve.index, y=result.equity_curve.values, name="Equity")
    )
    fig.update_layout(title="Equity Curve", xaxis_title="Date", yaxis_title="Equity (USD)")
    out_html = str(Path(out_dir) / f"{name}.html")
    fig.write_html(out_html)
    # Append the cost table and a machine-readable copy of every metric to the same page.
    payload = json.dumps(stats_json(result), ensure_ascii=False, allow_nan=False)
    extra = (
        _cost_table_html(result)
        + "<script type=\"application/json\" id=\"ibtrader-stats\">"
        + payload.replace("</", "<\\/")
        + "</script>"
    )
    html = Path(out_html).read_text(encoding="utf-8")
    if "</body>" in html:
        html = html.replace("</body>", extra + "</body>", 1)
    else:
        html = html + extra
    Path(out_html).write_text(html, encoding="utf-8")
    return out_html

