"""Guarded Autonomous Trading module.

Orchestrates an end-to-end "find an opportunity, propose a trade, optionally
execute it" loop on top of the existing TWS Robot building blocks.
"""

import logging as _logging

from autonomous.autonomous_config import AutonomousTradingConfig, AutonomousMode
from autonomous.basket_risk_allocator import BasketRiskAllocation, BasketRiskAllocator, BasketRiskLegDecision
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.candidate_ranker import CandidateRanker
from autonomous.drawdown_governor import DrawdownDecision, DrawdownGovernor
from autonomous.edge_estimator import EdgeEstimate, RuleBasedEdgeEstimator
from autonomous.execution_quality import ExecutionQualityDecision, ExecutionQualityGuard
from autonomous.feature_builder import FeatureBuilder
from autonomous.fractional_sizer import FractionalEdgeSizer, FractionalSizingDecision
from autonomous.outcome_evidence_writer import OutcomeEvidenceWriter
from autonomous.outcome_reconciliation import FillSummary, OutcomeReconciliation, OutcomeReconciler
from autonomous.order_lifecycle import OrderLifecycleEvent, OrderLifecycleState, OrderLifecycleStore
from autonomous.position_sizing import PositionSizer, SizingDecision
from autonomous.protection_verifier import BrokerOrderSnapshot, ProtectionVerifier, ProtectionVerificationResult
from autonomous.regime_context import build_regime_context, classify_time_of_day, sector_etf_for
from autonomous.risk_lifecycle import LossLimitDecision, LossLimitGuard, StrategyEquityCurveBuilder, StrategyEquityPoint
from autonomous.strategy_arm import StrategyArmLearner, StrategyArmStats
from autonomous.trade_planner import TradePlan, TradePlanner, TradeType
from autonomous.validation_framework import ValidationFramework, ValidationReport, ValidationThresholds
from autonomous.walk_forward_report import ChronoValidationReport, ChronoValidationWindow, ChronoValidator
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
    "BasketRiskAllocation",
    "BasketRiskAllocator",
    "BasketRiskLegDecision",
    "AutonomousTradingEngine",
    "AutonomousDecision",
    "DecisionStatus",
    "CandidateScanner",
    "CandidateSignal",
    "CandidateRanker",
    "ChronoValidationReport",
    "ChronoValidationWindow",
    "ChronoValidator",
    "DrawdownDecision",
    "DrawdownGovernor",
    "EdgeEstimate",
    "RuleBasedEdgeEstimator",
    "ExecutionQualityDecision",
    "ExecutionQualityGuard",
    "FeatureBuilder",
    "FillSummary",
    "FractionalEdgeSizer",
    "FractionalSizingDecision",
    "LossLimitDecision",
    "LossLimitGuard",
    "OutcomeEvidenceWriter",
    "OutcomeReconciliation",
    "OutcomeReconciler",
    "OrderLifecycleEvent",
    "OrderLifecycleState",
    "OrderLifecycleStore",
    "PositionSizer",
    "BrokerOrderSnapshot",
    "ProtectionVerifier",
    "ProtectionVerificationResult",
    "SizingDecision",
    "StrategyEquityCurveBuilder",
    "StrategyEquityPoint",
    "StrategyArmLearner",
    "StrategyArmStats",
    "TradePlan",
    "TradePlanner",
    "TradeType",
    "ValidationFramework",
    "ValidationReport",
    "ValidationThresholds",
    "build_regime_context",
    "classify_time_of_day",
    "sector_etf_for",
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
