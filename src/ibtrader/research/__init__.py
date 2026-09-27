"""V3 research laboratory: experiment runner, OOS gates, candidate registry."""

from .cost_stress import run_cost_ladder_research, summarize_cost_fragility
from .gates import OOSGateResult, evaluate_candidate_gates
from .registry import ExperimentRecord, load_experiments, save_experiment
from .runner import (
    SMA_GRID_CANDIDATES,
    TREND_REGIME_CANDIDATES,
    build_experiment_records,
    run_sma_research,
    run_trend_regime_research,
)
from .suite import run_research_suite
from .tsmom_runner import DEFAULT_TSMOM_LOOKBACKS, run_tsmom_research

# Aliases used by CLI / older drafts
DEFAULT_SMA_CANDIDATES = SMA_GRID_CANDIDATES

__all__ = [
    "DEFAULT_SMA_CANDIDATES",
    "DEFAULT_TSMOM_LOOKBACKS",
    "SMA_GRID_CANDIDATES",
    "TREND_REGIME_CANDIDATES",
    "OOSGateResult",
    "ExperimentRecord",
    "build_experiment_records",
    "evaluate_candidate_gates",
    "load_experiments",
    "run_cost_ladder_research",
    "run_research_suite",
    "run_sma_research",
    "run_trend_regime_research",
    "run_tsmom_research",
    "save_experiment",
    "summarize_cost_fragility",
]
