"""Signal provider interface for the autonomous trading engine.

The autonomous engine doesn't perform any technical analysis itself.  It
delegates that to a ``SignalProvider`` so the rest of the orchestration
(cash availability, ranking, planning, execution gating) can be tested in
isolation, and so production deployments can plug in the real
``Strong(100)`` / ``Confirmed Rebound`` analyser without touching the
engine code.

Two implementations are shipped here:

* ``SignalProvider`` — the abstract protocol.
* ``StaticSignalProvider`` — a deterministic in-memory provider used by
  tests and by the API ``scan`` endpoint when no production provider is
  wired in.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Protocol, runtime_checkable

from autonomous.candidate_scanner import CandidateSignal


@runtime_checkable
class SignalProvider(Protocol):
    """Protocol returning a :class:`CandidateSignal` for a given symbol.

    Implementations should be deterministic for a given (symbol, time)
    pair and must not raise on unknown symbols — they should return
    ``None`` instead.  This keeps the scanner pipeline simple and lets
    callers count "no signal" symbols separately from errors.
    """

    def analyze(self, symbol: str) -> Optional[CandidateSignal]:  # pragma: no cover - protocol
        ...


class StaticSignalProvider:
    """Deterministic in-memory ``SignalProvider``.

    Useful for tests, demos, and the initial wiring of the autonomous
    engine when the production technical-analysis adapter is not yet
    available.  Symbols not present in the provided mapping return
    ``None`` from :meth:`analyze`.

    .. warning::

       This is **not** the production ``Strong(100)`` / ``Confirmed
       Rebound`` analyser.  When the autonomous web API is wired with
       this provider (the default), ``/scan`` and ``/propose`` will
       report ``no_candidate`` for the live universe.  The production
       adapter (planned: ``TechnicalAnalysisSignalProvider`` /
       ``StockAnalysisSignalProvider``) must be registered via
       ``current_app.config['autonomous_engine_factory']`` before the
       autonomous endpoints will return real candidates.
    """

    def __init__(self, signals: Optional[Iterable[CandidateSignal]] = None) -> None:
        self._signals: Dict[str, CandidateSignal] = {}
        if signals:
            for sig in signals:
                self._signals[sig.symbol.upper()] = sig

    def add(self, signal: CandidateSignal) -> None:
        """Register or replace the signal for ``signal.symbol``."""
        self._signals[signal.symbol.upper()] = signal

    def analyze(self, symbol: str) -> Optional[CandidateSignal]:
        return self._signals.get(symbol.upper())
