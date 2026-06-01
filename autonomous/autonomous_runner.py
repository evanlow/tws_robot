"""Paper-only autonomous runner.

Wraps :class:`autonomous.AutonomousTradingEngine` with the additional
safety gates required to make a one-shot paper-autonomous cycle safe:

* paper-mode connection must be active
* paper adapter must be ready
* signal provider must be ready
* emergency stop must not be active
* daily-trade-limit / max-open-trades must not be exceeded

Successful paper executions are recorded in
:class:`autonomous.trade_store.TradeStore`.

This module **never** enables a background loop.  It exposes one
synchronous :meth:`AutonomousPaperRunner.run_once` call intended to be
invoked from a dashboard button or scheduled job; any scheduler must
opt in explicitly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from autonomous.autonomous_config import AutonomousMode
from autonomous.autonomous_engine import AutonomousDecision, AutonomousTradingEngine, DecisionStatus
from autonomous.runner_config import AutonomousRunnerConfig
from autonomous.signal_provider import StaticSignalProvider
from autonomous.trade_planner import TradeType
from autonomous.trade_store import (
    OPEN,
    AutonomousTrade,
    TradeStore,
)

logger = logging.getLogger(__name__)


# Rejection codes -----------------------------------------------------------

NOT_CONNECTED = "not_connected"
NOT_PAPER_MODE = "not_paper_mode"
PAPER_ADAPTER_NOT_READY = "paper_adapter_not_ready"
SIGNAL_PROVIDER_NOT_READY = "signal_provider_not_ready"
EMERGENCY_STOP_ACTIVE = "emergency_stop_active"
RUNNER_DISABLED = "runner_disabled"
MAX_OPEN_TRADES = "max_open_autonomous_trades_reached"
EXECUTED = "executed"
NO_TRADE = "no_trade"
ENGINE_REJECTED = "engine_rejected"
EXECUTION_FAILED = "execution_failed"


@dataclass
class ReadinessGates:
    """Snapshot of the readiness checks evaluated for the current run."""

    connected: bool = False
    paper_mode: bool = False
    paper_adapter_ready: bool = False
    signal_provider_ready: bool = False
    emergency_stop_active: bool = False
    runner_enabled: bool = False
    open_autonomous_trades: int = 0
    max_open_autonomous_trades: int = 1

    @property
    def ready(self) -> bool:
        """All gates pass and we are below the open-trades limit."""
        return (
            self.connected
            and self.paper_mode
            and self.paper_adapter_ready
            and self.signal_provider_ready
            and not self.emergency_stop_active
            and self.runner_enabled
            and self.open_autonomous_trades < self.max_open_autonomous_trades
        )

    def reasons(self) -> List[str]:
        """Human-readable list of failed gates (empty when ready)."""
        out: List[str] = []
        if not self.connected:
            out.append("Not connected to IBKR")
        if not self.paper_mode:
            out.append("Not connected to paper account")
        if not self.paper_adapter_ready:
            out.append("Paper adapter not ready")
        if not self.signal_provider_ready:
            out.append("Signal provider not ready")
        if self.emergency_stop_active:
            out.append("Emergency stop active")
        if not self.runner_enabled:
            out.append("Runner disabled in config")
        if self.open_autonomous_trades >= self.max_open_autonomous_trades:
            out.append(
                f"Max open autonomous trades reached "
                f"({self.open_autonomous_trades}/{self.max_open_autonomous_trades})"
            )
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "paper_mode": self.paper_mode,
            "paper_adapter_ready": self.paper_adapter_ready,
            "signal_provider_ready": self.signal_provider_ready,
            "emergency_stop_active": self.emergency_stop_active,
            "runner_enabled": self.runner_enabled,
            "open_autonomous_trades": self.open_autonomous_trades,
            "max_open_autonomous_trades": self.max_open_autonomous_trades,
            "ready": self.ready,
            "reasons": self.reasons(),
        }


@dataclass
class AutonomousRunResult:
    """Structured result for a single :meth:`run_once` call."""

    status: str
    gates: ReadinessGates
    rejection_reason: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    trade: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "gates": self.gates.to_dict(),
            "decision": self.decision,
            "trade": self.trade,
            "notes": list(self.notes),
        }


# Type aliases --------------------------------------------------------------

ConnectedProvider = Callable[[], bool]
ConnectionEnvProvider = Callable[[], Optional[str]]
EmergencyStopProvider = Callable[[], bool]
PaperAdapterProvider = Callable[[], Any]
SignalProviderProvider = Callable[[], Any]


class AutonomousPaperRunner:
    """Run one paper-only autonomous cycle and record the lifecycle.

    Parameters
    ----------
    engine:
        Pre-built :class:`AutonomousTradingEngine`.  The runner does not
        duplicate the engine's logic; it simply enforces the additional
        paper-only gates and forwards to ``engine.run_once`` in
        ``PAPER_EXECUTE`` mode.
    trade_store:
        Persistence for opened autonomous trades.
    runner_config:
        Safety configuration for the runner itself (limits, paper-only
        flag, scheduler off-switch).
    connected_provider, connection_env_provider, paper_adapter_provider,
    signal_provider_provider, emergency_stop_provider:
        Callables returning the live state of each readiness gate.  These
        are injected so tests can supply lightweight fakes and so the
        runner stays decoupled from any specific service-manager type.
    """

    def __init__(
        self,
        engine: AutonomousTradingEngine,
        trade_store: TradeStore,
        runner_config: Optional[AutonomousRunnerConfig] = None,
        *,
        connected_provider: ConnectedProvider,
        connection_env_provider: ConnectionEnvProvider,
        paper_adapter_provider: PaperAdapterProvider,
        signal_provider_provider: SignalProviderProvider,
        emergency_stop_provider: EmergencyStopProvider,
    ) -> None:
        self._engine = engine
        self._store = trade_store
        self._config = runner_config or AutonomousRunnerConfig()
        self._connected_provider = connected_provider
        self._connection_env_provider = connection_env_provider
        self._paper_adapter_provider = paper_adapter_provider
        self._signal_provider_provider = signal_provider_provider
        self._emergency_stop_provider = emergency_stop_provider

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def config(self) -> AutonomousRunnerConfig:
        return self._config

    @property
    def trade_store(self) -> TradeStore:
        return self._store

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------
    def evaluate_gates(self) -> ReadinessGates:
        """Evaluate every readiness gate; never raises."""
        try:
            connected = bool(self._connected_provider())
        except Exception:  # pragma: no cover - defensive
            connected = False
        try:
            env = self._connection_env_provider()
        except Exception:  # pragma: no cover - defensive
            env = None
        try:
            adapter = self._paper_adapter_provider()
        except Exception:  # pragma: no cover - defensive
            adapter = None
        adapter_ready = adapter is not None and getattr(adapter, "is_ready", lambda: True)()
        try:
            provider = self._signal_provider_provider()
        except Exception:  # pragma: no cover - defensive
            provider = None
        # StaticSignalProvider is the placeholder stub that returns no
        # signals — when it's the active provider the runner refuses to
        # act so we never paper-trade against an empty universe.
        provider_ready = provider is not None and not isinstance(
            provider, StaticSignalProvider
        )
        try:
            estop = bool(self._emergency_stop_provider())
        except Exception:  # pragma: no cover - defensive
            estop = False

        return ReadinessGates(
            connected=connected,
            paper_mode=(env == "paper"),
            paper_adapter_ready=adapter_ready,
            signal_provider_ready=provider_ready,
            emergency_stop_active=estop,
            runner_enabled=self._config.runner_enabled,
            open_autonomous_trades=self._store.count_open(),
            max_open_autonomous_trades=self._config.max_open_autonomous_trades,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run_once(self) -> AutonomousRunResult:
        """Execute one paper-only autonomous cycle.

        The runner enforces every gate **before** invoking the engine
        so a rejected run never reaches the broker path.  When the
        engine succeeds, the opened trade is recorded in the
        :class:`TradeStore` for the lifecycle / exit manager.
        """
        gates = self.evaluate_gates()
        if not gates.ready:
            return AutonomousRunResult(
                status=self._first_gate_status(gates),
                gates=gates,
                rejection_reason="; ".join(gates.reasons()) or "runner gates failed",
            )

        # Force PAPER_EXECUTE mode and supply the runner's internal
        # confirmation flag — the runner itself is the confirmation
        # source, not a user click.
        self._engine.config.mode = AutonomousMode.PAPER_EXECUTE
        decision = self._engine.run_once(confirm=True)
        decision_payload = decision.to_dict()

        if decision.status == DecisionStatus.PAPER_EXECUTED:
            trade = self._record_trade(decision)
            return AutonomousRunResult(
                status=EXECUTED,
                gates=gates,
                decision=decision_payload,
                trade=trade.to_dict() if trade else None,
                notes=["paper trade executed and recorded"],
            )

        if decision.status in (DecisionStatus.NO_CANDIDATE, DecisionStatus.NO_TRADE_PLAN,
                               DecisionStatus.NO_DEPLOYABLE_CASH):
            return AutonomousRunResult(
                status=NO_TRADE,
                gates=gates,
                rejection_reason=decision.rejection_reason,
                decision=decision_payload,
            )
        if decision.status == DecisionStatus.EXECUTION_FAILED:
            return AutonomousRunResult(
                status=EXECUTION_FAILED,
                gates=gates,
                rejection_reason=decision.rejection_reason,
                decision=decision_payload,
            )
        return AutonomousRunResult(
            status=ENGINE_REJECTED,
            gates=gates,
            rejection_reason=decision.rejection_reason or decision.status.value,
            decision=decision_payload,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _first_gate_status(gates: ReadinessGates) -> str:
        if not gates.connected:
            return NOT_CONNECTED
        if not gates.paper_mode:
            return NOT_PAPER_MODE
        if not gates.paper_adapter_ready:
            return PAPER_ADAPTER_NOT_READY
        if not gates.signal_provider_ready:
            return SIGNAL_PROVIDER_NOT_READY
        if gates.emergency_stop_active:
            return EMERGENCY_STOP_ACTIVE
        if not gates.runner_enabled:
            return RUNNER_DISABLED
        if gates.open_autonomous_trades >= gates.max_open_autonomous_trades:
            return MAX_OPEN_TRADES
        return ENGINE_REJECTED

    def _record_trade(
        self,
        decision: AutonomousDecision,
    ) -> Optional[AutonomousTrade]:
        plan = decision.trade_plan or {}
        if not plan:
            return None
        if self._config.buy_shares_only and plan.get("trade_type") != TradeType.BUY_SHARES.value:
            logger.info(
                "AutonomousPaperRunner: skipping trade store record for "
                "non-BUY_SHARES plan %s",
                plan.get("trade_type"),
            )
            return None
        try:
            trade = AutonomousTrade(
                autonomous_trade_id=AutonomousTrade.new_id(),
                symbol=str(plan.get("symbol")),
                trade_type=str(plan.get("trade_type") or TradeType.BUY_SHARES.value),
                status=OPEN,
                entry_order_id=int(decision.order_id) if decision.order_id is not None else 0,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=float(plan.get("limit_price") or 0.0),
                quantity=int(plan.get("quantity") or 0),
                target_price=_as_float(plan.get("target_price")),
                stop_price=_as_float(plan.get("stop_price")),
                max_holding_days=int(self._config.max_holding_days),
                notes=["recorded by AutonomousPaperRunner"],
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to build AutonomousTrade from decision")
            return None
        self._store.record_trade(trade)
        return trade


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
