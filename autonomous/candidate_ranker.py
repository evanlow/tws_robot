"""Ranking rules for autonomous trading candidates.

Filtering and ranking is separated from the scanner so that:

* Tests can build ranker fixtures without touching CSV or providers.
* Ranking rules can be tuned (or replaced) without rewriting the engine.

Hard filters still run first.  Expected-edge ranking cannot bypass minimum
signal strength, signal label, trend/volume, earnings, or concentration gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.edge_estimator import EdgeEstimate, RuleBasedEdgeEstimator
from autonomous.feature_builder import FeatureBuilder

logger = logging.getLogger(__name__)


@dataclass
class RankedCandidate:
    """A scored candidate produced by :class:`CandidateRanker`."""

    candidate: CandidateSignal
    score: float
    reasons: List[str]
    features: Dict[str, Any] = field(default_factory=dict)
    edge_estimate: Optional[EdgeEstimate] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "score": round(self.score, 6),
            "reasons": list(self.reasons),
            "features": dict(self.features),
            "edge_estimate": self.edge_estimate.to_dict() if self.edge_estimate is not None else None,
        }


class CandidateRanker:
    """Filter and rank :class:`CandidateSignal` objects."""

    def __init__(
        self,
        config: AutonomousTradingConfig,
        feature_builder: Optional[FeatureBuilder] = None,
        edge_estimator: Optional[RuleBasedEdgeEstimator] = None,
    ) -> None:
        self.config = config
        self.feature_builder = feature_builder or FeatureBuilder()
        self.edge_estimator = edge_estimator or RuleBasedEdgeEstimator()

    def _earnings_too_close(self, candidate: CandidateSignal, today: Optional[date] = None) -> bool:
        if candidate.earnings_date is None:
            return False
        ref = today or date.today()
        delta = candidate.earnings_date - ref
        return abs(delta) <= timedelta(days=self.config.avoid_earnings_within_days)

    def _already_over_concentrated(
        self,
        candidate: CandidateSignal,
        positions: Dict[str, Dict[str, Any]],
        equity: float,
    ) -> bool:
        if not positions or equity <= 0:
            return False
        pos = positions.get(candidate.symbol)
        if not pos:
            return False
        market_value = abs(float(pos.get("market_value", 0.0)))
        if market_value <= 0:
            return False
        return (market_value / equity) >= self.config.equity_cap_pct()

    def _passes_hard_filters(
        self,
        candidate: CandidateSignal,
        positions: Dict[str, Dict[str, Any]],
        equity: float,
        today: Optional[date],
    ) -> Optional[str]:
        if candidate.strength_score < self.config.min_signal_strength:
            return f"strength_score {candidate.strength_score} < min {self.config.min_signal_strength}"
        if candidate.signal_label != self.config.required_signal_label:
            return f"signal_label {candidate.signal_label!r} != required {self.config.required_signal_label!r}"
        if not candidate.volume_ok:
            return "volume_ok=False"
        if not candidate.trend_ok:
            return "trend_ok=False"
        if self._earnings_too_close(candidate, today):
            return f"earnings within {self.config.avoid_earnings_within_days} days"
        if self._already_over_concentrated(candidate, positions, equity):
            return "symbol already over-concentrated in portfolio"
        return None

    def _base_score(self, candidate: CandidateSignal) -> float:
        score = float(candidate.strength_score)
        last = candidate.last_price or 0.0
        sup = candidate.support_price
        res = candidate.resistance_price
        if last > 0 and sup is not None and sup > 0 and last >= sup:
            distance_from_sup = (last - sup) / last
            score += max(0.0, 0.20 - distance_from_sup)
        if last > 0 and res is not None and res > last:
            room_to_res = (res - last) / last
            score += min(0.30, room_to_res)
        return score

    def _ranked_candidate(
        self,
        candidate: CandidateSignal,
        *,
        market_gate: Optional[Dict[str, Any]],
    ) -> tuple[Optional[RankedCandidate], Optional[str]]:
        base_score = self._base_score(candidate)
        reasons = [
            f"strength_score={candidate.strength_score}",
            f"signal_label={candidate.signal_label}",
        ]
        features: Dict[str, Any] = {}
        edge_estimate: Optional[EdgeEstimate] = None
        score = base_score

        if self.config.edge_ranking_enabled:
            try:
                features = self.feature_builder.build(candidate, market_gate=market_gate)
                edge_estimate = self.edge_estimator.estimate(features)
            except Exception:
                logger.exception("edge estimation failed for %s", candidate.symbol)
                edge_estimate = None
                features = {}

            if edge_estimate is not None:
                candidate.extras["features"] = dict(features)
                candidate.extras["edge_estimate"] = edge_estimate.to_dict()
                # Later evidence calibration can set this value.  Keep an
                # explicit zero so the fractional sizing overlay knows that
                # bootstrap estimates are not yet evidence-backed.
                candidate.extras.setdefault("edge_observed_trades", 0)
                if edge_estimate.expected_r < self.config.min_expected_r:
                    return None, f"expected_r {edge_estimate.expected_r:.4f} < min {self.config.min_expected_r:.4f}"
                if edge_estimate.confidence < self.config.min_edge_confidence:
                    return None, f"edge_confidence {edge_estimate.confidence:.4f} < min {self.config.min_edge_confidence:.4f}"
                edge_component = edge_estimate.expected_r * self.config.edge_score_weight
                score = base_score + edge_component
                reasons.append(f"expected_r={edge_estimate.expected_r:.4f}")
                reasons.append(f"edge_confidence={edge_estimate.confidence:.4f}")
                reasons.append(f"edge_score_component={edge_component:.4f}")

        return RankedCandidate(
            candidate=candidate,
            score=score,
            reasons=reasons,
            features=features,
            edge_estimate=edge_estimate,
        ), None

    def rank(
        self,
        candidates: Sequence[CandidateSignal],
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        equity: float = 0.0,
        today: Optional[date] = None,
        market_gate: Optional[Dict[str, Any]] = None,
    ) -> List[RankedCandidate]:
        ranked, _rejections = self.rank_with_rejections(
            candidates,
            positions=positions,
            equity=equity,
            today=today,
            market_gate=market_gate,
        )
        return ranked

    def rank_with_rejections(
        self,
        candidates: Sequence[CandidateSignal],
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        equity: float = 0.0,
        today: Optional[date] = None,
        market_gate: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[RankedCandidate], List[Dict[str, Any]]]:
        positions = positions or {}
        ranked: List[RankedCandidate] = []
        rejected: List[Dict[str, Any]] = []
        for candidate in candidates:
            reason = self._passes_hard_filters(candidate, positions, equity, today)
            if reason is not None:
                rejected.append({"symbol": candidate.symbol, "reason": reason})
                continue
            ranked_candidate, edge_rejection = self._ranked_candidate(candidate, market_gate=market_gate)
            if edge_rejection is not None:
                rejected.append({"symbol": candidate.symbol, "reason": edge_rejection})
                continue
            if ranked_candidate is not None:
                ranked.append(ranked_candidate)
        ranked.sort(key=lambda rc: rc.score, reverse=True)
        return ranked, rejected

    def pick_best(
        self,
        candidates: Sequence[CandidateSignal],
        positions: Optional[Dict[str, Dict[str, Any]]] = None,
        equity: float = 0.0,
        today: Optional[date] = None,
        market_gate: Optional[Dict[str, Any]] = None,
    ) -> Optional[RankedCandidate]:
        ranked = self.rank(
            candidates,
            positions=positions,
            equity=equity,
            today=today,
            market_gate=market_gate,
        )
        return ranked[0] if ranked else None
