"""Expected-edge estimation for autonomous candidates.

This module starts with a transparent rule-based estimator.  It is intentionally
not ML yet; the interface is designed so later evidence-backed or model-backed
estimators can replace it without changing ranker/engine plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class EdgeEstimate:
    """Estimated edge for one candidate."""

    p_win: float
    avg_win_r: float
    avg_loss_r: float
    expected_r: float
    confidence: float
    source: str
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "p_win": round(self.p_win, 6),
            "avg_win_r": round(self.avg_win_r, 6),
            "avg_loss_r": round(self.avg_loss_r, 6),
            "expected_r": round(self.expected_r, 6),
            "confidence": round(self.confidence, 6),
            "source": self.source,
            "reasons": list(self.reasons),
        }


class RuleBasedEdgeEstimator:
    """Transparent first-pass estimator for expected R.

    The estimator produces conservative, bounded probabilities from available
    features.  It should be treated as a bootstrap estimate until enough
    realized trade evidence exists for a learned/calibrated estimator.
    """

    def estimate(self, features: Dict[str, Any]) -> EdgeEstimate:
        p_win = 0.50
        confidence = 0.25
        reasons: List[str] = ["bootstrap rule-based estimate"]

        quality_score = _num(features.get("quality_score"))
        if features.get("quality_label") == "Strong":
            p_win += 0.04
            confidence += 0.05
            reasons.append("quality_label=Strong")
        if quality_score is not None and quality_score >= 85:
            p_win += 0.02
            reasons.append("quality_score>=85")

        if features.get("momentum_label") == "Confirmed Rebound":
            p_win += 0.04
            confidence += 0.05
            reasons.append("momentum=Confirmed Rebound")

        rr = _num(features.get("risk_reward"))
        avg_win_r = 1.0
        if rr is not None and rr > 0:
            avg_win_r = max(0.25, min(3.0, rr))
            confidence += 0.05
            reasons.append(f"risk_reward={avg_win_r:.2f}R")
        else:
            reasons.append("risk_reward unavailable; using 1R default")

        support_distance_pct = _num(features.get("support_distance_pct"))
        if support_distance_pct is not None:
            if 0 <= support_distance_pct <= 0.05:
                p_win += 0.02
                reasons.append("near support")
            elif support_distance_pct > 0.12:
                p_win -= 0.03
                reasons.append("far from support")

        rsi = _num(features.get("rsi_14"))
        if rsi is not None:
            if 30 <= rsi <= 60:
                p_win += 0.01
                reasons.append("RSI in recovery/neutral range")
            elif rsi > 70:
                p_win -= 0.03
                reasons.append("RSI overbought")

        if features.get("spy_bullish") is True:
            p_win += 0.02
            reasons.append("SPY bullish")
        if features.get("vix_level_regime") == "normal":
            p_win += 0.01
            reasons.append("VIX normal")
        elif features.get("vix_level_regime") in {"caution", "block"}:
            p_win -= 0.03
            reasons.append("VIX caution/stress")

        if features.get("vix_direction_regime") == "falling":
            p_win += 0.01
            reasons.append("VIX falling")
        elif features.get("vix_direction_regime") in {"rising_caution", "rising_block"}:
            p_win -= 0.03
            reasons.append("VIX rising")

        adr_pct = _num(features.get("adr_pct"))
        if adr_pct is not None:
            confidence += 0.03
            if adr_pct > 0.06:
                p_win -= 0.02
                reasons.append("high ADR volatility")

        p_win = max(0.35, min(0.70, p_win))
        confidence = max(0.05, min(0.75, confidence))
        avg_loss_r = 1.0
        expected_r = (p_win * avg_win_r) - ((1.0 - p_win) * avg_loss_r)

        return EdgeEstimate(
            p_win=p_win,
            avg_win_r=avg_win_r,
            avg_loss_r=avg_loss_r,
            expected_r=expected_r,
            confidence=confidence,
            source="rule_based_bootstrap",
            reasons=reasons,
        )


def _num(value: Any):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out
