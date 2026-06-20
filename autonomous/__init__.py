"""Guarded Autonomous Trading module.

Orchestrates an end-to-end "find an opportunity, propose a trade, optionally
execute it" loop on top of the existing TWS Robot building blocks.
"""

import logging as _logging

from autonomous.autonomous_config import AutonomousTradingConfig, AutonomousMode
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.candidate_ranker import CandidateRanker
from autonomous.drawdown_governor import DrawdownDecision, DrawdownGovernor
from autonomous.edge_estimator import EdgeEstimate, RuleBasedEdgeEstimator
from autonomous.execution_quality import ExecutionQualityDecision, ExecutionQualityGuard
from autonomous.feature_builder import FeatureBuilder
from autonomous.fractional_sizer import FractionalEdgeSizer, FractionalSizingDecision
from autonomous.position_sizing import PositionSizer, SizingDecision
from autonomous.trade_planner import TradePlan, TradePlanner, TradeType
from autonomous.signal_provider import SignalProvider, StaticSignalProvider
from autonomous.technical_analysis_signal_provider import TechnicalAnalysisSignalProvider
from autonomous.autonomous_engine import AutonomousTradingEngine, AutonomousDecision, DecisionStatus
from autonomous.audit import AuditLogger
from autonomous.evidence_store import TradeEvidenceStore
from autonomous.runner_config import AutonomousRunnerConfig, AutonomousLiveRunnerConfig
from autonomous.trade_store import AutonomousTrade, TradeStore
from autonomous.exit_manager import AutonomousExitManager, ExitDecision
from autonomous.autonomous_runner import AutonomousPaperRunner, AutonomousRunResult, ReadinessGates
from autonomous.autonomous_live_runner import AutonomousLiveRunner, AutonomousLiveRunResult, LiveReadinessGates

try:  # pragma: no cover - import-time integration shim
    import autonomous.live_basket_patch  # noqa: F401
except Exception:
    _logging.getLogger(__name__).exception(
        "live_basket_patch import failed; basket live execution will be unavailable"
    )

__all__ = [
    "AutonomousTradingConfig",
    "AutonomousMode",
    "AutonomousTradingEngine",
    "AutonomousDecision",
    "DecisionStatus",
    "CandidateScanner",
    "CandidateSignal",
    "CandidateRanker",
    "DrawdownDecision",
    "DrawdownGovernor",
    "EdgeEstimate",
    "RuleBasedEdgeEstimator",
    "ExecutionQualityDecision",
    "ExecutionQualityGuard",
    "FeatureBuilder",
    "FractionalEdgeSizer",
    "FractionalSizingDecision",
    "PositionSizer",
    "SizingDecision",
    "TradePlan",
    "TradePlanner",
    "TradeType",
    "SignalProvider",
    "StaticSignalProvider",
    "TechnicalAnalysisSignalProvider",
    "AuditLogger",
    "TradeEvidenceStore",
    "AutonomousRunnerConfig",
    "AutonomousLiveRunnerConfig",
    "AutonomousTrade",
    "TradeStore",
    "AutonomousExitManager",
    "ExitDecision",
    "AutonomousPaperRunner",
    "AutonomousRunResult",
    "ReadinessGates",
    "AutonomousLiveRunner",
    "AutonomousLiveRunResult",
    "LiveReadinessGates",
]
