"""Feature extraction for autonomous edge estimation.

The feature builder converts a ``CandidateSignal`` plus market-regime context
into a stable JSON-serialisable feature dict.  It deliberately does not score or
rank anything; downstream edge estimators consume the features.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from autonomous.candidate_scanner import CandidateSignal


def _float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


class FeatureBuilder:
    """Build candidate-level features for expected-edge estimation."""

    def build(
        self,
        candidate: CandidateSignal,
        *,
        market_gate: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last = _float(candidate.last_price)
        support = _float(candidate.support_price)
        resistance = _float(candidate.resistance_price)
        extras = candidate.extras or {}
        market_gate = market_gate or {}
        vix = market_gate.get("vix") or {}

        support_distance_pct = None
        if last is not None and support is not None and last > 0:
            support_distance_pct = (last - support) / last

        resistance_room_pct = None
        if last is not None and resistance is not None and last > 0:
            resistance_room_pct = (resistance - last) / last

        risk_reward = None
        if (
            last is not None
            and support is not None
            and resistance is not None
            and last > support
            and resistance > last
        ):
            stop = support * 0.97
            risk = last - stop
            reward = resistance - last
            if risk > 0:
                risk_reward = reward / risk

        return {
            "symbol": candidate.symbol,
            "sector": candidate.sector,
            "signal_label": candidate.signal_label,
            "strength_score": candidate.strength_score,
            "last_price": last,
            "support_price": support,
            "resistance_price": resistance,
            "support_distance_pct": round(support_distance_pct, 6) if support_distance_pct is not None else None,
            "resistance_room_pct": round(resistance_room_pct, 6) if resistance_room_pct is not None else None,
            "risk_reward": round(risk_reward, 6) if risk_reward is not None else None,
            "quality_label": extras.get("quality_label"),
            "quality_score": _float(extras.get("quality_score")),
            "momentum_label": extras.get("momentum_label"),
            "momentum_confirmation": extras.get("momentum_confirmation"),
            "bollinger_status": extras.get("bollinger_status"),
            "rsi_14": _float(extras.get("rsi_14")),
            "rsi_status": extras.get("rsi_status"),
            "adr_pct": _float(extras.get("adr_pct")),
            "levels_valid": (
                bool(support or resistance)
                if extras.get("levels_valid") is None
                else bool(extras.get("levels_valid"))
            ),
            "market_classification": market_gate.get("classification"),
            "spy_bullish": market_gate.get("bullish"),
            "vix_available": vix.get("available"),
            "vix_level_regime": vix.get("level_regime"),
            "vix_direction_regime": vix.get("direction_regime"),
            "market_size_multiplier": _float(market_gate.get("size_multiplier")),
        }
