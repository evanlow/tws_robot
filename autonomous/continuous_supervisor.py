"""Continuous autonomous run supervisor.

The supervisor coordinates repeated autonomous cycles without owning strategy
logic or broker order placement. It is dependency-injected so it can wrap the
existing live runner/API tick path and fail closed when operational faults are
detected.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional


IDLE = "IDLE"
RUNNING = "RUNNING"
PAUSED = "PAUSED"
SKIPPED = "SKIPPED"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

BROKER_DISCONNECTED = "broker_disconnected"
EMERGENCY_STOP_ACTIVE = "emergency_stop_active"
UNRECONCILED_LIFECYCLE_STATE = "unreconciled_lifecycle_state"
RISK_LIFECYCLE_BREACH = "risk_lifecycle_breach"
OVERLAPPING_RUN = "overlapping_run"
CADENCE_WAIT = "cadence_wait"
MANUAL_PAUSE = "manual_pause"
TICK_EXCEPTION = "tick_exception"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


@dataclass
class SupervisorFault:
    """Operational condition that should pause continuous autonomous cycles."""

    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass
class SupervisorCycleResult:
    """Result from one supervisor-managed cycle attempt."""

    status: str
    reason: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Any = None
    fault: Optional[SupervisorFault] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "result": (
                self.result.to_dict()
                if hasattr(self.result, "to_dict")
                else self.result
            ),
            "fault": self.fault.to_dict() if self.fault is not None else None,
        }


class ContinuousSupervisor:
    """Coordinate safe repeated autonomous cycles.

    ``tick`` remains the owner of actual work. The supervisor only decides
    whether a cycle may start, prevents overlap, records heartbeat/status, and
    pauses when injected gate/fault checks report serious operational risk.
    """

    def __init__(
        self,
        *,
        name: str = "AutonomousContinuousSupervisor",
        cadence_seconds: float = 60.0,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.name = name
        self._cadence = max(1.0, float(cadence_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._paused = False
        self._pause_reason: Optional[str] = None
        self._pause_message: Optional[str] = None
        self._heartbeat_at: Optional[datetime] = None
        self._last_started_at: Optional[datetime] = None
        self._last_finished_at: Optional[datetime] = None
        self._last_success_at: Optional[datetime] = None
        self._next_eligible_at: Optional[datetime] = None
        self._last_result: Optional[SupervisorCycleResult] = None
        self._last_error: Optional[str] = None
        self._cycles_started = 0
        self._cycles_completed = 0
        self._cycles_failed = 0
        self._overlap_blocks = 0
        self._cadence_skips = 0

    @property
    def paused(self) -> bool:
        with self._state_lock:
            return self._paused

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def pause(self, reason: str = MANUAL_PAUSE, message: Optional[str] = None) -> None:
        with self._state_lock:
            self._paused = True
            self._pause_reason = reason
            self._pause_message = message or reason

    def resume(self) -> None:
        with self._state_lock:
            self._paused = False
            self._pause_reason = None
            self._pause_message = None
            self._last_error = None

    def heartbeat(self) -> None:
        with self._state_lock:
            self._heartbeat_at = self._clock()

    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            if self._paused:
                state = PAUSED
            elif self.running:
                state = RUNNING
            else:
                state = IDLE
            return {
                "name": self.name,
                "state": state,
                "paused": self._paused,
                "pause_reason": self._pause_reason,
                "pause_message": self._pause_message,
                "running": self.running,
                "heartbeat_at": _iso(self._heartbeat_at),
                "last_started_at": _iso(self._last_started_at),
                "last_finished_at": _iso(self._last_finished_at),
                "last_success_at": _iso(self._last_success_at),
                "next_eligible_at": _iso(self._next_eligible_at),
                "last_error": self._last_error,
                "cycles_started": self._cycles_started,
                "cycles_completed": self._cycles_completed,
                "cycles_failed": self._cycles_failed,
                "overlap_blocks": self._overlap_blocks,
                "cadence_skips": self._cadence_skips,
                "last_result": (
                    self._last_result.to_dict()
                    if self._last_result is not None
                    else None
                ),
            }

    def run_cycle(
        self,
        tick: Callable[[], Any],
        *,
        gates_provider: Optional[Callable[[], Any]] = None,
        fault_provider: Optional[Callable[[], Iterable[SupervisorFault]]] = None,
        result_fault_provider: Optional[Callable[[Any], Optional[SupervisorFault]]] = None,
    ) -> SupervisorCycleResult:
        """Run one supervised cycle if cadence and safety checks allow it."""

        now = self._clock()
        with self._state_lock:
            self._heartbeat_at = now
            if self._paused:
                result = SupervisorCycleResult(status=SKIPPED, reason=PAUSED)
                self._last_result = result
                return result
            if self._next_eligible_at is not None and now < self._next_eligible_at:
                self._cadence_skips += 1
                result = SupervisorCycleResult(status=SKIPPED, reason=CADENCE_WAIT)
                self._last_result = result
                return result

        if not self._lock.acquire(blocking=False):
            with self._state_lock:
                self._overlap_blocks += 1
                result = SupervisorCycleResult(status=SKIPPED, reason=OVERLAPPING_RUN)
                self._last_result = result
                return result

        started = self._clock()
        with self._state_lock:
            self._last_started_at = started
            self._cycles_started += 1

        try:
            fault = self._first_fault(fault_provider, gates_provider)
            if fault is not None:
                return self._pause_with_fault(fault, started)

            value = tick()
            if result_fault_provider is not None:
                fault = result_fault_provider(value)
                if fault is not None:
                    return self._pause_with_fault(fault, started, result=value)

            finished = self._clock()
            result = SupervisorCycleResult(
                status=COMPLETED,
                started_at=started,
                finished_at=finished,
                result=value,
            )
            with self._state_lock:
                self._last_finished_at = finished
                self._last_success_at = finished
                self._next_eligible_at = finished + timedelta(seconds=self._cadence)
                self._cycles_completed += 1
                self._last_result = result
                self._last_error = None
            return result
        except Exception as exc:
            fault = SupervisorFault(TICK_EXCEPTION, str(exc) or exc.__class__.__name__)
            return self._pause_with_fault(fault, started)
        finally:
            self._lock.release()

    def _first_fault(
        self,
        fault_provider: Optional[Callable[[], Iterable[SupervisorFault]]],
        gates_provider: Optional[Callable[[], Any]],
    ) -> Optional[SupervisorFault]:
        if fault_provider is not None:
            for fault in fault_provider() or []:
                if fault is not None:
                    return fault
        if gates_provider is None:
            return None
        return _fault_from_gates(gates_provider())

    def _pause_with_fault(
        self,
        fault: SupervisorFault,
        started: datetime,
        *,
        result: Any = None,
    ) -> SupervisorCycleResult:
        finished = self._clock()
        cycle_result = SupervisorCycleResult(
            status=PAUSED,
            reason=fault.code,
            started_at=started,
            finished_at=finished,
            result=result,
            fault=fault,
        )
        with self._state_lock:
            self._paused = True
            self._pause_reason = fault.code
            self._pause_message = fault.message
            self._last_finished_at = finished
            self._next_eligible_at = finished + timedelta(seconds=self._cadence)
            self._cycles_failed += 1
            self._last_error = fault.message
            self._last_result = cycle_result
        return cycle_result


def _fault_from_gates(gates: Any) -> Optional[SupervisorFault]:
    """Infer supervisor faults from a LiveReadinessGates-like object."""

    if gates is None:
        return None
    if not bool(getattr(gates, "connected", True)):
        return SupervisorFault(
            BROKER_DISCONNECTED,
            "Broker disconnected; continuous supervisor paused.",
        )
    if bool(getattr(gates, "emergency_stop_active", False)):
        return SupervisorFault(
            EMERGENCY_STOP_ACTIVE,
            "Emergency stop active; continuous supervisor paused.",
        )
    protection_required = int(getattr(gates, "protection_recovery_required", 0) or 0)
    protection_confirmed = bool(getattr(gates, "protection_confirmed", True))
    if protection_required > 0 or not protection_confirmed:
        return SupervisorFault(
            UNRECONCILED_LIFECYCLE_STATE,
            "Unreconciled protection/lifecycle state requires recovery.",
            {"protection_recovery_required": protection_required},
        )
    if bool(getattr(gates, "recovery_required", False)):
        diagnostics = getattr(gates, "recovery_diagnostics", {}) or {}
        return SupervisorFault(
            UNRECONCILED_LIFECYCLE_STATE,
            "Restart recovery/broker reconciliation requires operator action.",
            {
                "recovery_classification": getattr(
                    gates,
                    "recovery_classification",
                    None,
                ),
                "recovery_diagnostics": diagnostics,
            },
        )
    return None
