"""V3 research laboratory: experiment runner, OOS gates, candidate registry."""

from __future__ import annotations

from .gates import OOSGateResult, evaluate_candidate_gates
from .registry import (
    DEFAULT_REGISTRY_DIR,
    DEFAULT_REGISTRY_FILE,
    ExperimentRecord,
    default_registry_path,
    load_experiments,
    save_experiment,
)
from .runner import (
    SMA_GRID_CANDIDATES,
    TREND_REGIME_CANDIDATES,
    build_experiment_records,
    run_sma_research,
    run_trend_regime_research,
)

# Aliases for CLI / draft names
DEFAULT_SMA_CANDIDATES = SMA_GRID_CANDIDATES
evaluate_oos_gates = evaluate_candidate_gates
run_sma_grid_research = run_sma_research

__all__ = [
    "DEFAULT_REGISTRY_DIR",
    "DEFAULT_REGISTRY_FILE",
    "DEFAULT_SMA_CANDIDATES",
    "SMA_GRID_CANDIDATES",
    "TREND_REGIME_CANDIDATES",
    "OOSGateResult",
    "ExperimentRecord",
    "build_experiment_records",
    "default_registry_path",
    "evaluate_candidate_gates",
    "evaluate_oos_gates",
    "load_experiments",
    "run_sma_grid_research",
    "run_sma_research",
    "run_trend_regime_research",
    "save_experiment",
]
