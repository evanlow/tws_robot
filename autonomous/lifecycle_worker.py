"""Background lifecycle loop for Autonomous Mode.

The worker is deliberately small and dependency-injected.  API routes provide
the actual tick function so the same loop can be used for paper and live mode
without importing Flask inside this module.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AutonomousLifecycleWorker:
    """Run a lifecycle tick repeatedly until mode is turned off."""

    def __init__(
        self,
        *,
        name: str,
        is_active: Callable[[], bool],
        tick: Callable[[], None],
        interval_seconds: float = 60.0,
        initial_delay_seconds: Optional[float] = None,
    ) -> None:
        self.name = name
        self._is_active = is_active
        self._tick = tick
        self._interval = max(1.0, float(interval_seconds))
        if initial_delay_seconds is None:
            initial_delay_seconds = self._interval
        self._initial_delay = max(0.0, float(initial_delay_seconds))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=self.name,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> None:
        if self._is_active():
            self._tick()

    def _loop(self) -> None:
        if self._initial_delay and self._stop.wait(self._initial_delay):
            return
        while not self._stop.is_set():
            if not self._is_active():
                return
            try:
                self._tick()
            except Exception:
                logger.exception("%s lifecycle tick failed", self.name)
            if self._stop.wait(self._interval):
                return
