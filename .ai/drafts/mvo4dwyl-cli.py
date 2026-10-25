    payload = run_autopilot(use_ai=use_ai, pack=pack, open_ui=open_ui)
    slim = {
        "exp_id": payload.get("exp_id"),
        "orders_sent": payload.get("orders_sent", 0),
        "brief_source": (payload.get("brief") or {}).get("source"),
        "artifact_html": payload.get("latest_html") or payload.get("artifact_html"),
        "disclaimer": payload.get("disclaimer"),
    }
    typer.echo(_json.dumps(_noneify(slim), ensure_ascii=False, separators=(",", ":")))


@app.command("ibc-checklist")
def ibc_checklist() -> None:
    """Print a manual paper Gateway/IBC checklist as JSON (no installs, no orders)."""
    import json as _json

    from .ibc_checklist import build_ibc_checklist

    typer.echo(_json.dumps(_noneify(build_ibc_checklist()), ensure_ascii=False, separators=(",", ":")))


@app.command("slippage-report")
def slippage_report(
    path: str = typer.Option(
        "data/slippage_ledger.jsonl",
        "--path",
        help="Path to slippage JSONL ledger.",
    ),
    window_days: int = typer.Option(
        30,
        "--window-days",
        help="Lookback window in days.",
    ),
) -> None:
    """Print slippage ledger summary as JSON (zero orders)."""
    import json as _json

    from .slippage_report import summarize_cli

    typer.echo(
        _json.dumps(_noneify(summarize_cli(path, window_days)), ensure_ascii=False, separators=(",", ":"))
    )


@app.command("paper-reconcile")
def paper_reconcile(
    window_days: int = typer.Option(
        30,
        "--window-days",
        help="Slippage ledger summary lookback when data/slippage_ledger.jsonl exists.",
    ),
) -> None:
    """Compare DecisionEngine targets vs paper_positions.json; no broker orders."""
    import json as _json
    from pathlib import Path as _Path

    from .shadow import desired_from_decisions, log_shadow_snapshot

    s = AppSettings()
    s.resolve_paths()
    data = load_universe_v2(s)
    engine = DecisionEngine(s)
    decisions = engine.generate(data)
    desired = desired_from_decisions(decisions)

    held: dict[str, float] = {}
    held_path = _Path(s.data.data_dir) / "paper_positions.json"
    if held_path.exists():
        raw = _json.loads(held_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            held = {str(k): float(v) for k, v in raw.items()}

    out: dict[str, Any] = log_shadow_snapshot(desired, held, tag="paper-reconcile")
    out["orders_sent"] = 0
    out["shadow_held_source"] = str(held_path) if held_path.exists() else None

    ledger_path = _Path(s.data.data_dir) / "slippage_ledger.jsonl"
    if ledger_path.exists():
        try:
            from . import slippage_ledger as _slippage_ledger

            out["slippage"] = _slippage_ledger.summarize(ledger_path, window_days)
        except ImportError:
            pass

    typer.echo(_json.dumps(_noneify(out), ensure_ascii=False, separators=(",", ":")))


@app.command()
def kill() -> None:
    s = AppSettings()
    s.resolve_paths()
    activate_killswitch(s.risk.killswitch_file)
    rprint({"kill_switch": True})


@app.command("clear-kill")
def clear_kill() -> None:
    s = AppSettings()
    s.resolve_paths()
    clear_killswitch(s.risk.killswitch_file)
    rprint({"kill_switch": False})


@app.command("regime-fit")
def regime_fit(symbol: Optional[str] = None, n_components: int = 2, exp_id: Optional[str] = None) -> None:
    """
    P6 Regime Engine: learned regimes via GaussianMixture on benchmark returns/volatility.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    bench = s.universe.benchmark if s.universe.benchmark in data else next(iter(data.keys()))
    model, rep = fit_gmm_regime(data[bench]["close"], n_components=n_components)
    from datetime import datetime as _dt

    run_id = exp_id or _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
    # Save CSV report
    import os

    out_csv = os.path.join(s.data.reports_dir, f"regime_{run_id}.csv")
    rep.to_csv(out_csv, index=True)
    # Summary
    counts = rep["regime"].value_counts().to_dict()
    cols = [c for c in ["ret_1d", "vol_20"] if c in rep.columns]
    means = rep.groupby("regime")[cols].mean().to_dict() if cols else {}
    rprint(
        {
            "report": out_csv,
            "components": n_components,
            "counts": counts,
            "means": means,
        }
    )


@app.command("signal-validate")
def signal_validate(
    symbol: Optional[str] = None,
    direction: str = "long_only",
    exp_id: Optional[str] = None,
) -> None:
    """
    P7 Signal Validation: CV evaluation of SMA signal against forward returns.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    folds, agg = validate_sma_signal(
        data,
        sym,
        fast=int(s.strategy.params.get("fast_window", 10)),
        slow=int(s.strategy.params.get("slow_window", 30)),
        direction=direction,
    )
    # Buy & Hold for comparison (benchmark may have been dropped by validation)
    bench = s.universe.benchmark if s.universe.benchmark in data else next(iter(data))
    px = data[bench]["close"].astype(float)
    eq = (100_000.0 / float(px.iloc[0])) * px
    bh_ret = eq.pct_change().fillna(0.0)
    ann = np.sqrt(252.0)
    bh_stats = {
        "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (252 / max(len(eq), 1)) - 1.0),
        "sharpe": float((bh_ret.mean() / (bh_ret.std(ddof=0) or 1e-9)) * ann),
        "max_dd": float((eq / eq.cummax() - 1.0).min()),
    }
    rprint(
        {
            "symbol": sym,
            "direction": direction,
            "cv": [{"mean": f.mean_ret, "sharpe": f.sharpe, "n": f.n_obs} for f in folds],
            "cv_aggregate": {"mean": agg.mean_ret, "sharpe": agg.sharpe, "n": agg.n_obs},
            "buy_hold": bh_stats,
        }
    )


@app.command("run-with-risk")
def run_with_risk(
    symbol: Optional[str] = None,
    exp_id: Optional[str] = None,
    risk_on_threshold: Optional[float] = None,
) -> None:
    """
    P8 Risk Integration: regime veto + volatility-target sizing. No live orders; prints decision.
    """
    s = AppSettings()
    s.resolve_paths()
    warn_unknown_trading_env()
    if symbol:
        s.universe.symbols = [symbol]
    data = load_universe_v2(s)
    sym = s.universe.symbols[0]
    # Historical regime probabilities (expanding, min window)
    bench = s.universe.benchmark if s.universe.benchmark in data else sym
    bench_close = data[bench]["close"].astype(float)
    feats_all = build_regime_features(bench_close)
    min_train = 60
    probs = []
    idxs = list(feats_all.index)
    for i in range(len(idxs)):
        tr_idx = idxs[: i + 1]
        if len(tr_idx) < min_train:
            probs.append(0.0)
            continue
        model, _ = fit_gmm_regime(bench_close.reindex(tr_idx), n_components=2, 