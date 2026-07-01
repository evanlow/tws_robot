"""Adapter exposing valid Opening Range Breakout setups to the autonomous engine.

The autonomous trading engine (``autonomous.autonomous_engine.AutonomousTradingEngine``)
consumes :class:`~autonomous.candidate_scanner.CandidateSignal` objects produced by a
``SignalProvider``. This module adds an *optional* ``OpeningRangeSignalProvider`` so
runtime ORB setups (Phases 2.1-2.6: candle aggregation, the runtime ORB strategy,
recommend-only proposals, and paper execution) can flow through the same
orchestration layer (cash checks, ranking, planning, risk gates, evidence logging)
as the existing rebound scanner — without forcing ORB through the
``Confirmed Rebound`` / ``Strong(100)`` assumptions used by
:class:`~autonomous.technical_analysis_signal_provider.TechnicalAnalysisSignalProvider`.

This adapter performs *no* ORB detection itself. It is handed a ``setup_source``
callable that returns the current, still-valid
:class:`~autonomous.opening_range.ORBSetup` for a symbol (or ``None``) and maps it
onto a :class:`~autonomous.candidate_scanner.CandidateSignal`.

Safety posture (Prime Directive):
- Long-only: setups with ``direction != ORBDirection.LONG`` are rejected. No
  short-side entries.
- Model C is out of scope for this adapter: only Model A (displacement/gap) and
  Model B (break/retest) setups produce candidates.
  ``ORBEntryModel.MODEL_C_REVERSAL`` setups are rejected.
- Malformed setups (missing/non-positive entry, stop, or target price; stop/target
  on the wrong side of entry; missing or non-positive risk/reward/R:R) are
  rejected — this adapter returns ``None`` rather than raising, so a single bad
  setup cannot poison the scan pipeline.
- Nothing here places, routes, or simulates an order. It only produces
  ``CandidateSignal`` objects for downstream ranking/planning; the planner
  (``autonomous.trade_planner.TradePlanner``) must still apply its own safety
  gates before any paper/live execution.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from autonomous.candidate_scanner import CandidateSignal
from autonomous.opening_range import ORBDirection, ORBEntryModel, ORBSetup

logger = logging.getLogger(__name__)

# Canonical ORB signal labels. These intentionally do *not* reuse
# "Confirmed Rebound" so the ranker/planner can distinguish ORB candidates
# from the existing rebound scanner and apply ORB-specific handling.
SIGNAL_LABEL_MODEL_A = "ORB_LONG_MODEL_A"
SIGNAL_LABEL_MODEL_B = "ORB_LONG_MODEL_B"

# ``CandidateSignal.extras["strategy"]`` marker used by ``TradePlanner`` to
# route a candidate through the ORB-aware planning branch instead of the
# rebound-scanner path. Shared as a constant so the provider and planner
# never drift out of sync.
STRATEGY_OPENING_RANGE_BREAKOUT = "opening_range_breakout"

# Model C (reversal) is explicitly out of scope for this adapter (non-goal).
_MODEL_LABELS: Dict[ORBEntryModel, str] = {
    ORBEntryModel.MODEL_A_DISPLACEMENT_GAP: SIGNAL_LABEL_MODEL_A,
    ORBEntryModel.MODEL_B_BREAK_RETEST: SIGNAL_LABEL_MODEL_B,
}

# Deterministic default strength score. This is high enough to clear the
# default ``min_signal_strength`` gate; deployments that have ORB
# evidence/calibration available can supply ``strength_score_provider``
# instead for an evidence-derived confidence value.
DEFAULT_STRENGTH_SCORE = 100

SetupSource = Callable[[str], Optional[ORBSetup]]


class OpeningRangeSignalProvider:
    """``SignalProvider`` adapter mapping valid ``ORBSetup`` objects onto ORB
    :class:`CandidateSignal` instances.

    Parameters
    ----------
    setup_source:
        Callable returning the current, still-valid ``ORBSetup`` for a symbol,
        or ``None`` if no setup exists / it has been invalidated. Typically
        backed by the runtime candle/strategy layer or the ORB proposal store.
    strength_score:
        Deterministic ``CandidateSignal.strength_score`` used when
        ``strength_score_provider`` is not supplied (or returns ``None``).
    strength_score_provider:
        Optional callable returning an evidence-derived confidence score for
        a given ``ORBSetup``. When it returns ``None`` the deterministic
        ``strength_score`` is used instead.
    """

    def __init__(
        self,
        setup_source: SetupSource,
        strength_score: int = DEFAULT_STRENGTH_SCORE,
        strength_score_provider: Optional[Callable[[ORBSetup], Optional[float]]] = None,
    ) -> None:
        self._setup_source = setup_source
        self._strength_score = strength_score
        self._strength_score_provider = strength_score_provider

    def analyze(self, symbol: str) -> Optional[CandidateSignal]:
        """Return an ORB :class:`CandidateSignal` for ``symbol`` or ``None``.

        Never raises: exceptions from ``setup_source`` or during mapping are
        logged and treated as "no signal" so a single misbehaving symbol
        cannot poison the scan pipeline.
        """
        try:
            setup = self._setup_source(symbol)
        except Exception:
            logger.exception("OpeningRangeSignalProvider: setup_source raised for %s", symbol)
            return None
        if setup is None:
            return None
        try:
            return self._setup_to_signal(symbol, setup)
        except Exception:
            logger.exception("OpeningRangeSignalProvider: failed to map ORBSetup for %s", symbol)
            return None

    def _setup_to_signal(self, symbol: str, setup: ORBSetup) -> Optional[CandidateSignal]:
        if setup.invalidation_reason:
            logger.debug("ORB setup for %s invalidated: %s", symbol, setup.invalidation_reason)
            return None
        if setup.direction != ORBDirection.LONG:
            # Non-goal: no short-side entries in this adapter.
            return None

        signal_label = _MODEL_LABELS.get(setup.model)
        if signal_label is None:
            # Model C (reversal) or any unrecognised model is out of scope.
            return None

        if not self._is_valid_setup(setup):
            return None

        strength_score = self._strength_score
        if self._strength_score_provider is not None:
            try:
                score = self._strength_score_provider(setup)
            except Exception:
                logger.exception(
                    "OpeningRangeSignalProvider: strength_score_provider raised for %s", symbol
                )
                score = None
            if score is not None:
                strength_score = score

        opening_range = setup.opening_range
        confirmation = setup.confirmation

        return CandidateSignal(
            symbol=symbol.upper(),
            strength_score=int(round(strength_score)),
            signal_label=signal_label,
            last_price=setup.entry_price,
            support_price=setup.stop_price,
            resistance_price=setup.target_price,
            technical_reason=(
                f"ORB {setup.model.value} breakout confirmed at "
                f"{confirmation.confirmed_at.isoformat()} (R/R={setup.rr_ratio:.2f})"
            ),
            volume_ok=True,
            trend_ok=True,
            extras={
                "strategy": STRATEGY_OPENING_RANGE_BREAKOUT,
                "setup_model": setup.model.value,
                "direction": setup.direction.value,
                "opening_range_high": opening_range.high,
                "opening_range_low": opening_range.low,
                "confirmation_time": confirmation.confirmed_at.isoformat(),
                "entry_price": setup.entry_price,
                "stop_price": setup.stop_price,
                "target_price": setup.target_price,
                "risk_per_share": setup.risk_per_share,
                "reward_per_share": setup.reward_per_share,
                "rr_ratio": setup.rr_ratio,
                "orb_evidence": dict(setup.evidence or {}),
            },
        )

    @staticmethod
    def _is_valid_setup(setup: ORBSetup) -> bool:
        """Reject malformed setups (Prime Directive: fail closed, not open)."""
        entry = setup.entry_price
        stop = setup.stop_price
        target = setup.target_price
        if entry is None or entry <= 0:
            return False
        if stop is None or stop <= 0:
            return False
        if target is None or target <= 0:
            return False
        # Long-only: stop must be below entry, target must be above entry.
        if not (stop < entry < target):
            return False
        if setup.risk_per_share is None or setup.risk_per_share <= 0:
            return False
        if setup.reward_per_share is None or setup.reward_per_share <= 0:
            return False
        if setup.rr_ratio is None or setup.rr_ratio <= 0:
            return False
        return True


class MappingOpeningRangeSetupSource:
    """Simple in-memory ``setup_source`` keyed by uppercase symbol.

    Convenient for tests and for wiring a single scan's worth of ORB setups
    (e.g. sourced from the runtime candle/strategy layer or the proposal
    store) into :class:`OpeningRangeSignalProvider` without a live feed.
    """

    def __init__(self, setups: Optional[Dict[str, ORBSetup]] = None) -> None:
        self._setups: Dict[str, ORBSetup] = {}
        if setups:
            for symbol, setup in setups.items():
                self._setups[symbol.upper()] = setup

    def set(self, symbol: str, setup: ORBSetup) -> None:
        self._setups[symbol.upper()] = setup

    def clear(self, symbol: Optional[str] = None) -> None:
        if symbol is None:
            self._setups.clear()
        else:
            self._setups.pop(symbol.upper(), None)

    def __call__(self, symbol: str) -> Optional[ORBSetup]:
        return self._setups.get(symbol.upper())
