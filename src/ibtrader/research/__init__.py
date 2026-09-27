"""V3 research laboratory: experiment runner, OOS gates, candidate registry."""

from .cost_stress import run_cost_ladder_research, summarize_cost_fragility
from .cpcv import cpcv_sharpe_distribution
from .cpcv_sma import run_sma_cpcv
from .dsr import deflated_sharpe_ratio, expected_max_sharpe
from .dsr_sma import run_sma_grid_dsr
from .embargo_sensitivity import run_embargo_sensitivity
from .gates import OOSGateResult, evaluate_candidate_gates
from .loss_mitigation import (
    DEFAULT_LOSS_MITIGATION_SPECS,
    run_loss_mitigation_research,
    summarize_loss_mitigation,
)
from .market_analyzer import analyze_market, score_symbol
from .mean_reversion_runner import DEFAULT_MR_CANDIDATES, run_mean_reversion_research
from .multi_asset import (
    DEFAULT_MULTI_ASSET_CANDIDATES,
    DEFAULT_RESEARCH_SYMBOLS,
    run_multi_asset_sma_research,
    summarize_cross_section,
)
from .pbo import pbo_from_fold_sharpe_rows, probability_of_backtest_overfitting
from .pbo_sma import run_sma_grid_pbo
from .registry import ExperimentRecord, load_experiments, save_experiment
from .report import build_honest_report
from .runner import (
    SMA_GRID_CANDIDATES,
    TREND_REGIME_CANDIDATES,
    build_experiment_records,
    run_sma_research,
    run_trend_regime_research,
)
from .suite import run_research_suite
from .tsmom_runner import DEFAULT_TSMOM_LOOKBACKS, run_tsmom_research
from .turnover_diag import diagnose_turnover
from .xsection_runner import DEFAULT_XSECTION_CANDIDATES, run_xsection_research

DEFAULT_SMA_CANDIDATES = SMA_GRID_CANDIDATES

__all__ = [
    "DEFAULT_LOSS_MITIGATION_SPECS",
    "DEFAULT_MR_CANDIDATES",
    "DEFAULT_MULTI_ASSET_CANDIDATES",
    "DEFAULT_RESEARCH_SYMBOLS",
    "DEFAULT_SMA_CANDIDATES",
    "DEFAULT_TSMOM_LOOKBACKS",
    "DEFAULT_XSECTION_CANDIDATES",
    "SMA_GRID_CANDIDATES",
    "TREND_REGIME_CANDIDATES",
    "OOSGateResult",
    "ExperimentRecord",
    "analyze_market",
    "build_experiment_records",
    "build_honest_report",
    "cpcv_sharpe_distribution",
    "deflated_sharpe_ratio",
    "diagnose_turnover",
    "evaluate_candidate_gates",
    "expected_max_sharpe",
    "load_experiments",
    "pbo_from_fold_sharpe_rows",
    "probability_of_backtest_overfitting",
    "run_cost_ladder_research",
    "run_embargo_sensitivity",
    "run_loss_mitigation_research",
    "run_mean_reversion_research",
    "run_multi_asset_sma_research",
    "run_research_suite",
    "run_sma_cpcv",
    "run_sma_grid_dsr",
    "run_sma_grid_pbo",
    "run_sma_research",
    "run_trend_regime_research",
    "run_tsmom_research",
    "run_xsection_research",
    "save_experiment",
    "score_symbol",
    "summarize_cost_fragility",
    "summarize_cross_section",
    "summarize_loss_mitigation",
]
