"""Setup eligibility gate for evidence-backed autonomous candidates.

The gate is deliberately conservative. It can reject or downgrade a setup from
calibrated evidence, but it never enables live trading, bypasses risk controls,
changes sizing, or places orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from autonomous.autonomous_config import AutonomousMode
from autonomous.edge_estimator import EdgeEstimate
from autonomous.evidence_calibrator import (
    SETUP_STATE_ACCEPTABLE,
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_LIVE_ELIGIBLE,
    SETUP_STATE_PAPER_ONLY,
    SETUP_STATE_RETIRED,
    SETUP_STATE_STRONG,
    SETUP_STATE_WEAK,
    SetupEvidenceSummary,
)


SETUP_ELIGIBILITY_ALLOW = "ALLOW"
SETUP_ELIGIBILITY_REJECT = "REJECT"
SETUP_ELIGIBILITY_PAPER_ONLY = "PAPER_ONLY"


@dataclass(frozen=True)
class SetupEligibilityConfig:
    """Conservative thresholds for setup eligibility decisions."""

    sufficient_sample_size: int = 20
    min_expected_r: float = 0.0
    block_insufficient_evidence_in_live: bool = True


@dataclass
class SetupEligibilityDecision:
    """Eligibility decision and diagnostics for one setup."""

    eligible: bool
    action: str
    reason: str
    setup_id: Optional[str] = None
    setup_state: Optional[str] = None
    sample_size: int = 0
    expected_r: Optional[float] = None
    confidence: Optional[float] = None
    allowed_modes: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "action": self.action,
            "reason": self.reason,
            "setup_id": self.setup_id,
            "setup_state": self.setup_state,
            "sample_size": self.sample_size,
            "expected_r": _round_optional(self.expected_r),
            "confidence": _round_optional(self.confidence),
            "allowed_modes": list(self.allowed_modes),
            "diagnostics": dict(self.diagnostics),
        }


class SetupEligibilityGate:
    """Evaluate setup evidence before planning or execution."""

    def __init__(self, config: Optional[SetupEligibilityConfig] = None) -> None:
        self.config = config or SetupEligibilityConfig()

    def evaluate(
        self,
        *,
        mode: AutonomousMode | str,
        edge_estimate: Optional[EdgeEstimate] = None,
        setup_evidence: Optional[SetupEvidenceSummary] = None,
    ) -> SetupEligibilityDecision:
        mode = AutonomousMode(mode)
        snapshot = _snapshot(edge_estimate=edge_estimate, setup_evidence=setup_evidence)
        if snapshot["setup_state"] is None and snapshot["expected_r"] is None:
            return SetupEligibilityDecision(
                eligible=True,
                action=SETUP_ELIGIBILITY_ALLOW,
                reason="setup evidence unavailable; no eligibility restriction applied",
                allowed_modes=_all_modes(),
                diagnostics=snapshot,
            )

        if snapshot["setup_state"] == SETUP_STATE_RETIRED:
            return self._reject(snapshot, "setup state is RETIRED")

        if (
            snapshot["sample_size"] >= self.config.sufficient_sample_size
            and snapshot["expected_r"] is not None
            and snapshot["expected_r"] <= self.config.min_expected_r
        ):
            return self._reject(
                snapshot,
                f"expected_r {snapshot['expected_r']:.4f} <= min {self.config.min_expected_r:.4f}",
            )

        if snapshot["setup_state"] == SETUP_STATE_WEAK:
            return self._reject(snapshot, "setup state is WEAK")

        if snapshot["setup_state"] == SETUP_STATE_PAPER_ONLY:
            return self._paper_only(
                mode=mode,
                snapshot=snapshot,
                reason="setup state is PAPER_ONLY",
            )

        if snapshot["setup_state"] == SETUP_STATE_INSUFFICIENT_EVIDENCE:
            if mode == AutonomousMode.ASSISTED_LIVE and self.config.block_insufficient_evidence_in_live:
                return self._reject(
                    snapshot,
                    "insufficient setup evidence for assisted_live; EL6 tiny-live sizing is not active",
                    allowed_modes=[AutonomousMode.RECOMMEND_ONLY.value, AutonomousMode.PAPER_EXECUTE.value],
                )
            return self._paper_only(
                mode=mode,
                snapshot=snapshot,
                reason="insufficient setup evidence; recommend/paper only until more evidence exists",
            )

        if snapshot["setup_state"] in {
            SETUP_STATE_ACCEPTABLE,
            SETUP_STATE_STRONG,
            SETUP_STATE_LIVE_ELIGIBLE,
            None,
        }:
            return SetupEligibilityDecision(
                eligible=True,
                action=SETUP_ELIGIBILITY_ALLOW,
                reason="setup evidence passes eligibility gate",
                setup_id=snapshot["setup_id"],
                setup_state=snapshot["setup_state"],
                sample_size=snapshot["sample_size"],
                expected_r=snapshot["expected_r"],
                confidence=snapshot["confidence"],
                allowed_modes=_all_modes(),
                diagnostics=snapshot,
            )

        return self._paper_only(
            mode=mode,
            snapshot=snapshot,
            reason=f"unrecognized setup state {snapshot['setup_state']!r}; restricting to recommend/paper",
        )

    def _reject(
        self,
        snapshot: Dict[str, Any],
        reason: str,
        *,
        allowed_modes: Optional[List[str]] = None,
    ) -> SetupEligibilityDecision:
        return SetupEligibilityDecision(
            eligible=False,
            action=SETUP_ELIGIBILITY_REJECT,
            reason=reason,
            setup_id=snapshot["setup_id"],
            setup_state=snapshot["setup_state"],
            sample_size=snapshot["sample_size"],
            expected_r=snapshot["expected_r"],
            confidence=snapshot["confidence"],
            allowed_modes=allowed_modes or [],
            diagnostics=snapshot,
        )

    def _paper_only(
        self,
        *,
        mode: AutonomousMode,
        snapshot: Dict[str, Any],
        reason: str,
    ) -> SetupEligibilityDecision:
        allowed_modes = [AutonomousMode.RECOMMEND_ONLY.value, AutonomousMode.PAPER_EXECUTE.value]
        if mode == AutonomousMode.ASSISTED_LIVE:
            return self._reject(snapshot, reason, allowed_modes=allowed_modes)
        return SetupEligibilityDecision(
            eligible=True,
            action=SETUP_ELIGIBILITY_PAPER_ONLY,
            reason=reason,
            setup_id=snapshot["setup_id"],
            setup_state=snapshot["setup_state"],
            sample_size=snapshot["sample_size"],
            expected_r=snapshot["expected_r"],
            confidence=snapshot["confidence"],
            allowed_modes=allowed_modes,
            diagnostics=snapshot,
        )


def _snapshot(
    *,
    edge_estimate: Optional[EdgeEstimate],
    setup_evidence: Optional[SetupEvidenceSummary],
) -> Dict[str, Any]:
    if setup_evidence is not None:
        metrics = setup_evidence.metrics.to_dict()
        return {
            "source": "setup_evidence",
            "setup_id": setup_evidence.setup_id,
            "setup_state": setup_evidence.state,
            "sample_size": setup_evidence.sample_size,
            "expected_r": setup_evidence.posterior_expected_r,
            "confidence": setup_evidence.confidence,
            "profit_factor": metrics.get("profit_factor"),
            "max_drawdown_r": metrics.get("max_drawdown_r"),
            "reasons": list(setup_evidence.reasons),
        }

    if edge_estimate is not None:
        return {
            "source": "edge_estimate",
            "setup_id": edge_estimate.setup_id,
            "setup_state": edge_estimate.setup_state,
            "sample_size": edge_estimate.sample_size,
            "expected_r": edge_estimate.expected_r,
            "confidence": edge_estimate.confidence,
            "profit_factor": None,
            "max_drawdown_r": None,
            "reasons": list(edge_estimate.reasons),
        }

    return {
        "source": "none",
        "setup_id": None,
        "setup_state": None,
        "sample_size": 0,
        "expected_r": None,
        "confidence": None,
        "profit_factor": None,
        "max_drawdown_r": None,
        "reasons": [],
    }


def _all_modes() -> List[str]:
    return [mode.value for mode in AutonomousMode]


def _round_optional(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 6)
