# ruff: noqa: E501
"""WARDEN research command panel — self-contained HTML artifact.

Mission-control surface over ``analyze_market`` output. Visual power ≠ edge claim.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


def _esc(x: Any) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def _pct(x: Any, digits: int = 1) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    return f"{v * 100:.{digits}f}%"


def _num(x: Any, digits: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    return f"{v:.{digits}f}"


def render_warden_panel(
    report: Mapping[str, Any],
    *,
    generated_at: Optional[str] = None,
    title: str = "WARDEN",
) -> str:
    """Return a full HTML document for the research command panel."""
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    model = report.get("model") or {}
    posture = report.get("posture") or {}
    regime = report.get("regime") or {}
    sleeve = report.get("sleeve_hypothesis") or {}
    counts = report.get("action_counts") or {}
    ranked = list(report.get("ranked") or [])
    disclaimer = str(report.get("disclaimer") or "")
    engines = list(model.get("engines") or [])

    # Spark bars for sleeve
    cash = float(sleeve.get("cash") or 0)
    core = float(sleeve.get("core_beta") or 0)
    sat = float(sleeve.get("satellite_research") or 0)

    rows_html = []
    for i, r in enumerate(ranked):
        scores = r.get("scores") or {}
        eng = r.get("engines") or {}
        flags = r.get("risk_flags") or []
        action = str(r.get("action") or "WATCH")
        action_cls = {
            "AVOID": "act-avoid",
            "WATCH": "act-watch",
            "RESEARCH_CANDIDATE": "act-cand",
        }.get(action, "act-watch")
        engine_bars = "".join(
            f'<div class="ebar" title="{_esc(k)}">'
            f'<span class="ek">{_esc(k[:3].upper())}</span>'
            f'<i style="--v:{float(eng.get(k) or 0):.4f}"></i>'
            f"</div>"
            for k in (
                "trend",
                "relative_strength",
                "risk_quality",
                "momentum_quality",
                "volume_thrust",
                "bench_decoupling",
                "mean_reversion_pressure",
            )
            if k in eng or True
        )
        flag_html = (
            "".join(f'<span class="flag">{_esc(f)}</span>' for f in flags)
            if flags
            else '<span class="flag quiet">clear</span>'
        )
        rows_html.append(
            f"""
<article class="sym-row" data-action="{_esc(action)}" style="--i:{i}">
  <button type="button" class="sym-head" aria-expanded="false">
    <span class="rank">{i + 1:02d}</span>
    <span class="sym">{_esc(r.get("symbol"))}</span>
    <span class="px">{_esc(_num(r.get("last_close"), 2))}</span>
    <span class="comp">{_esc(_num(scores.get("composite"), 3))}</span>
    <span class="conf">{_esc(_num(scores.get("confidence"), 2))}</span>
    <span class="pill {_esc(action_cls)}">{_esc(action.replace("_", " "))}</span>
  </button>
  <div class="sym-body" hidden>
    <div class="engine-grid">{engine_bars}</div>
    <div class="meta-line">
      <span>RS {_esc(_num(r.get("rs_percentile"), 2))}</span>
      <span>Vol {_esc(_num(r.get("vol_21_ann"), 2))}</span>
      <span>DD63 {_esc(_pct(r.get("max_dd_63")))}</span>
      <span>Hit {_esc(_pct(r.get("hit_rate_63")))}</span>
      <span>Corr {_esc(_num(r.get("corr_to_bench_63"), 2))}</span>
    </div>
    <div class="flags">{flag_html}</div>
  </div>
