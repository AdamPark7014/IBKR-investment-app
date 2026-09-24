from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from .engine import BacktestResult


def save_equity_report(result: BacktestResult, out_dir: str, name: str = "report") -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=result.equity_curve.index, y=result.equity_curve.values, name="Equity")
    )
    fig.update_layout(title="Equity Curve", xaxis_title="Date", yaxis_title="Equity (USD)")
    out_html = str(Path(out_dir) / f"{name}.html")
    fig.write_html(out_html)
    return out_html

