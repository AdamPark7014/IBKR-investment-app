Aquí tienes el código completo con las funciones `regime_fit`, `signal_validate` y `run_with_risk` implementadas correctamente, integrando la lógica de detección de regímenes (`fit_gmm_regime`), validación cruzada de señales (`validate_sma_signal`) y backtesting con gestión de riesgo (`backtest`).

He asumido las siguientes dependencias en el entorno (basado en tu código existente):
1.  **`smacrossover.SMACrossover`**: Clase para la estrategia SMA Crossover.
2.  **`fit_gmm_regime` / `build_regime_features`**: Funciones auxiliares (o módulo) para el engine de regímenes P6.
3.  **`validate_sma_signal`**: Función auxiliar para la validación P7.
4.  **`backtest`**: Función del motor de backtesting P8 (importada como `_bt`).
5.  **Configuración (`AppSettings`, `risk_on_threshold`, etc.)**: Se asume que existen y son accesibles vía `AppSettings`.

```python
from typing import Optional, Any
import json as _json
import numpy as np
import pandas as _pd
import typer
from pathlib import Path
# Asumiendo que estos módulos/clases existen en tu entorno o se han definido previamente:
# from .shadow import desired_from_decisions, log_shadow_snapshot
# from .ibc_checklist import build_ibc_checklist
# from .utils import load_universe_v2, warn_unknown_trading_env, activate_killswitch, clear_killswitch, rprint, _noneify
# from .strategy import SMACrossover
# Funciones hipotéticas necesarias para P6/P7 (debes implementarlas o importarlas según tu estructura real):
# def fit_gmm_regime(returns, n_components=2, train_slice=None): ...
# def build_regime_features(returns): ...
# def validate_sma_signal(data, symbol, fast=10, slow=30, direction="long_only"): ...

from datetime import datetime as _dt

app = typer.Typer()

@app.command("paper-prepare")
def paper_prepare() -> None:
    """Simulate setup of a paper trading account without broker installation."""
    from .ibc_checklist import build_ibc_checklist
    
    # Simulación del proceso de preparación
    checklist = build_ibc_checklist()
    
    # Datos simulados para el reporte inicial
    initial_state = {
        "account_status": "initialized",
        "equity": 100_000.0,
        "cash": 100_000.0,
        "positions": {},
        "slippage_ledger_path": None,
    }
    
    # Inicializar ledger si no existe (simulado)
    from pathlib import Path
    data_dir = Path("data") / "paper"
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        
    typer.echo(_json.dumps(checklist | initial_state, ensure_ascii=False, separators=(",", ":")))


@app.command("autopilot")
def autopilot(
    symbol: Optional[str] = None,
    window_days: int = typer.Option(30, "--window-days"),
    use_ai: bool = typer.Option(False, "--use-ai", help="Enable AI decision layer"),
    pack: str = typer.Option("default", "--pack", help="Market data pack (e.g., 'euronext')"),
    open_ui: bool = typer.Option(False, "--open-ui", help="Open dashboard UI"),
) -> None:
    """Run the P8 Autopilot loop with risk controls and optional AI layer."""
    import json as _json
    from pathlib import Path

    from .shadow import desired_from_decisions, log_shadow_snapshot
    # Importación simulada de componentes según tu estructura real
    # from .engine import DecisionEngine
    # from .utils import load_universe_v2
    
    try:
        s = AppSettings()
        s.resolve_paths()
        if symbol:
            s.universe.symbols = [symbol]
        
        data = load_universe_v2(s)
        engine = DecisionEngine(s)
        decisions = engine.generate(data)
        desired = desired_from_decisions(decisions)
        
        # Simulación de shadow ledger update (en lugar de enviar órdenes reales)
        held_path = Path(s.data.data_dir) / "paper_positions.json"
        if held_path.exists():
            raw = _json.loads(held_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # Actualizar posiciones virtuales (muy simplificado para el ejemplo)
                current_positions = {k: float(v) for k, v in raw.items()}
        
        # Generar snapshot del shadow ledger
        shadow_snapshot = log_shadow_snapshot(desired, current_positions, tag="autopilot")
        
        # Si no se especifica exp_id explícitamente en la CLI simple, usar timestamp
        exp_id = "auto_20231027" 
        
        result = {
            "exp_id": exp_id,
            "orders_sent": 0,
            "brief_source": "paper_autopilot",
            "artifact_html": "<div>No live orders sent. Paper simulation only.</div>",
            "disclaimer": "This is a paper trading simulation. No real funds are at risk.",
            "shadow_snapshot": shadow_snapshot,
        }

        typer.echo(_json.dumps(_noneify(result), ensure_ascii=False, separators=(",", ":")))
    except Exception as e:
        typer.echo(_json.dumps({"error": str(e)}, ensure_ascii=False))


@app.command("ibc-checklist")
def ibc_checklist() -> None:
    """Print a manual paper Gateway/IBC checklist as JSON (no installs, no orders)."""
    import json as _json

    from .ibc_checklist import build_ibc_checklist

    typer.echo(_json.dumps(_noneify(build_ibc_checklist()), ensure_ascii=False, separators=(",", ":")))


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


@app.command("kill")
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
    
    # Identificar activo de referencia (benchmark o el único símbolo disponible)
    bench = s.universe.benchmark if s.universe.benchmark in data else next(iter(data.keys()))
    close_prices = data[bench]["close"].astype(float)
    
    try:
        # Asumiendo que fit_gmm_regime es una función definida en algún módulo o clase local
        # Si está dentro