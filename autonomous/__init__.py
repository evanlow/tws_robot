"""Guarded Autonomous Trading module.

Orchestrates an end-to-end "find an opportunity, propose a trade, optionally
execute it" loop on top of the existing TWS Robot building blocks
(CashAvailabilityAnalyzer, RiskManager, OrderExecutor, ServiceManager, paper
trading adapter).

The module is intentionally safety-first:

* Default mode is ``recommend_only`` — no orders are placed.
* Live execution is disabled by default and requires both an explicit
  ``allow_live_execution=True`` config flag and an explicit caller
  confirmation flag.
* The EMERGENCY_STOP file (and RiskManager.emergency_stop_active) blocks every
  execution path.
* Every decision — including rejections — is written to the JSONL audit log.

See ``autonomous.autonomous_engine.AutonomousTradingEngine`` for the entry
point.
"""

import logging as _logging

from autonomous.autonomous_config import AutonomousTradingConfig, AutonomousMode
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.candidate_ranker import CandidateRanker
from autonomous.trade_planner import TradePlan, TradePlanner, TradeType
from autonomous.signal_provider import SignalProvider, StaticSignalProvider
from autonomous.technical_analysis_signal_provider import (
    TechnicalAnalysisSignalProvider,
)
from autonomous.autonomous_engine import (
    AutonomousTradingEngine,
    AutonomousDecision,
    DecisionStatus,
)
from autonomous.audit import AuditLogger
from autonomous.evidence_store import TradeEvidenceStore
from autonomous.runner_config import AutonomousRunnerConfig, AutonomousLiveRunnerConfig
from autonomous.trade_store import AutonomousTrade, TradeStore
from autonomous.exit_manager import AutonomousExitManager, ExitDecision
from autonomous.autonomous_runner import (
    AutonomousPaperRunner,
    AutonomousRunResult,
    ReadinessGates,
)
from autonomous.autonomous_live_runner import (
    AutonomousLiveRunner,
    AutonomousLiveRunResult,
    LiveReadinessGates,
)

# Install basket-aware run_once behaviour after the live-runner class is loaded.
# This keeps the feature opt-in through engine config while making it available
# to assisted-live users once they choose to enable basket mode.
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
