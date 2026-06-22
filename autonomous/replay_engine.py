"""Deterministic replay / chaos harness for autonomous live readiness.

The harness is simulation-only. It never submits, cancels, replaces, or
flattens broker orders. It drives existing recovery, fill-ingestion,
lifecycle, market-data health, and supervisor components with deterministic
broker snapshots so operational failure modes can be reproduced in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from autonomous.broker_fill_ingestor import BrokerFillIngestionResult, BrokerFillIngestor
from autonomous.continuous_supervisor import (
    BROKER_DISCONNECTED,
    COMPLETED,
    PAUSED,
    UNRECONCILED_LIFECYCLE_STATE,
    ContinuousSupervisor,
    SupervisorCycleResult,
    SupervisorFault,
)
from autonomous.idempotency import IdempotencyStore
from autonomous.market_data_health import MarketDataHealthDecision, MarketDataHealthGuard
from autonomous.order_lifecycle import (
    ENTRY,
    STOP,
    TARGET,
    OrderLifecycleEvent,
    OrderLifecycleState,
    OrderLifecycleStore,
)
from autonomous.outcome_evidence_writer import OutcomeEvidenceWriter
from autonomous.protection_verifier import ProtectionVerifier
from autonomous.recovery_manager import RecoveryManager, RecoveryReport
from autonomous.trade_store import CLOSED, FAILED, OPEN, AutonomousTrade, TradeStore


STALE_QUOTE_FAULT = "stale_quote"
_NOW = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)


class ReplayStepKind(str, Enum):
    NORMAL_FILL = "normal_fill"
    PARTIAL_FILL = "partial_fill"
    ORDER_REJECTION = "order_rejection"
    BROKER_DISCONNECT = "broker_disconnect"
    STALE_QUOTE = "stale_quote"
    RESTART_AFTER_SUBMISSION = "restart_after_submission"
    RESTART_AFTER_FILL_BEFORE_EVIDENCE = "restart_after_fill_before_evidence"
    BASKET_ONE_FAILED_LEG = "basket_one_failed_leg"
    STOP_HIT = "stop_hit"
    TARGET_HIT = "target_hit"
    UNCONFIRMED_PROTECTIVE_STOP = "unconfirmed_protective_stop"


@dataclass(frozen=True)
class ReplayStep:
    """One deterministic chaos step."""

    kind: ReplayStepKind | str
    symbol: str = "AAA"
    quantity: int = 2
    price: float = 100.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayScenario:
    """Reproducible replay scenario definition."""

    name: str
    steps: Sequence[ReplayStep]
    description: str = ""
    max_symbol_exposure: int = 1


@dataclass(frozen=True)
class ReplayStepResult:
    """Diagnostics emitted after one replay step."""

    index: int
    kind: str
    recovery_classification: str
    recovery_required: bool
    supervisor_status: str
    supervisor_reason: Optional[str]
    duplicate_exposure_detected: bool
    evidence_reconstructable: bool
    ingestion: Dict[str, Any] = field(default_factory=dict)
    market_data_health: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "recovery_classification": self.recovery_classification,
            "recovery_required": self.recovery_required,
            "supervisor_status": self.supervisor_status,
            "supervisor_reason": self.supervisor_reason,
            "duplicate_exposure_detected": self.duplicate_exposure_detected,
            "evidence_reconstructable": self.evidence_reconstructable,
            "ingestion": dict(self.ingestion),
            "market_data_health": (
                dict(self.market_data_health)
                if self.market_data_health is not None
                else None
            ),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ReplayResult:
    """Full replay outcome."""

    scenario: str
    steps: List[ReplayStepResult]
    recovery: Dict[str, Any]
    supervisor: Dict[str, Any]
    duplicate_exposure_detected: bool
    evidence_reconstructable: bool
    broker_connected: bool
    open_positions: Dict[str, float]
    open_orders: List[Dict[str, Any]]
    lifecycle_current: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "steps": [step.to_dict() for step in self.steps],
            "recovery": dict(self.recovery),
            "supervisor": dict(self.supervisor),
            "duplicate_exposure_detected": self.duplicate_exposure_detected,
            "evidence_reconstructable": self.evidence_reconstructable,
            "broker_connected": self.broker_connected,
            "open_positions": dict(self.open_positions),
            "open_orders": [dict(order) for order in self.open_orders],
            "lifecycle_current": [dict(event) for event in self.lifecycle_current],
            "trades": [dict(trade) for trade in self.trades],
            "notes": list(self.notes),
        }


class SimulatedBroker:
    """Small deterministic broker snapshot used by replay scenarios."""

    def __init__(self) -> None:
        self.connected = True
        self.positions: Dict[str, float] = {}
        self.open_orders: List[Dict[str, Any]] = []
        self.fill_events: List[Dict[str, Any]] = []
        self.recent_executions: List[Dict[str, Any]] = []

    def set_position(self, symbol: str, quantity: float) -> None:
        symbol = _symbol(symbol)
        if quantity == 0:
            self.positions.pop(symbol, None)
            return
        self.positions[symbol] = float(quantity)

    def add_open_order(
        self,
        *,
        order_id: int,
        symbol: str,
        action: str,
        order_type: str = "LMT",
        quantity: float = 1,
        status: str = "Submitted",
        parent_id: Optional[int] = None,
        remaining: Optional[float] = None,
    ) -> None:
        self.open_orders = [
            order for order in self.open_orders
            if int(order.get("order_id", -1)) != int(order_id)
        ]
        self.open_orders.append({
            "order_id": int(order_id),
            "symbol": _symbol(symbol),
            "action": str(action).upper(),
            "order_type": str(order_type).upper(),
            "quantity": float(quantity),
            "remaining": remaining,
            "status": status,
            "parent_id": parent_id,
        })

    def remove_open_order(self, order_id: int) -> None:
        self.open_orders = [
            order for order in self.open_orders
            if int(order.get("order_id", -1)) != int(order_id)
        ]

    def record_fill(
        self,
        *,
        execution_id: str,
        order_id: int,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> None:
        event = {
            "execution_id": execution_id,
            "order_id": int(order_id),
            "symbol": _symbol(symbol),
            "side": side,
            "quantity": float(quantity),
            "price": float(price),
            "commission": float(commission),
            "timestamp": (timestamp or _NOW).isoformat(),
        }
        self.fill_events.append(event)
        self.recent_executions.append(dict(event))

    def pop_fill_events(self) -> List[Dict[str, Any]]:
        events = list(self.fill_events)
        self.fill_events.clear()
        return events

    def positions_payload(self) -> Dict[str, Dict[str, float]]:
        return {
            symbol: {"quantity": quantity}
            for symbol, quantity in self.positions.items()
        }

    def open_order_payload(self) -> List[Dict[str, Any]]:
        return [dict(order) for order in self.open_orders]


class ReplayChaosHarness:
    """Run deterministic operational replay scenarios against safety modules."""

    def __init__(
        self,
        root: str | Path,
        *,
        idempotency_stale_minutes: int = 30,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.trade_store = TradeStore(path=str(self.root / "trades.jsonl"))
        self.lifecycle_store = OrderLifecycleStore(path=str(self.root / "lifecycle.jsonl"))
        self.idempotency_store = IdempotencyStore(path=str(self.root / "idempotency.jsonl"))
        self.evidence_dir = self.root / "evidence"
        self.broker = SimulatedBroker()
        self.recovery_manager = RecoveryManager(
            idempotency_stale_minutes=idempotency_stale_minutes
        )
        self.protection_verifier = ProtectionVerifier()
        self.ingestor = BrokerFillIngestor(
            self.trade_store,
            lifecycle_store=self.lifecycle_store,
            outcome_writer=OutcomeEvidenceWriter(str(self.evidence_dir)),
        )
        self.market_data_guard = MarketDataHealthGuard(
            max_quote_age_seconds=60,
            block_missing_timestamp_live=True,
        )
        self.supervisor = ContinuousSupervisor(cadence_seconds=1)
        self._notes: List[str] = []

    def run(self, scenario: ReplayScenario) -> ReplayResult:
        """Run a scenario and return deterministic diagnostics."""
        step_results: List[ReplayStepResult] = []
        latest_recovery = self._evaluate_recovery()
        latest_supervisor = self.supervisor.status()
        latest_evidence_ok = True

        for index, step in enumerate(scenario.steps):
            kind = ReplayStepKind(step.kind)
            self._apply_step(kind, step)
            ingestion = self.ingestor.ingest(self.broker.pop_fill_events())
            health = self._market_data_health(kind, step)
            latest_recovery = self._evaluate_recovery()
            supervisor_result = self._run_supervisor(latest_recovery, health)
            duplicate = self._duplicate_exposure_detected(
                max_symbol_exposure=scenario.max_symbol_exposure
            )
            latest_evidence_ok = self._evidence_reconstructable(ingestion)
            notes = list(ingestion.notes)
            if health is not None and not health.allowed:
                notes.append(health.reason)
            if latest_recovery.recovery_required:
                notes.extend(latest_recovery.reasons())
            step_results.append(ReplayStepResult(
                index=index,
                kind=kind.value,
                recovery_classification=latest_recovery.classification.value,
                recovery_required=latest_recovery.recovery_required,
                supervisor_status=supervisor_result.status,
                supervisor_reason=supervisor_result.reason,
                duplicate_exposure_detected=duplicate,
                evidence_reconstructable=latest_evidence_ok,
                ingestion=ingestion.to_dict(),
                market_data_health=health.to_dict() if health is not None else None,
                notes=notes,
            ))
            latest_supervisor = self.supervisor.status()
            if self.supervisor.paused:
                self.supervisor.resume()

        return ReplayResult(
            scenario=scenario.name,
            steps=step_results,
            recovery=latest_recovery.to_dict(),
            supervisor=latest_supervisor,
            duplicate_exposure_detected=any(
                step.duplicate_exposure_detected for step in step_results
            ),
            evidence_reconstructable=all(
                step.evidence_reconstructable for step in step_results
            ),
            broker_connected=self.broker.connected,
            open_positions=dict(self.broker.positions),
            open_orders=self.broker.open_order_payload(),
            lifecycle_current=[
                event.to_dict()
                for event in self.lifecycle_store.current_states().values()
            ],
            trades=[trade.to_dict() for trade in self.trade_store.list_all()],
            notes=list(self._notes),
        )

    def _apply_step(self, kind: ReplayStepKind, step: ReplayStep) -> None:
        if kind == ReplayStepKind.NORMAL_FILL:
            trade = self._ensure_trade(step.symbol, step.quantity)
            self.broker.set_position(step.symbol, step.quantity)
            self._ensure_protective_orders(trade)
            self.broker.record_fill(
                execution_id=f"{kind.value}-{step.symbol}",
                order_id=trade.entry_order_id,
                symbol=step.symbol,
                side="BOT",
                quantity=step.quantity,
                price=step.price,
            )
            return

        if kind == ReplayStepKind.PARTIAL_FILL:
            trade = self._ensure_trade(step.symbol, step.quantity)
            partial_qty = max(1, int(step.quantity // 2))
            self.broker.set_position(step.symbol, partial_qty)
            self._ensure_protective_orders(trade)
            self.broker.record_fill(
                execution_id=f"{kind.value}-{step.symbol}",
                order_id=trade.entry_order_id,
                symbol=step.symbol,
                side="BOT",
                quantity=partial_qty,
                price=step.price,
            )
            return

        if kind == ReplayStepKind.ORDER_REJECTION:
            trade = self._ensure_trade(step.symbol, step.quantity)
            self.trade_store.update_trade(
                trade.autonomous_trade_id,
                status=FAILED,
                notes=["replay: broker rejected entry"],
            )
            self.lifecycle_store.record_transition(
                lifecycle_id=trade.entry_lifecycle_id or f"{trade.autonomous_trade_id}-entry",
                state=OrderLifecycleState.REJECTED,
                symbol=trade.symbol,
                order_role=ENTRY,
                broker_order_id=trade.entry_order_id,
                autonomous_trade_id=trade.autonomous_trade_id,
                reason="replay broker rejection",
            )
            return

        if kind == ReplayStepKind.BROKER_DISCONNECT:
            self.broker.connected = False
            return

        if kind == ReplayStepKind.STALE_QUOTE:
            return

        if kind == ReplayStepKind.RESTART_AFTER_SUBMISSION:
            self.idempotency_store.acquire(symbol=step.symbol)
            self.broker.add_open_order(
                order_id=900,
                symbol=step.symbol,
                action="BUY",
                quantity=step.quantity,
            )
            return

        if kind == ReplayStepKind.RESTART_AFTER_FILL_BEFORE_EVIDENCE:
            self.broker.set_position(step.symbol, step.quantity)
            self.broker.record_fill(
                execution_id=f"{kind.value}-{step.symbol}",
                order_id=901,
                symbol=step.symbol,
                side="BOT",
                quantity=step.quantity,
                price=step.price,
            )
            return

        if kind == ReplayStepKind.BASKET_ONE_FAILED_LEG:
            first = self._ensure_trade("AAA", step.quantity)
            second = self._ensure_trade("BBB", step.quantity)
            self.broker.set_position("AAA", step.quantity)
            self._ensure_protective_orders(first)
            self.broker.record_fill(
                execution_id="basket-aaa-entry",
                order_id=first.entry_order_id,
                symbol="AAA",
                side="BOT",
                quantity=step.quantity,
                price=step.price,
            )
            self.trade_store.update_trade(
                second.autonomous_trade_id,
                status=FAILED,
                notes=["replay: basket leg rejected"],
            )
            self.lifecycle_store.record_transition(
                lifecycle_id=second.entry_lifecycle_id or f"{second.autonomous_trade_id}-entry",
                state=OrderLifecycleState.REJECTED,
                symbol=second.symbol,
                order_role=ENTRY,
                broker_order_id=second.entry_order_id,
                autonomous_trade_id=second.autonomous_trade_id,
                reason="replay basket leg rejected",
            )
            return

        if kind in {ReplayStepKind.STOP_HIT, ReplayStepKind.TARGET_HIT}:
            trade = self._ensure_trade(step.symbol, step.quantity)
            self.broker.set_position(step.symbol, 0)
            self._ensure_protective_orders(trade)
            exit_order_id = (
                trade.stop_order_id
                if kind == ReplayStepKind.STOP_HIT
                else trade.target_order_id
            )
            exit_price = 95.0 if kind == ReplayStepKind.STOP_HIT else 110.0
            self.broker.record_fill(
                execution_id=f"{kind.value}-{step.symbol}-entry",
                order_id=trade.entry_order_id,
                symbol=step.symbol,
                side="BOT",
                quantity=step.quantity,
                price=step.price,
            )
            self.broker.record_fill(
                execution_id=f"{kind.value}-{step.symbol}-exit",
                order_id=int(exit_order_id or 0),
                symbol=step.symbol,
                side="SLD",
                quantity=step.quantity,
                price=exit_price,
            )
            self.broker.remove_open_order(int(exit_order_id or 0))
            return

        if kind == ReplayStepKind.UNCONFIRMED_PROTECTIVE_STOP:
            self._ensure_trade(step.symbol, step.quantity)
            self.broker.set_position(step.symbol, step.quantity)
            return

        raise ValueError(f"unsupported replay step: {kind.value}")

    def _ensure_trade(self, symbol: str, quantity: int) -> AutonomousTrade:
        symbol = _symbol(symbol)
        existing = [
            trade for trade in self.trade_store.list_all()
            if trade.symbol == symbol
        ]
        if existing:
            return existing[-1]
        base = 1000 + len(self.trade_store.list_all()) * 10
        trade_id = f"replay-{symbol.lower()}"
        trade = AutonomousTrade(
            autonomous_trade_id=trade_id,
            symbol=symbol,
            trade_type="BUY_SHARES",
            status=OPEN,
            entry_order_id=base,
            entry_time=_NOW,
            entry_limit_price=100.0,
            quantity=int(quantity),
            target_price=110.0,
            stop_price=95.0,
            target_order_id=base + 1,
            stop_order_id=base + 2,
            entry_lifecycle_id=f"{trade_id}-entry",
            target_lifecycle_id=f"{trade_id}-target",
            stop_lifecycle_id=f"{trade_id}-stop",
        )
        self.trade_store.record_trade(trade)
        self.lifecycle_store.record_transition(
            lifecycle_id=trade.entry_lifecycle_id,
            state=OrderLifecycleState.SUBMITTED,
            symbol=trade.symbol,
            order_role=ENTRY,
            broker_order_id=trade.entry_order_id,
            autonomous_trade_id=trade.autonomous_trade_id,
            reason="replay seeded entry",
        )
        self.idempotency_store.acquire(symbol=trade.symbol)
        self.idempotency_store.mark_submitted(
            self.idempotency_store.build_key(symbol=trade.symbol),
            broker_order_id=trade.entry_order_id,
            autonomous_trade_id=trade.autonomous_trade_id,
        )
        return trade

    def _ensure_protective_orders(self, trade: AutonomousTrade) -> None:
        self.broker.add_open_order(
            order_id=int(trade.stop_order_id or 0),
            symbol=trade.symbol,
            action="SELL",
            order_type="STP",
            quantity=trade.quantity,
            parent_id=trade.entry_order_id,
        )
        self.broker.add_open_order(
            order_id=int(trade.target_order_id or 0),
            symbol=trade.symbol,
            action="SELL",
            order_type="LMT",
            quantity=trade.quantity,
            parent_id=trade.entry_order_id,
        )
        self.lifecycle_store.record_transition(
            lifecycle_id=trade.stop_lifecycle_id or f"{trade.autonomous_trade_id}-stop",
            state=OrderLifecycleState.PROTECTIVE_STOP_CONFIRMED,
            symbol=trade.symbol,
            order_role=STOP,
            broker_order_id=trade.stop_order_id,
            autonomous_trade_id=trade.autonomous_trade_id,
            parent_lifecycle_id=trade.entry_lifecycle_id,
            reason="replay protective stop confirmed",
        )
        self.lifecycle_store.record_transition(
            lifecycle_id=trade.target_lifecycle_id or f"{trade.autonomous_trade_id}-target",
            state=OrderLifecycleState.TARGET_PENDING,
            symbol=trade.symbol,
            order_role=TARGET,
            broker_order_id=trade.target_order_id,
            autonomous_trade_id=trade.autonomous_trade_id,
            parent_lifecycle_id=trade.entry_lifecycle_id,
            reason="replay target pending",
        )

    def _evaluate_recovery(self) -> RecoveryReport:
        trades = self.trade_store.list_all()
        open_trades = [trade for trade in trades if trade.status == OPEN]
        protection_results = self.protection_verifier.verify_open_trades(
            open_trades,
            broker_positions=self.broker.positions_payload(),
            open_orders=self.broker.open_order_payload(),
        )
        return self.recovery_manager.evaluate(
            trades=trades,
            broker_positions=self.broker.positions_payload(),
            broker_open_orders=self.broker.open_order_payload(),
            lifecycle_events=self.lifecycle_store.list_events(),
            idempotency_locks=list(self.idempotency_store.current_locks().values()),
            protection_results=protection_results,
            deployable_cash=50_000.0,
            recent_executions=self.broker.recent_executions,
            now=_NOW + timedelta(hours=1),
        )

    def _market_data_health(
        self,
        kind: ReplayStepKind,
        step: ReplayStep,
    ) -> Optional[MarketDataHealthDecision]:
        if kind != ReplayStepKind.STALE_QUOTE:
            return None
        stale = _NOW - timedelta(minutes=10)
        return self.market_data_guard.evaluate(
            symbol=step.symbol,
            mode="assisted_live",
            bid=99.95,
            ask=100.05,
            last=100.0,
            quote_timestamp=stale,
            feed_healthy=True,
            market_open=True,
            now=_NOW,
        )

    def _run_supervisor(
        self,
        recovery: RecoveryReport,
        health: Optional[MarketDataHealthDecision],
    ) -> SupervisorCycleResult:
        faults: List[SupervisorFault] = []
        if not self.broker.connected:
            faults.append(SupervisorFault(
                BROKER_DISCONNECTED,
                "Replay broker disconnected.",
            ))
        if health is not None and not health.allowed:
            faults.append(SupervisorFault(
                STALE_QUOTE_FAULT,
                health.reason,
                health.to_dict(),
            ))
        if recovery.recovery_required:
            faults.append(SupervisorFault(
                UNRECONCILED_LIFECYCLE_STATE,
                "Replay recovery classification requires operator action.",
                recovery.to_dict(),
            ))
        return self.supervisor.run_cycle(
            lambda: {"status": COMPLETED},
            fault_provider=lambda: faults,
        )

    def _duplicate_exposure_detected(self, *, max_symbol_exposure: int) -> bool:
        local_open: Dict[str, int] = {}
        active_buys: Dict[str, int] = {}
        for trade in self.trade_store.list_open():
            local_open[trade.symbol] = local_open.get(trade.symbol, 0) + 1
        for order in self.broker.open_order_payload():
            if str(order.get("action") or "").upper() != "BUY":
                continue
            status = str(order.get("status") or "").replace(" ", "").lower()
            if status in {"cancelled", "filled", "inactive", "rejected"}:
                continue
            symbol = _symbol(order.get("symbol"))
            active_buys[symbol] = active_buys.get(symbol, 0) + 1
        return any(count > max_symbol_exposure for count in local_open.values()) or any(
            count > max_symbol_exposure for count in active_buys.values()
        )

    def _evidence_reconstructable(
        self,
        ingestion: BrokerFillIngestionResult,
    ) -> bool:
        if any(note.startswith("unmatched broker fill") for note in ingestion.notes):
            return False
        known_order_ids = {
            order_id
            for trade in self.trade_store.list_all()
            for order_id in (
                trade.entry_order_id,
                trade.target_order_id,
                trade.stop_order_id,
                trade.exit_order_id,
            )
            if order_id is not None
        }
        for execution in self.broker.recent_executions:
            if int(execution.get("order_id", -1)) not in known_order_ids:
                return False
        for trade in self.trade_store.list_all():
            if trade.status == CLOSED and (
                not trade.entry_fills
                or not trade.exit_fills
                or not trade.outcome_emitted
            ):
                return False
        return True


def default_phase_11_scenarios() -> List[ReplayScenario]:
    """Return the required Phase 11 replay scenarios."""
    return [
        ReplayScenario(
            "normal_fill",
            [ReplayStep(ReplayStepKind.NORMAL_FILL)],
            "Entry fill with broker-visible protective orders.",
        ),
        ReplayScenario(
            "partial_fill",
            [ReplayStep(ReplayStepKind.PARTIAL_FILL)],
            "Partial entry fill leaves reconciliation required.",
        ),
        ReplayScenario(
            "order_rejection",
            [ReplayStep(ReplayStepKind.ORDER_REJECTION)],
            "Rejected entry becomes terminal local state.",
        ),
        ReplayScenario(
            "broker_disconnect",
            [ReplayStep(ReplayStepKind.BROKER_DISCONNECT)],
            "Supervisor pauses on broker disconnect.",
        ),
        ReplayScenario(
            "stale_quote",
            [ReplayStep(ReplayStepKind.STALE_QUOTE)],
            "Stale live quote blocks the supervised cycle.",
        ),
        ReplayScenario(
            "restart_after_submission",
            [ReplayStep(ReplayStepKind.RESTART_AFTER_SUBMISSION)],
            "Active broker BUY plus idempotency lock requires recovery.",
        ),
        ReplayScenario(
            "restart_after_fill_before_evidence",
            [ReplayStep(ReplayStepKind.RESTART_AFTER_FILL_BEFORE_EVIDENCE)],
            "Broker execution without local evidence is not reconstructable.",
        ),
        ReplayScenario(
            "basket_one_failed_leg",
            [ReplayStep(ReplayStepKind.BASKET_ONE_FAILED_LEG)],
            "One basket leg fills while another is rejected.",
        ),
        ReplayScenario(
            "stop_hit",
            [ReplayStep(ReplayStepKind.STOP_HIT)],
            "Protective stop fill closes the trade and emits outcome evidence.",
        ),
        ReplayScenario(
            "target_hit",
            [ReplayStep(ReplayStepKind.TARGET_HIT)],
            "Target fill closes the trade and emits outcome evidence.",
        ),
        ReplayScenario(
            "unconfirmed_protective_stop",
            [ReplayStep(ReplayStepKind.UNCONFIRMED_PROTECTIVE_STOP)],
            "Open broker position without confirmed protection requires recovery.",
        ),
    ]


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()
