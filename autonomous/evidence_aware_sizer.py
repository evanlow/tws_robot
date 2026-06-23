"""Evidence-aware sizing overlay for autonomous trade plans.

The overlay is conservative by construction. It can halt or reduce a BUY_SHARES
cap from setup evidence, but it never bypasses the caller's cash, risk,
volatility, drawdown, basket, or operator caps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from autonomous.evidence_calibrator import (
    SETUP_STATE_ACCEPTABLE,
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_LIVE_ELIGIBLE,
    SETUP_STATE_PAPER_ONLY,
    SETUP_STATE_RETIRED,
    SETUP_STATE_STRONG,
    SETUP_STATE_WEAK,
)
from autonomous.setup_eligibility import SETUP_ELIGIBILITY_REJECT


EVIDENCE_SIZE_NO_TRADE = "NO_TRADE"
EVIDENCE_SIZE_PAPER_ONLY = "PAPER_ONLY"
EVIDENCE_SIZE_TINY_LIVE = "TINY_LIVE"
EVIDENCE_SIZE_NORMAL_CAPPED = "NORMAL_CAPPED"
EVIDENCE_SIZE_REDUCED_SIZE = "REDUCED_SIZE"
EVIDENCE_SIZE_RETIRED = "RETIRED"


@dataclass(frozen=True)
class EvidenceAwareSizingConfig:
    """Thresholds for the evidence-aware sizing overlay."""

    enabled: bool = False
    min_trades_for_tiny_live: int = 20
    min_trades_for_normal: int = 100
    tiny_live_max_position_pct: float = 0.001
    reduced_size_multiplier: float = 0.50
    min_confidence_for_normal: float = 0.60
    strong_expected_r: float = 0.25
    max_drawdown_r_for_normal: float = 8.00
    max_slippage_bps_for_normal: float = 50.0
    allow_size_increase: bool = False


@dataclass
class EvidenceAwareSizingDecision:
    """Evidence overlay result and diagnostics."""

    enabled: bool
    applied: bool
    state: str = EVIDENCE_SIZE_NORMAL_CAPPED
    multiplier: float = 1.0
    cap_value: Optional[float] = None
    evidence_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "applied": self.applied,
            "state": self.state,
            "multiplier": round(self.multiplier, 6),
            "cap_value": round(self.cap_value, 2) if self.cap_value is not None else None,
            "evidence_score": round(self.evidence_score, 6),
            "reasons": list(self.reasons),
            "diagnostics": dict(self.diagnostics),
        }


class EvidenceAwareSizer:
    """Evaluate setup evidence into an optional sizing cap."""

    def __init__(self, config: Optional[EvidenceAwareSizingConfig] = None) -> None:
        self.config = config or EvidenceAwareSizingConfig()

    def evaluate(
        self,
        *,
        equity: float,
        current_cap_value: float,
        edge_estimate: Optional[Dict[str, Any]] = None,
        observed_trades: int = 0,
        setup_eligibility: Optional[Dict[str, Any]] = None,
        strategy_drawdown_pct: Optional[float] = None,
        avg_slippage_bps: Optional[float] = None,
    ) -> EvidenceAwareSizingDecision:
        if not self.config.enabled:
            return EvidenceAwareSizingDecision(
                enabled=False,
                applied=False,
                reasons=["evidence-aware sizing disabled"],
            )

        evidence = _snapshot(
            edge_estimate=edge_estimate,
            observed_trades=observed_trades,
            setup_eligibility=setup_eligibility,
            strategy_drawdown_pct=strategy_drawdown_pct,
            avg_slippage_bps=avg_slippage_bps,
        )
        score = _evidence_score(evidence, self.config)

        action = evidence.get("eligibility_action")
        setup_state = evidence.get("setup_state")
        sample_size = evidence.get("sample_size") or 0
        expected_r = evidence.get("expected_r")
        confidence = evidence.get("confidence") or 0.0
        max_drawdown_r = evidence.get("max_drawdown_r")
        slippage_bps = evidence.get("avg_slippage_bps")

        if action == SETUP_ELIGIBILITY_REJECT or setup_state in {SETUP_STATE_RETIRED, SETUP_STATE_WEAK}:
            state = EVIDENCE_SIZE_RETIRED if setup_state == SETUP_STATE_RETIRED else EVIDENCE_SIZE_NO_TRADE
            return EvidenceAwareSizingDecision(
                enabled=True,
                applied=True,
                state=state,
                multiplier=0.0,
                cap_value=0.0,
                evidence_score=score,
                reasons=[f"setup evidence blocks sizing: action={action!r}, state={setup_state!r}"],
                diagnostics=evidence,
            )

        if expected_r is not None and sample_size >= self.config.min_trades_for_tiny_live and expected_r <= 0:
            return EvidenceAwareSizingDecision(
                enabled=True,
                applied=True,
                state=EVIDENCE_SIZE_NO_TRADE,
                multiplier=0.0,
                cap_value=0.0,
                evidence_score=score,
                reasons=[f"expected_r {expected_r:.4f} is non-positive with {sample_size} trades"],
                diagnostics=evidence,
            )

        if (
            setup_state in {SETUP_STATE_INSUFFICIENT_EVIDENCE, SETUP_STATE_PAPER_ONLY}
            or sample_size < self.config.min_trades_for_normal
        ):
            if sample_size < self.config.min_trades_for_tiny_live:
                return EvidenceAwareSizingDecision(
                    enabled=True,
                    applied=True,
                    state=EVIDENCE_SIZE_PAPER_ONLY,
                    multiplier=0.0,
                    cap_value=0.0,
                    evidence_score=score,
                    reasons=[
                        "insufficient evidence for tiny sizing; "
                        f"need {self.config.min_trades_for_tiny_live} trades"
                    ],
                    diagnostics=evidence,
                )
            cap_value = min(current_cap_value, max(0.0, equity * self.config.tiny_live_max_position_pct))
            return EvidenceAwareSizingDecision(
                enabled=True,
                applied=True,
                state=EVIDENCE_SIZE_TINY_LIVE,
                multiplier=_ratio(cap_value, current_cap_value),
                cap_value=cap_value,
                evidence_score=score,
                reasons=[f"limited to tiny evidence cap until {self.config.min_trades_for_normal} trades"],
                diagnostics=evidence,
            )

        reduction_reasons: list[str] = []
        if confidence < self.config.min_confidence_for_normal:
            reduction_reasons.append(
                f"confidence {confidence:.4f} < {self.config.min_confidence_for_normal:.4f}"
            )
        if max_drawdown_r is not None and max_drawdown_r > self.config.max_drawdown_r_for_normal:
            reduction_reasons.append(
                f"max_drawdown_r {max_drawdown_r:.4f} > {self.config.max_drawdown_r_for_normal:.4f}"
            )
        if slippage_bps is not None and slippage_bps > self.config.max_slippage_bps_for_normal:
            reduction_reasons.append(
                f"avg_slippage_bps {slippage_bps:.4f} > {self.config.max_slippage_bps_for_normal:.4f}"
            )
        if strategy_drawdown_pct is not None and strategy_drawdown_pct > 0:
            reduction_reasons.append(f"strategy_drawdown_pct {strategy_drawdown_pct:.4f} > 0")

        if reduction_reasons:
            cap_value = current_cap_value * self.config.reduced_size_multiplier
            return EvidenceAwareSizingDecision(
                enabled=True,
                applied=True,
                state=EVIDENCE_SIZE_REDUCED_SIZE,
                multiplier=self.config.reduced_size_multiplier,
                cap_value=cap_value,
                evidence_score=score,
                reasons=reduction_reasons,
                diagnostics=evidence,
            )

        if (
            expected_r is not None
            and expected_r >= self.config.strong_expected_r
            and setup_state in {SETUP_STATE_ACCEPTABLE, SETUP_STATE_STRONG, SETUP_STATE_LIVE_ELIGIBLE, None}
        ):
            return EvidenceAwareSizingDecision(
                enabled=True,
                applied=False,
                state=EVIDENCE_SIZE_NORMAL_CAPPED,
                multiplier=1.0,
                cap_value=current_cap_value if self.config.allow_size_increase else None,
                evidence_score=score,
                reasons=["evidence supports normal capped sizing; existing hard caps remain binding"],
                diagnostics=evidence,
            )

        cap_value = current_cap_value * self.config.reduced_size_multiplier
        return EvidenceAwareSizingDecision(
            enabled=True,
            applied=True,
            state=EVIDENCE_SIZE_REDUCED_SIZE,
            multiplier=self.config.reduced_size_multiplier,
            cap_value=cap_value,
            evidence_score=score,
            reasons=["evidence is mature but not strong enough for normal capped sizing"],
            diagnostics=evidence,
        )


def _snapshot(
    *,
    edge_estimate: Optional[Dict[str, Any]],
    observed_trades: int,
    setup_eligibility: Optional[Dict[str, Any]],
    strategy_drawdown_pct: Optional[float],
    avg_slippage_bps: Optional[float],
) -> Dict[str, Any]:
    diagnostics = setup_eligibility.get("diagnostics") if setup_eligibility else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    sample_size = _first_num(
        diagnostics.get("sample_size"),
        setup_eligibility.get("sample_size") if setup_eligibility else None,
        edge_estimate.get("sample_size") if edge_estimate else None,
        observed_trades,
    )
    expected_r = _first_num(
        diagnostics.get("expected_r"),
        setup_eligibility.get("expected_r") if setup_eligibility else None,
        edge_estimate.get("expected_r") if edge_estimate else None,
    )
    confidence = _first_num(
        diagnostics.get("confidence"),
        setup_eligibility.get("confidence") if setup_eligibility else None,
        edge_estimate.get("confidence") if edge_estimate else None,
    )
    setup_state = _first_non_empty(
        setup_eligibility.get("setup_state") if setup_eligibility else None,
        diagnostics.get("setup_state"),
        edge_estimate.get("setup_state") if edge_estimate else None,
    )
    return {
        "setup_id": _first_non_empty(
            setup_eligibility.get("setup_id") if setup_eligibility else None,
            diagnostics.get("setup_id"),
            edge_estimate.get("setup_id") if edge_estimate else None,
        ),
        "setup_state": setup_state,
        "eligibility_action": setup_eligibility.get("action") if setup_eligibility else None,
        "sample_size": int(sample_size or 0),
        "expected_r": expected_r,
        "confidence": confidence,
        "rolling_sharpe": _first_num(
            diagnostics.get("rolling_sharpe"),
            edge_estimate.get("rolling_sharpe") if edge_estimate else None,
        ),
        "max_drawdown_r": _first_num(
            diagnostics.get("max_drawdown_r"),
            edge_estimate.get("max_drawdown_r") if edge_estimate else None,
        ),
        "avg_slippage_bps": _first_num(
            avg_slippage_bps,
            diagnostics.get("avg_slippage_bps"),
            edge_estimate.get("avg_slippage_bps") if edge_estimate else None,
        ),
        "strategy_drawdown_pct": strategy_drawdown_pct,
    }


def _evidence_score(evidence: Dict[str, Any], config: EvidenceAwareSizingConfig) -> float:
    sample_score = min(1.0, (evidence.get("sample_size") or 0) / max(1, config.min_trades_for_normal))
    confidence_score = max(0.0, min(1.0, evidence.get("confidence") or 0.0))
    expected_r = evidence.get("expected_r")
    edge_score = 0.0 if expected_r is None else max(0.0, min(1.0, expected_r / max(0.000001, config.strong_expected_r)))
    rolling_sharpe = evidence.get("rolling_sharpe")
    sharpe_score = 0.5 if rolling_sharpe is None else max(0.0, min(1.0, (rolling_sharpe + 1.0) / 3.0))
    drawdown_r = evidence.get("max_drawdown_r")
    drawdown_score = (
        0.5
        if drawdown_r is None
        else max(0.0, 1.0 - (drawdown_r / max(0.000001, config.max_drawdown_r_for_normal)))
    )
    return (
        sample_score * 0.25
        + confidence_score * 0.20
        + edge_score * 0.25
        + sharpe_score * 0.15
        + drawdown_score * 0.15
    )


def _ratio(cap_value: float, current_cap_value: float) -> float:
    if current_cap_value <= 0:
        return 0.0
    return max(0.0, min(1.0, cap_value / current_cap_value))


def _first_num(*values: Any) -> Optional[float]:
    for value in values:
        try:
            out = float(value)
        except (TypeError, ValueError):
            continue
        return out
    return None


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value:
            return str(value)
    return None
