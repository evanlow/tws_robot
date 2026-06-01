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
]
