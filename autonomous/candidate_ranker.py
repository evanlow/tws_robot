"""Ranking rules for autonomous trading candidates.

Filtering and ranking is separated from the scanner so that:

* Tests can build ranker fixtures without touching CSV or providers.
* Ranking rules can be tuned (or replaced) without rewriting the engine.

Rules (per the issue):

* Must satisfy ``strength_score >= min_signal_strength``.
* Must satisfy ``signal_label == required_signal_label``.
* Must have ``volume_ok`` and ``trend_ok``.
* Earnings within ``avoid_earnings_within_days`` disqualifies the candidate.
* Symbols already over-concentrated in the current portfolio are filtered.
* Among the survivors:

    - Closer to support (further below resistance) ranks higher, *but* only
      when the price has clearly rebounded off support.
    - Higher strength score wins ties.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal

logger = logging.getLogger(__name__)


@dataclass
class RankedCandidate:
    """A scored candidate produced by :class:`CandidateRanker`."""

    candidate: CandidateSignal
    score: float
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "score": round(self.score, 6),
            "reasons": list(self.reasons),
        }


class CandidateRanker:
    """Filter and rank :class:`CandidateSignal` objects.

    The ranker is configured with the same :class:`AutonomousTradingConfig`
    as the rest of the engine so it stays consistent with the safety
    thresholds.
    """

    def __init__(self, config: AutonomousTradingConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _earnings_too_close(
        self,
        candidate: CandidateSignal,
        today: Optional[date] = None,
    ) -> bool:
        if candidate.earnings_date is None:
            return False
        ref = today or date.today()
        delta = candidate.earnings_date - ref
        # Reject candidates whose earnings are in the configured window
        # (in either direction — same-day earnings are also disqualifying).
        return abs(delta) <= timedelta(days=self.config.avoid_earnings_within_days)

    def _already_over_concentrated(
        self,
        candidate: CandidateSignal,
        positions: Dict[str, Dict[str, Any]],
        equity: float,
    ) -> bool:
        """Return True if the existing position in ``candidate.symbol`` is
        already at-or-above the configured per-position size limit.
        """
        if not positions or equity <= 0:
            return False
        pos = positions.get(candidate.symbol)
        if not pos:
            return False
        market_value = abs(float(pos.get("market_value", 0.0)))
        if market_value <= 0:
            return False
        return (market_value / equity) >= self.config.max_new_position_pct

    def _passes_hard_filters(
        self,
        candidate: CandidateSignal,
        positions: Dict[str, Dict[str, Any]],
        equity: float,
        today: Optional[date],
    ) -> Optional[str]:
        """Return ``None`` when the candidate passes, otherwise the reason
        string explaining the rejection.  Reason strings are stable and
        used in the audit log.
        """
        if candidate.strength_score < self.config.min_signal_strength:
            return (
                f"strength_score {candidate.strength_score} "
                f"< min {self.config.min_signal_strength}"
            )
        if candidate.signal_label != self.config.required_signal_label:
            return (
                f"signal_label {candidate.signal_label!r} != required "
                f"{self.config.required_signal_label!r}"
            )
        if not candidate.volume_ok:
            return "volume_ok=False"
        if not candidate.trend_ok:
            return "trend_ok=False"
        if self._earnings_too_close(candidate, today):
            return (
                f"earnings within {self.config.avoid_earnings_within_days} days"
            )
        if self._already_over_concentrated(candidate, positions, equity):
            return "symbol already over-concentrated in portfolio"
        return None

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(self, candidate: CandidateSignal) -> float:
        """Higher score = better candidate.

        Components (in priority order):

        * strength_score (dominant term).
        * proximity to support (closer to support but above it → higher).
        * room to resistance (further below resistance → higher).
        """
        score = float(candidate.strength_score)

        last = candidate.last_price or 0.0
        sup = candidate.support_price
        res = candidate.resistance_price

        if last > 0 and sup is not None and sup > 0 and last >= sup:
            # 0.0 when price == support, grows as price pulls away from
            # support; we want price *close to* support, so we invert.
            distance_from_sup = (last - sup) / last
            score += max(0.0, 0.20 - distance_from_sup)  # up to +0.20

        if last > 0 and res is not None and res > last:
            # Reward room left up to resistance.
            room_to_res = (res - last) / last
            score += min(0.30, room_to_res)  # cap at +0.30

        return score

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def rank(
        self,
        candidates: Sequence[CandidateSignal],
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        equity: float = 0.0,
        today: Optional[date] = None,
    ) -> List[RankedCandidate]:
        """Return surviving candidates, best first.

        The returned list contains only the candidates that pass the hard
        filters; rejected candidates are logged but not returned.  Callers
        that need the rejection set should call :meth:`rank_with_rejections`.
        """
        ranked, _rejections = self.rank_with_rejections(
            candidates, positions=positions, equity=equity, today=today
        )
        return ranked

    def rank_with_rejections(
        self,
        candidates: Sequence[CandidateSignal],
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        equity: float = 0.0,
        today: Optional[date] = None,
    ) -> tuple[List[RankedCandidate], List[Dict[str, Any]]]:
        positions = positions or {}
        ranked: List[RankedCandidate] = []
        rejected: List[Dict[str, Any]] = []
        for candidate in candidates:
            reason = self._passes_hard_filters(candidate, positions, equity, today)
            if reason is not None:
                rejected.append({"symbol": candidate.symbol, "reason": reason})
                continue
            ranked.append(
                RankedCandidate(
                    candidate=candidate,
                    score=self._score(candidate),
                    reasons=[
                        f"strength_score={candidate.strength_score}",
                        f"signal_label={candidate.signal_label}",
                    ],
                )
            )
        ranked.sort(key=lambda rc: rc.score, reverse=True)
        return ranked, rejected

    def pick_best(
        self,
        candidates: Sequence[CandidateSignal],
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        equity: float = 0.0,
        today: Optional[date] = None,
    ) -> Optional[RankedCandidate]:
        ranked = self.rank(candidates, positions=positions, equity=equity, today=today)
        return ranked[0] if ranked else None
