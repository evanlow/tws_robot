from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from autonomous.autonomous_live_runner import LiveReadinessGates
from autonomous.continuous_supervisor import (
    BROKER_DISCONNECTED,
    CADENCE_WAIT,
    COMPLETED,
    EMERGENCY_STOP_ACTIVE,
    OVERLAPPING_RUN,
    PAUSED,
    RISK_LIFECYCLE_BREACH,
    SKIPPED,
    TICK_EXCEPTION,
    UNRECONCILED_LIFECYCLE_STATE,
    ContinuousSupervisor,
    SupervisorFault,
)


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass
class _Result:
    status: str

    def to_dict(self):
        return {"status": self.status}


def test_runs_cycle_records_heartbeat_and_status():
    clock = _Clock()
    supervisor = ContinuousSupervisor(cadence_seconds=30, clock=clock)

    result = supervisor.run_cycle(lambda: _Result("ok"))

    assert result.status == COMPLETED
    status = supervisor.status()
    assert status["state"] == "IDLE"
    assert status["heartbeat_at"] == "2026-01-01T14:30:00+00:00"
    assert status["cycles_started"] == 1
    assert status["cycles_completed"] == 1
    assert status["last_result"]["result"] == {"status": "ok"}
    assert status["next_eligible_at"] == "2026-01-01T14:30:30+00:00"


def test_cadence_prevents_too_frequent_cycles():
    clock = _Clock()
    supervisor = ContinuousSupervisor(cadence_seconds=60, clock=clock)
    calls = []

    supervisor.run_cycle(lambda: calls.append("first"))
    second = supervisor.run_cycle(lambda: calls.append("second"))

    assert second.status == SKIPPED
    assert second.reason == CADENCE_WAIT
    assert calls == ["first"]
    assert supervisor.status()["cadence_skips"] == 1

    clock.advance(60)
    third = supervisor.run_cycle(lambda: calls.append("third"))
    assert third.status == COMPLETED
    assert calls == ["first", "third"]


def test_prevents_overlapping_cycles():
    clock = _Clock()
    supervisor = ContinuousSupervisor(cadence_seconds=1, clock=clock)
    entered = threading.Event()
    release = threading.Event()
    results = []

    def slow_tick():
        entered.set()
        release.wait(timeout=5)
        return "done"

    worker = threading.Thread(target=lambda: results.append(supervisor.run_cycle(slow_tick)))
    worker.start()
    assert entered.wait(timeout=5)

    blocked = supervisor.run_cycle(lambda: "should-not-run")
    release.set()
    worker.join(timeout=5)

    assert blocked.status == SKIPPED
    assert blocked.reason == OVERLAPPING_RUN
    assert results[0].status == COMPLETED
    assert supervisor.status()["overlap_blocks"] == 1


def test_manual_pause_and_resume():
    supervisor = ContinuousSupervisor()
    supervisor.pause("operator_pause", "operator paused continuous mode")

    skipped = supervisor.run_cycle(lambda: "nope")
    assert skipped.status == SKIPPED
    assert skipped.reason == PAUSED
    assert supervisor.status()["pause_reason"] == "operator_pause"

    supervisor.resume()
    ran = supervisor.run_cycle(lambda: "ok")
    assert ran.status == COMPLETED
    assert supervisor.status()["paused"] is False


def test_disconnected_gate_pauses_supervisor():
    supervisor = ContinuousSupervisor()
    gates = LiveReadinessGates(connected=False)

    result = supervisor.run_cycle(lambda: "nope", gates_provider=lambda: gates)

    assert result.status == PAUSED
    assert result.reason == BROKER_DISCONNECTED
    assert supervisor.paused is True
    assert supervisor.status()["pause_reason"] == BROKER_DISCONNECTED


def test_emergency_stop_gate_pauses_supervisor():
    supervisor = ContinuousSupervisor()
    gates = LiveReadinessGates(connected=True, emergency_stop_active=True)

    result = supervisor.run_cycle(lambda: "nope", gates_provider=lambda: gates)

    assert result.status == PAUSED
    assert result.reason == EMERGENCY_STOP_ACTIVE


def test_unreconciled_protection_gate_pauses_supervisor():
    supervisor = ContinuousSupervisor()
    gates = LiveReadinessGates(
        connected=True,
        protection_confirmed=False,
        protection_recovery_required=2,
    )

    result = supervisor.run_cycle(lambda: "nope", gates_provider=lambda: gates)

    assert result.status == PAUSED
    assert result.reason == UNRECONCILED_LIFECYCLE_STATE
    assert result.fault is not None
    assert result.fault.details["protection_recovery_required"] == 2


def test_fault_provider_can_pause_on_risk_lifecycle_breach():
    supervisor = ContinuousSupervisor()
    fault = SupervisorFault(
        RISK_LIFECYCLE_BREACH,
        "risk lifecycle blocked new entries",
        {"reason": "daily loss breached"},
    )

    result = supervisor.run_cycle(lambda: "nope", fault_provider=lambda: [fault])

    assert result.status == PAUSED
    assert result.reason == RISK_LIFECYCLE_BREACH
    assert supervisor.status()["last_error"] == "risk lifecycle blocked new entries"


def test_tick_exception_pauses_supervisor():
    supervisor = ContinuousSupervisor()

    def explode():
        raise RuntimeError("boom")

    result = supervisor.run_cycle(explode)

    assert result.status == PAUSED
    assert result.reason == TICK_EXCEPTION
    assert supervisor.status()["cycles_failed"] == 1