</article>
"""
        )

    engines_strip = "".join(f"<li>{_esc(e)}</li>" for e in engines)
    payload_json = json.dumps(dict(report), default=str, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)} · Research Command</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
:root {{
  --bg0: #0a0e13;
  --bg1: #121922;
  --bg2: #1a2430;
  --ink: #e7eef6;
  --muted: #8b9aab;
  --line: rgba(231,238,246,0.10);
  --amber: #d4a04a;
  --teal: #3d9a8b;
  --coral: #c45c4a;
  --steel: #6f8499;
  --ok: #7aaf6b;
  --font-display: "Syne", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; min-height: 100%; }}
body {{
  font-family: var(--font-mono);
  color: var(--ink);
  background:
    radial-gradient(1200px 700px at 12% -10%, rgba(212,160,74,0.14), transparent 55%),
    radial-gradient(900px 600px at 95% 0%, rgba(61,154,139,0.10), transparent 50%),
    linear-gradient(165deg, var(--bg0), #0f1620 45%, var(--bg0));
  background-attachment: fixed;
}}
body::before {{
  content: "";
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(rgba(231,238,246,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(231,238,246,0.03) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
}}
.wrap {{ position: relative; z-index: 1; max-width: 1180px; margin: 0 auto; padding: 0 1.25rem 3rem; }}

/* Hero — one composition */
.hero {{
  min-height: 100vh;
  display: grid;
  align-content: center;
  gap: 1.25rem;
  padding: 3.5rem 0 2.5rem;
  animation: rise 0.9s ease-out both;
}}
@keyframes rise {{
  from {{ opacity: 0; transform: translateY(18px); }}
  to {{ opacity: 1; transform: none; }}
}}
.brand {{
  font-family: var(--font-display);
  font-weight: 800;
  font-size: clamp(3.4rem, 12vw, 6.5rem);
  letter-spacing: -0.04em;
  line-height: 0.92;
  margin: 0;
  background: linear-gradient(120deg, var(--ink) 20%, var(--amber) 55%, var(--teal) 95%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}}
.tagline {{
  max-width: 34rem;
  font-size: 0.95rem;
  color: var(--muted);
  line-height: 1.55;
  margin: 0;
}}
.status-row {{
  display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem;
  align-items: center; margin-top: 0.5rem;
}}
.led {{
  display: inline-flex; align-items: center; gap: 0.45rem;
  font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--amber);
}}
.led i {{
  width: 0.55rem; height: 0.55rem; border-radius: 1px;
  background: var(--amber);
  animation: blink 2.4s ease-in-out infinite;
}}
@keyframes blink {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.35; }}
}}
.posture {{
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.15rem;
  letter-spacing: 0.04em;
  color: var(--ink);
}}
.cta-row {{ display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.75rem; }}
.cta {{
  appearance: none; border: 1px solid var(--line);
  background: linear-gradient(180deg, var(--bg2), var(--bg1));
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.7rem 1rem;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, transform 0.2s;
}}
.cta:hover {{ border-color: var(--amber); color: var(--amber); transform: translateY(-1px); }}
.cta.primary {{ border-color: rgba(212,160,74,0.45); color: var(--amber); }}

section {{ margin-top: 2.5rem; animation: rise 0.8s ease-out both; animation-delay: 0.12s; }}
.sec-h {{
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 700;
  margin: 0 0 0.35rem;
  letter-spacing: -0.02em;
}}
.sec-p {{ margin: 0 0 1.1rem; color: var(--muted); font-size: 0.8rem; max-width: 40rem; }}

.matrix {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.65rem;
}}
.matrix li {{
  list-style: none;
  margin: 0;
  padding: 0.85rem 0.9rem;
  background: linear-gradient(160deg, rgba(26,36,48,0.9), rgba(18,25,34,0.95));
  border-left: 2px solid var(--teal);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
.matrix ul {{ margin: 0; padding: 0; display: contents; }}

.regime-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}}
@media (max-width: 800px) {{ .regime-grid {{ grid-template-columns: 1fr 1fr; }} }}
.stat {{
  padding: 1rem 1.05rem;
  background: rgba(18,25,34,0.85);
  border-top: 1px solid var(--line);
}}
.stat .k {{ display: block; font-size: 0.65rem; color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase; }}
.stat .v {{ display: block; margin-top: 0.35rem; font-family: var(--font-display); font-size: 1.35rem; font-weight: 700; }}

.sleeve {{
  display: grid; gap: 0.55rem; margin-top: 0.5rem;
}}
.sleeve .bar {{
  display: grid; grid-template-columns: 7.5rem 1fr 3rem; gap: 0.6rem; align-items: center;
  font-size: 0.72rem; color: var(--muted);
}}
.sleeve .track {{
  height: 0.55rem; background: rgba(231,238,246,0.06); overflow: hidden;
}}
.sleeve .fill {{
  display: block; height: 100%; width: 0;
  background: linear-gradient(90deg, var(--steel), var(--amber));
  animation: fillbar 1.1s ease-out forwards;
}}
.sleeve .fill.core {{ background: linear-gradient(90deg, var(--teal), #5fb8a8); animation-delay: 0.1s; }}
.sleeve .fill.sat {{ background: linear-gradient(90deg, var(--amber), #e0b86a); animation-delay: 0.2s; }}
@keyframes fillbar {{ to {{ width: var(--w); }} }}

.board {{ display: grid; gap: 0.45rem; }}
.sym-row {{
  background: rgba(18,25,34,0.72);
  border: 1px solid transparent;
  border-bottom-color: var(--line);
  animation: rise 0.55s ease-out both;
  animation-delay: calc(0.04s * var(--i));
}}
.sym-row[data-action="RESEARCH_CANDIDATE"] {{ border-left: 2px solid var(--teal); }}
.sym-row[data-action="AVOID"] {{ border-left: 2px solid var(--coral); }}
.sym-row[data-action="WATCH"] {{ border-left: 2px solid var(--steel); }}
.sym-head {{
  width: 100%;
  display: grid;
  grid-template-columns: 2.2rem 4.5rem 4.5rem 4.2rem 3.8rem 1fr;
  gap: 0.5rem;
  align-items: center;
  padding: 0.75rem 0.85rem;
  background: transparent;
  border: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}}
@media (max-width: 700px) {{
  .sym-head {{ grid-template-columns: 2rem 3.5rem 1fr; }}
  .sym-head .px, .sym-head .comp, .sym-head .conf {{ display: none; }}
}}
.rank {{ color: var(--muted); font-size: 0.7rem; }}
.sym {{ font-family: var(--font-display); font-weight: 700; font-size: 1.05rem; letter-spacing: 0.02em; }}
.pill {{
  justify-self: end;
  font-size: 0.62rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.28rem 0.45rem;
  border: 1px solid var(--line);
}}
.act-cand {{ color: var(--teal); border-color: rgba(61,154,139,0.45); }}
.act-avoid {{ color: var(--coral); border-color: rgba(196,92,74,0.45); }}
.act-watch {{ color: var(--steel); }}
.sym-body {{ padding: 0 0.85rem 0.95rem; }}
.engine-grid {{
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.35rem;
  margin-bottom: 0.65rem;
}}
@media (max-width: 800px) {{ .engine-grid {{ grid-template-columns: repeat(4, 1fr); }} }}
.ebar {{
  display: grid; gap: 0.2rem;
}}
.ebar .ek {{ font-size: 0.55rem; color: var(--muted); letter-spacing: 0.04em; }}
.ebar i {{
  display: block; height: 0.35rem;
  background: rgba(231,238,246,0.08);
  position: relative;
}}
.ebar i::after {{
  content: "";
  position: absolute; left: 0; top: 0; bottom: 0;
  width: calc(var(--v) * 100%);
  background: var(--amber);
}}
.meta-line {{
  display: flex; flex-wrap: wrap; gap: 0.75rem;
  font-size: 0.68rem; color: var(--muted); margin-bottom: 0.45rem;
}}
.flags {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
.flag {{
  font-size: 0.58rem; letter-spacing: 0.05em; text-transform: uppercase;
  padding: 0.2rem 0.35rem; border: 1px solid rgba(196,92,74,0.35); color: var(--coral);
}}
.flag.quiet {{ border-color: var(--line); color: var(--muted); }}

.disclaimer {{
  margin-top: 2.5rem;
  padding: 1rem 0;
  border-top: 1px solid var(--line);
  font-size: 0.72rem;
  color: var(--muted);
  line-height: 1.55;
  max-width: 46rem;
}}
.foot {{
  margin-top: 1rem;
  font-size: 0.65rem;
  color: var(--steel);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero" id="top">
    <p class="led"><i></i> Systems nominal · research mode</p>
    <h1 class="brand">{_esc(title)}</h1>
    <p class="tagline">
      Multi-engine market command surface. Ranks where <em>not</em> to bleed first,
      then which names deserve walk-forward re-runs — never a promise of mega returns.
    </p>
    <div class="status-row">
      <span class="posture">{_esc(posture.get("code") or "NEUTRAL")}</span>
      <span style="color:var(--muted);font-size:0.78rem">{_esc(posture.get("detail") or "")}</span>
    </div>
    <div class="cta-row">
      <a class="cta primary" href="#board">Open triage board</a>
      <a class="cta" href="#engines">Inspect engines</a>
      <a class="cta" href="#sleeve">Sleeve hypothesis</a>
    </div>
    <p class="foot">Model {_esc(model.get("name") or "WARDEN")} v{_esc(model.get("version") or "—")} · {_esc(ts)} · {_esc(report.get("n_symbols"))} names</p>
  </header>

  <section id="engines">
    <h2 class="sec-h">Engine matrix</h2>
    <p class="sec-p">Seven concurrent scorers + disagreement-aware confidence. Complexity is process power, not claimed edge.</p>
    <div class="matrix"><ul>{engines_strip}</ul></div>
  </section>

  <section id="regime">
    <h2 class="sec-h">Regime & counts</h2>
    <p class="sec-p">Universe posture feeds cash bias before any name is promoted.</p>
    <div class="regime-grid">
      <div class="stat"><span class="k">Breadth &gt; SMA200</span><span class="v">{_esc(_pct(regime.get("breadth_above_sma200")))}</span></div>
      <div class="stat"><span class="k">Bench above SMA200</span><span class="v">{_esc(regime.get("benchmark_above_sma200"))}</span></div>
      <div class="stat"><span class="k">Risk-on proxy</span><span class="v">{_esc(regime.get("risk_on_proxy"))}</span></div>
      <div class="stat"><span class="k">Cash bias</span><span class="v">{_esc(regime.get("cash_bias"))}</span></div>
      <div class="stat"><span class="k">Avoid</span><span class="v">{_esc(counts.get("AVOID", 0))}</span></div>
      <div class="stat"><span class="k">Watch</span><span class="v">{_esc(counts.get("WATCH", 0))}</span></div>
      <div class="stat"><span class="k">Research</span><span class="v">{_esc(counts.get("RESEARCH_CANDIDATE", 0))}</span></div>
      <div class="stat"><span class="k">Benchmark</span><span class="v">{_esc(report.get("benchmark"))}</span></div>
    </div>
  </section>

  <section id="sleeve">
    <h2 class="sec-h">Sleeve hypothesis</h2>
    <p class="sec-p">{_esc(sleeve.get("note") or "Paper-stage weights only.")}</p>
    <div class="sleeve">
      <div class="bar"><span>Cash</span><div class="track"><span class="fill" style="--w:{cash * 100:.1f}%"></span></div><span>{cash * 100:.0f}%</span></div>
      <div class="bar"><span>Core beta</span><div class="track"><span class="fill core" style="--w:{core * 100:.1f}%"></span></div><span>{core * 100:.0f}%</span></div>
      <div class="bar"><span>Satellite</span><div class="track"><span class="fill sat" style="--w:{sat * 100:.1f}%"></span></div><span>{sat * 100:.0f}%</span></div>
    </div>
  </section>

  <section id="board">
    <h2 class="sec-h">Triage board</h2>
    <p class="sec-p">Tap a name to expand the engine stack. RESEARCH CANDIDATE ≠ buy.</p>
    <div class="board">
      {"".join(rows_html) if rows_html else "<p class='sec-p'>No symbols loaded.</p>"}
    </div>
  </section>

  <p class="disclaimer">{_esc(disclaimer)}</p>
  <p class="foot"><a href="#top" style="color:var(--amber);text-decoration:none">Return to command</a></p>
</div>
<script id="warden-data" type="application/json">{html.escape(payload_json, quote=False)}</script>
<script>
document.querySelectorAll(".sym-head").forEach((btn) => {{
  btn.addEventListener("click", () => {{
    const body = btn.nextElementSibling;
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", open ? "false" : "true");
    if (body) body.hidden = open;
  }});
}});
</script>
</body>
</html>
"""


def write_warden_panel(
    report: Mapping[str, Any],
    path: str,
    *,
    generated_at: Optional[str] = None,
) -> str:
    """Write HTML panel to ``path``; return the path."""
    from pathlib import Path

    html_doc = render_warden_panel(report, generated_at=generated_at)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_doc, encoding="utf-8")
    return str(p)
