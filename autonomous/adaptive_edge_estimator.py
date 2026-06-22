"""Adaptive edge estimation from rule-based prior plus setup evidence.

This module is analytics-only.  It blends an existing rule-based
``EdgeEstimate`` with an EL3 ``SetupEvidenceSummary`` and does not change
candidate ranking, sizing, eligibility gates, risk controls, broker
connectivity, or order execution by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from autonomous.edge_estimator import EdgeEstimate
from autonomous.evidence_calibrator import (
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_RETIRED,
    SETUP_STATE_WEAK,
    SetupEvidenceSummary,
)


@dataclass(frozen=True)
class AdaptiveEdgeBlendConfig:
    """Conservative controls for blending prior and evidence estimates."""

    mature_sample_size: int = 100
    prior_trade_equivalent: int = 30
    max_evidence_weight: float = 0.85
    insufficient_evidence_max_weight: float = 0.20
    weak_evidence_min_weight: float = 0.60
    retired_evidence_min_weight: float = 0.75


class AdaptiveEdgeEstimator:
    """Blend a rule-based edge prior with realized setup evidence."""

    def __init__(self, config: Optional[AdaptiveEdgeBlendConfig] = None) -> None:
        self.config = config or AdaptiveEdgeBlendConfig()

    def estimate(
        self,
        prior: EdgeEstimate,
        setup_evidence: Optional[SetupEvidenceSummary],
    ) -> EdgeEstimate:
        if setup_evidence is None:
            return self._without_evidence(prior)

        prior_weight, evidence_weight = self._weights(setup_evidence)
        evidence_avg_loss_r = abs(setup_evidence.posterior_avg_loss_r)
        p_win = _blend(prior.p_win, setup_evidence.posterior_win_rate, evidence_weight)
        avg_win_r = _blend(prior.avg_win_r, setup_evidence.posterior_avg_win_r, evidence_weight)
        avg_loss_r = _blend(prior.avg_loss_r, evidence_avg_loss_r, evidence_weight)
        p_win = _clamp(p_win, 0.0, 1.0)
        avg_win_r = max(0.0, avg_win_r)
        avg_loss_r = max(0.0, avg_loss_r)
        expected_r = (p_win * avg_win_r) - ((1.0 - p_win) * avg_loss_r)
        confidence = _blend(prior.confidence, setup_evidence.confidence, evidence_weight)
        reasons = self._reasons(
            prior=prior,
            setup_evidence=setup_evidence,
            prior_weight=prior_weight,
            evidence_weight=evidence_weight,
        )

        return EdgeEstimate(
            p_win=p_win,
            avg_win_r=avg_win_r,
            avg_loss_r=avg_loss_r,
            expected_r=expected_r,
            confidence=_clamp(confidence, 0.0, 1.0),
            source="adaptive_evidence_blend",
            reasons=reasons,
            setup_id=setup_evidence.setup_id,
            sample_size=setup_evidence.sample_size,
            prior_weight=prior_weight,
            evidence_weight=evidence_weight,
            setup_state=setup_evidence.state,
        )

    def _without_evidence(self, prior: EdgeEstimate) -> EdgeEstimate:
        reasons = list(prior.reasons)
        reasons.append("setup evidence unavailable; using rule-based prior")
        return EdgeEstimate(
            p_win=prior.p_win,
            avg_win_r=prior.avg_win_r,
            avg_loss_r=prior.avg_loss_r,
            expected_r=prior.expected_r,
            confidence=prior.confidence,
            source="adaptive_prior_only",
            reasons=reasons,
            setup_id=prior.setup_id,
            sample_size=prior.sample_size,
            prior_weight=1.0,
            evidence_weight=0.0,
            setup_state=prior.setup_state,
        )

    def _weights(self, setup_evidence: SetupEvidenceSummary) -> tuple[float, float]:
        config = self.config
        sample_size = max(0, setup_evidence.sample_size)
        sample_weight = sample_size / max(1, sample_size + config.prior_trade_equivalent)
        maturity_weight = sample_size / max(1, config.mature_sample_size)
        evidence_weight = min(
            config.max_evidence_weight,
            sample_weight * maturity_weight * setup_evidence.confidence,
        )

        if setup_evidence.state == SETUP_STATE_INSUFFICIENT_EVIDENCE:
            evidence_weight = min(evidence_weight, config.insufficient_evidence_max_weight)
        elif setup_evidence.state == SETUP_STATE_WEAK:
            evidence_weight = max(evidence_weight, config.weak_evidence_min_weight)
        elif setup_evidence.state == SETUP_STATE_RETIRED:
            evidence_weight = max(evidence_weight, config.retired_evidence_min_weight)

        evidence_weight = _clamp(evidence_weight, 0.0, config.max_evidence_weight)
        prior_weight = 1.0 - evidence_weight
        return prior_weight, evidence_weight

    def _reasons(
        self,
        *,
        prior: EdgeEstimate,
        setup_evidence: SetupEvidenceSummary,
        prior_weight: float,
        evidence_weight: float,
    ) -> List[str]:
        reasons = list(prior.reasons)
        reasons.append(
            "adaptive blend "
            f"setup_id={setup_evidence.setup_id} "
            f"state={setup_evidence.state} "
            f"sample_size={setup_evidence.sample_size} "
            f"prior_weight={prior_weight:.4f} "
            f"evidence_weight={evidence_weight:.4f}"
        )
        reasons.append(
            "setup evidence "
            f"p_win={setup_evidence.posterior_win_rate:.4f} "
            f"avg_win_r={setup_evidence.posterior_avg_win_r:.4f} "
            f"avg_loss_r={abs(setup_evidence.posterior_avg_loss_r):.4f} "
            f"expected_r={setup_evidence.posterior_expected_r:.4f} "
            f"confidence={setup_evidence.confidence:.4f}"
        )
        return reasons + list(setup_evidence.reasons)


def _blend(prior_value: float, evidence_value: float, evidence_weight: float) -> float:
    prior_weight = 1.0 - evidence_weight
    return prior_value * prior_weight + evidence_value * evidence_weight


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))
