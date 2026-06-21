"""Restart recovery and broker/local reconciliation for autonomous live mode.

The recovery manager is read-only.  It gathers local autonomous trade state,
broker snapshots, lifecycle events, idempotency locks, and protection
diagnostics into a startup classification.  It never submits, cancels,
replaces, or flattens broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence

from autonomous.idempotency import IdempotencyLock
from autonomous.order_lifecycle import OrderLifecycleEvent, OrderLifecycleState
from autonomous.protection_verifier import (
    BrokerOrderSnapshot,
    ProtectionVerificationResult,
)
from autonomous.trade_store import CLOSED, FAILED, OPEN, AutonomousTrade


class RecoveryClassification(str, Enum):
    SAFE_TO_TRADE = "SAFE_TO_TRADE"
    SAFE_TO_MONITOR_ONLY = "SAFE_TO_MONITOR_ONLY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"


INFO = "info"
WARNING = "warning"
RECOVERY = "recovery"
MANUAL = "manual"


@dataclass(frozen=True)
class RecoveryIssue:
    code: str
    severity: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class RecoveryReport:
    classification: RecoveryClassification
    generated_at: datetime
    issues: List[RecoveryIssue] = field(default_factory=list)
    local_open_trades: int = 0
    broker_positions: int = 0
    broker_open_orders: int = 0
    active_idempotency_locks: int = 0
    stale_idempotency_locks: int = 0
    deployable_cash: Optional[float] = None
    risk_lifecycle: Optional[Dict[str, Any]] = None
    protection_diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ready_to_trade(self) -> bool:
        return self.classification == RecoveryClassification.SAFE_TO_TRADE

    @property
    def recovery_required(self) -> bool:
        return self.classification in {
            RecoveryClassification.RECOVERY_REQUIRED,
            RecoveryClassification.MANUAL_INTERVENTION_REQUIRED,
        }

    def reasons(self) -> List[str]:
        return [issue.message for issue in self.issues if issue.severity in {RECOVERY, MANUAL}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification.value,
            "ready_to_trade": self.ready_to_trade,
            "recovery_required": self.recovery_required,
            "generated_at": self.generated_at.isoformat(),
            "issues": [issue.to_dict() for issue in self.issues],
            "local_open_trades": self.local_open_trades,
            "broker_positions": self.broker_positions,
            "broker_open_orders": self.broker_open_orders,
            "active_idempotency_locks": self.active_idempotency_locks,
            "stale_idempotency_locks": self.stale_idempotency_locks,
            "deployable_cash": self.deployable_cash,
            "risk_lifecycle": dict(self.risk_lifecycle or {}),
            "protection_diagnostics": list(self.protection_diagnostics),
        }


class RecoveryManager:
    """Classify whether autonomous live mode can safely resume after restart."""

    def __init__(self, *, idempotency_stale_minutes: int = 120) -> None:
        self._idempotency_stale_minutes = max(0, int(idempotency_stale_minutes))

    def evaluate(
        self,
        *,
        trades: Iterable[AutonomousTrade],
        broker_positions: Dict[str, Any],
        broker_open_orders: Iterable[Any],
        lifecycle_events: Iterable[OrderLifecycleEvent],
        idempotency_locks: Iterable[IdempotencyLock],
        protection_results: Optional[Iterable[ProtectionVerificationResult]] = None,
        deployable_cash: Optional[float] = None,
        risk_lifecycle: Optional[Dict[str, Any]] = None,
        recent_executions: Optional[Iterable[Dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> RecoveryReport:
        ref = now or datetime.now(timezone.utc)
        trade_list = list(trades or [])
        open_trades = [trade for trade in trade_list if trade.status in {OPEN}]
        positions = dict(broker_positions or {})
        order_snapshots = [
            BrokerOrderSnapshot.from_raw(order)
            for order in (broker_open_orders or [])
        ]
        lifecycle_current = self._current_lifecycle(lifecycle_events or [])
        locks = list(idempotency_locks or [])
        active_locks = [lock for lock in locks if lock.active]
        stale_locks = [
            lock for lock in active_locks
            if lock.is_stale(older_than_minutes=self._idempotency_stale_minutes, now=ref)
        ]
        protection = list(protection_results or [])

        issues: List[RecoveryIssue] = []
        issues.extend(self._trade_position_issues(open_trades, positions))
        issues.extend(self._broker_order_issues(open_trades, order_snapshots, lifecycle_current))
        issues.extend(self._lifecycle_issues(open_trades, lifecycle_current))
        issues.extend(self._idempotency_issues(active_locks, stale_locks, trade_list))
        issues.extend(self._protection_issues(protection))
        issues.extend(self._risk_lifecycle_issues(risk_lifecycle))
        issues.extend(self._recent_execution_issues(recent_executions, trade_list))

        classification = self._classify(issues)
        return RecoveryReport(
            classification=classification,
            generated_at=ref,
            issues=issues,
            local_open_trades=len(open_trades),
            broker_positions=len([
                pos for pos in positions.values()
                if _position_quantity(pos) != 0
            ]),
            broker_open_orders=len([
                order for order in order_snapshots
                if order.is_active
            ]),
            active_idempotency_locks=len(active_locks),
            stale_idempotency_locks=len(stale_locks),
            deployable_cash=deployable_cash,
            risk_lifecycle=dict(risk_lifecycle or {}),
            protection_diagnostics=[item.to_dict() for item in protection],
        )

    def manual_intervention_report(self, reason: str) -> RecoveryReport:
        issue = RecoveryIssue(
            code="recovery_snapshot_unavailable",
            severity=MANUAL,
            message=reason,
        )
        return RecoveryReport(
            classification=RecoveryClassification.MANUAL_INTERVENTION_REQUIRED,
            generated_at=datetime.now(timezone.utc),
            issues=[issue],
        )

    @staticmethod
    def _current_lifecycle(
        events: Iterable[OrderLifecycleEvent],
    ) -> Dict[str, OrderLifecycleEvent]:
        current: Dict[str, OrderLifecycleEvent] = {}
        for event in events:
            current[event.lifecycle_id] = event
        return current

    def _trade_position_issues(
        self,
        open_trades: Sequence[AutonomousTrade],
        broker_positions: Dict[str, Any],
    ) -> List[RecoveryIssue]:
        issues: List[RecoveryIssue] = []
        positions_by_symbol = {
            str(symbol or "").strip().upper(): position
            for symbol, position in (broker_positions or {}).items()
        }
        for trade in open_trades:
            if _is_dry_run_trade(trade):
                continue
            symbol = str(trade.symbol or "").strip().upper()
            broker_qty = _position_quantity(positions_by_symbol.get(symbol))
            local_qty = abs(float(getattr(trade, "quantity", 0) or 0))
            if broker_qty == 0:
                issues.append(RecoveryIssue(
                    code="local_open_trade_missing_broker_position",
                    severity=RECOVERY,
                    message=(
                        f"Local autonomous trade {trade.autonomous_trade_id} "
                        f"for {symbol} is OPEN but broker position is missing."
                    ),
                    details={
                        "autonomous_trade_id": trade.autonomous_trade_id,
                        "symbol": symbol,
                        "entry_order_id": trade.entry_order_id,
                    },
                ))
                continue
            if local_qty > 0 and abs(broker_qty - local_qty) > 1e-9:
                issues.append(RecoveryIssue(
                    code="local_broker_quantity_mismatch",
                    severity=RECOVERY,
                    message=(
                        f"Local autonomous trade {trade.autonomous_trade_id} "
                        f"quantity {local_qty:g} does not match broker quantity "
                        f"{broker_qty:g} for {symbol}."
                    ),
                    details={
                        "autonomous_trade_id": trade.autonomous_trade_id,
                        "symbol": symbol,
                        "local_quantity": local_qty,
                        "broker_quantity": broker_qty,
                    },
                ))
        return issues

    def _broker_order_issues(
        self,
        open_trades: Sequence[AutonomousTrade],
        open_orders: Sequence[BrokerOrderSnapshot],
        lifecycle_current: Dict[str, OrderLifecycleEvent],
    ) -> List[RecoveryIssue]:
        issues: List[RecoveryIssue] = []
        trade_order_ids = {
            _as_int(order_id)
            for trade in open_trades
            for order_id in (trade.entry_order_id, trade.target_order_id, trade.stop_order_id)
            if _as_int(order_id) is not None
        }
        _terminal_states = {
            OrderLifecycleState.FILLED,
            OrderLifecycleState.CLOSED,
            OrderLifecycleState.RECONCILED,
            OrderLifecycleState.REJECTED,
            OrderLifecycleState.CANCELLED,
            OrderLifecycleState.EXPIRED,
        }
        lifecycle_order_ids = {
            event.broker_order_id
            for event in lifecycle_current.values()
            if event.broker_order_id is not None
            and event.state not in _terminal_states
        }
        known_order_ids = trade_order_ids | lifecycle_order_ids
        for order in open_orders:
            if not order.is_active or order.order_id is None:
                continue
            if order.order_id not in known_order_ids and order.action == "BUY":
                issues.append(RecoveryIssue(
                    code="unmatched_broker_entry_order",
                    severity=RECOVERY,
                    message=(
                        f"Broker has active BUY order {order.order_id} for "
                        f"{order.symbol} without a matching autonomous trade/lifecycle record."
                    ),
                    details=order.to_dict(),
                ))
        return issues

    def _lifecycle_issues(
        self,
        open_trades: Sequence[AutonomousTrade],
        lifecycle_current: Dict[str, OrderLifecycleEvent],
    ) -> List[RecoveryIssue]:
        issues: List[RecoveryIssue] = []
        open_trade_ids = {trade.autonomous_trade_id for trade in open_trades}
        recovery_states = {
            OrderLifecycleState.RECOVERY_REQUIRED,
            OrderLifecycleState.BROKER_DISCONNECTED,
            OrderLifecycleState.ORPHANED_ORDER,
        }
        monitor_states = {
            OrderLifecycleState.DUPLICATE_ORDER_BLOCKED,
        }
        for event in lifecycle_current.values():
            if event.state in recovery_states and (
                event.autonomous_trade_id in open_trade_ids
                or event.state == OrderLifecycleState.ORPHANED_ORDER
            ):
                issues.append(RecoveryIssue(
                    code="lifecycle_recovery_state",
                    severity=RECOVERY,
                    message=(
                        f"Lifecycle {event.lifecycle_id} for "
                        f"{event.symbol} is {event.state.value}."
                    ),
                    details=event.to_dict(),
                ))
            elif event.state in monitor_states:
                issues.append(RecoveryIssue(
                    code="lifecycle_monitor_state",
                    severity=WARNING,
                    message=(
                        f"Lifecycle {event.lifecycle_id} for "
                        f"{event.symbol} is {event.state.value}; operator review is advised."
                    ),
                    details=event.to_dict(),
                ))
        return issues

    def _idempotency_issues(
        self,
        active_locks: Sequence[IdempotencyLock],
        stale_locks: Sequence[IdempotencyLock],
        trades: Sequence[AutonomousTrade],
    ) -> List[RecoveryIssue]:
        issues: List[RecoveryIssue] = []
        trades_by_id = {trade.autonomous_trade_id: trade for trade in trades}
        stale_keys = {lock.key for lock in stale_locks}
        for lock in active_locks:
            trade = trades_by_id.get(lock.autonomous_trade_id or "")
            if lock.key in stale_keys:
                issues.append(RecoveryIssue(
                    code="stale_idempotency_lock",
                    severity=RECOVERY,
                    message=(
                        f"Active idempotency lock {lock.key} is stale and "
                        "must be inspected or cleared before trading resumes."
                    ),
                    details=lock.to_dict(),
                ))
                continue
            if not lock.autonomous_trade_id or trade is None:
                issues.append(RecoveryIssue(
                    code="idempotency_lock_without_trade",
                    severity=RECOVERY,
                    message=(
                        f"Active idempotency lock {lock.key} has no matching "
                        "local autonomous trade."
                    ),
                    details=lock.to_dict(),
                ))
                continue
            if trade.status in {CLOSED, FAILED}:
                issues.append(RecoveryIssue(
                    code="idempotency_lock_terminal_trade",
                    severity=WARNING,
                    message=(
                        f"Active idempotency lock {lock.key} points to terminal "
                        f"trade {trade.autonomous_trade_id}."
                    ),
                    details=lock.to_dict(),
                ))
        return issues

    @staticmethod
    def _protection_issues(
        protection_results: Sequence[ProtectionVerificationResult],
    ) -> List[RecoveryIssue]:
        issues: List[RecoveryIssue] = []
        for result in protection_results:
            if not result.recovery_required:
                continue
            issues.append(RecoveryIssue(
                code="broker_protection_missing",
                severity=RECOVERY,
                message=(
                    f"Broker-side protection is not confirmed for "
                    f"{result.symbol} trade {result.autonomous_trade_id}: "
                    f"{result.reason}"
                ),
                details=result.to_dict(),
            ))
        return issues

    @staticmethod
    def _risk_lifecycle_issues(
        risk_lifecycle: Optional[Dict[str, Any]],
    ) -> List[RecoveryIssue]:
        if not risk_lifecycle:
            return []
        allowed = risk_lifecycle.get("allowed")
        blocked = risk_lifecycle.get("blocked")
        if allowed is False or blocked is True:
            return [RecoveryIssue(
                code="risk_lifecycle_blocks_trading",
                severity=RECOVERY,
                message="Risk lifecycle currently blocks autonomous trading.",
                details=dict(risk_lifecycle),
            )]
        return []

    @staticmethod
    def _recent_execution_issues(
        recent_executions: Optional[Iterable[Dict[str, Any]]],
        trades: Sequence[AutonomousTrade],
    ) -> List[RecoveryIssue]:
        if recent_executions is None:
            return []
        known_order_ids = {
            _as_int(order_id)
            for trade in trades
            for order_id in (trade.entry_order_id, trade.exit_order_id, trade.target_order_id, trade.stop_order_id)
            if _as_int(order_id) is not None
        }
        issues: List[RecoveryIssue] = []
        for execution in recent_executions:
            order_id = _as_int(
                execution.get("order_id")
                or execution.get("broker_order_id")
                or execution.get("orderId")
            )
            if order_id is None or order_id in known_order_ids:
                continue
            issues.append(RecoveryIssue(
                code="unmatched_recent_execution",
                severity=RECOVERY,
                message=(
                    f"Recent broker execution for order {order_id} has no "
                    "matching autonomous trade record."
                ),
                details=dict(execution),
            ))
        return issues

    @staticmethod
    def _classify(issues: Sequence[RecoveryIssue]) -> RecoveryClassification:
        severities = {issue.severity for issue in issues}
        if MANUAL in severities:
            return RecoveryClassification.MANUAL_INTERVENTION_REQUIRED
        if RECOVERY in severities:
            return RecoveryClassification.RECOVERY_REQUIRED
        if WARNING in severities:
            return RecoveryClassification.SAFE_TO_MONITOR_ONLY
        return RecoveryClassification.SAFE_TO_TRADE


def _position_quantity(position: Any) -> float:
    if position is None:
        return 0.0
    if isinstance(position, dict):
        for key in ("quantity", "position", "shares"):
            if key in position:
                return _as_float(position[key])
        return 0.0
    for key in ("quantity", "position", "shares"):
        value = getattr(position, key, None)
        if value is not None:
            return _as_float(value)
    return 0.0


def _is_dry_run_trade(trade: AutonomousTrade) -> bool:
    return any(str(note).strip().lower() == "dry_run=true" for note in (trade.notes or []))


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
