from __future__ import annotations

import time

from autonomous.lifecycle_worker import AutonomousLifecycleWorker


def _wait_until(predicate, timeout=1.0, step=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def test_stop_before_initial_delay_prevents_tick():
    ticks = []
    worker = AutonomousLifecycleWorker(
        name="test-worker-delay",
        is_active=lambda: True,
        tick=lambda: ticks.append("tick"),
        interval_seconds=0.1,
        initial_delay_seconds=1.0,
    )

    worker.start()
    worker.stop()

    assert _wait_until(lambda: not worker.running, timeout=0.5)
    assert ticks == []


def test_inactive_worker_exits_without_ticking():
    ticks = []
    worker = AutonomousLifecycleWorker(
        name="test-worker-inactive",
        is_active=lambda: False,
        tick=lambda: ticks.append("tick"),
        interval_seconds=0.1,
        initial_delay_seconds=0.0,
    )

    worker.start()

    assert _wait_until(lambda: not worker.running, timeout=0.5)
    assert ticks == []


def test_stop_during_interval_exits_promptly_without_extra_ticks():
    ticks = []
    worker = AutonomousLifecycleWorker(
        name="test-worker-stop",
        is_active=lambda: True,
        tick=lambda: ticks.append("tick"),
        interval_seconds=10.0,
        initial_delay_seconds=0.0,
    )

    worker.start()
    assert _wait_until(lambda: len(ticks) == 1, timeout=0.5)
    worker.stop()

    assert _wait_until(lambda: not worker.running, timeout=0.5)
    assert ticks == ["tick"]
