"""Setup-level evidence calibration for autonomous learning.

This module is analytics-only.  It summarizes realized outcome evidence by
deterministic setup ID and does not alter execution, sizing, eligibility gates,
risk controls, capital promotion, or broker connectivity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from autonomous.evidence_utils import _realized_r
from autonomous.performance_metrics import PerformanceMetrics, calculate_performance_metrics
from autonomous.setup_registry import SetupMetadata, SetupRegistry


SETUP_STATE_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
SETUP_STATE_WEAK = "WEAK"
SETUP_STATE_ACCEPTABLE = "ACCEPTABLE"
SETUP_STATE_STRONG = "STRONG"
SETUP_STATE_RETIRED = "RETIRED"
SETUP_STATE_PAPER_ONLY = "PAPER_ONLY"
SETUP_STATE_LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


@dataclass(frozen=True)
class EvidenceCalibrationThresholds:
    """Conservative thresholds for setup-level evidence calibration."""

    min_trades: int = 20
    strong_min_trades: int = 50
    live_eligible_min_trades: int = 100
    retire_min_trades: int = 30
    prior_trades: int = 20
    prior_win_rate: float = 0.50
    prior_avg_win_r: float = 1.00
    prior_avg_loss_r: float = -1.00
    weak_expected_r: float = 0.00
    acceptable_expected_r: float = 0.05
    strong_expected_r: float = 0.20
    live_eligible_expected_r: float = 0.25
    acceptable_profit_factor: float = 1.05
    strong_profit_factor: float = 1.50
    live_eligible_profit_factor: float = 1.75
    retire_expected_r: float = -0.10
    retire_profit_factor: float = 0.75
    max_live_drawdown_r: float = 8.00
    retire_drawdown_r: float = 12.00


@dataclass
class SetupEvidenceSummary:
    """Evidence summary and calibrated setup state for one setup family."""

    setup_id: str
    state: str
    sample_size: int
    confidence: float
    evidence_weight: float
    prior_weight: float
    posterior_win_rate: float
    posterior_avg_win_r: float
    posterior_avg_loss_r: float
    posterior_expected_r: float
    metrics: PerformanceMetrics
    setup_metadata: SetupMetadata
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "setup_id": self.setup_id,
            "state": self.state,
            "sample_size": self.sample_size,
            "confidence": round(self.confidence, 6),
            "evidence_weight": round(self.evidence_weight, 6),
            "prior_weight": round(self.prior_weight, 6),
            "posterior_win_rate": round(self.posterior_win_rate, 6),
            "posterior_avg_win_r": round(self.posterior_avg_win_r, 6),
            "posterior_avg_loss_r": round(self.posterior_avg_loss_r, 6),
            "posterior_expected_r": round(self.posterior_expected_r, 6),
            "metrics": self.metrics.to_dict(),
            "setup_metadata": self.setup_metadata.to_dict(),
            "reasons": list(self.reasons),
        }


class EvidenceCalibrator:
    """Calibrate realized evidence into setup-level performance summaries."""

    def __init__(
        self,
        *,
        thresholds: Optional[EvidenceCalibrationThresholds] = None,
        setup_registry: Optional[SetupRegistry] = None,
    ) -> None:
        self.thresholds = thresholds or EvidenceCalibrationThresholds()
        self.setup_registry = setup_registry or SetupRegistry()

    def summarize(self, records: Iterable[Dict[str, Any]]) -> Dict[str, SetupEvidenceSummary]:
        grouped = self._group_realized_records(records)
        summaries: Dict[str, SetupEvidenceSummary] = {}
        for setup_id in sorted(grouped):
            rows = grouped[setup_id]["records"]
            metadata = grouped[setup_id]["metadata"]
            summaries[setup_id] = self._summarize_setup(
                setup_id=setup_id,
                records=rows,
                metadata=metadata,
            )
        return summaries

    def summarize_list(self, records: Iterable[Dict[str, Any]]) -> List[SetupEvidenceSummary]:
        return list(self.summarize(records).values())

    def _group_realized_records(
        self,
        records: Iterable[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for record in records:
            if _realized_r(record) is None:
                continue
            metadata = self.setup_registry.metadata_for_record(record)
            bucket = grouped.setdefault(
                metadata.setup_id,
                {
                    "metadata": metadata,
                    "records": [],
                },
            )
            if bucket["metadata"] is not metadata:
                symbol = metadata.symbols[0] if metadata.symbols else None
                bucket["metadata"].add_observation(symbol=symbol)
            bucket["records"].append(record)
        return grouped

    def _summarize_setup(
        self,
        *,
        setup_id: str,
        records: List[Dict[str, Any]],
        metadata: SetupMetadata,
    ) -> SetupEvidenceSummary:
        metrics = calculate_performance_metrics(records)
        posterior = self._posterior(metrics)
        state, reasons = self._classify(metrics=metrics, posterior=posterior)
        confidence = self._confidence(metrics=metrics, posterior_expected_r=posterior["expected_r"])

        return SetupEvidenceSummary(
            setup_id=setup_id,
            state=state,
            sample_size=metrics.trade_count,
            confidence=confidence,
            evidence_weight=posterior["evidence_weight"],
            prior_weight=posterior["prior_weight"],
            posterior_win_rate=posterior["win_rate"],
            posterior_avg_win_r=posterior["avg_win_r"],
            posterior_avg_loss_r=posterior["avg_loss_r"],
            posterior_expected_r=posterior["expected_r"],
            metrics=metrics,
            setup_metadata=metadata,
            reasons=reasons,
        )

    def _posterior(self, metrics: PerformanceMetrics) -> Dict[str, float]:
        thresholds = self.thresholds
        sample_size = metrics.trade_count
        prior_trades = max(0, thresholds.prior_trades)
        denominator = sample_size + prior_trades
        evidence_weight = sample_size / denominator if denominator else 0.0
        prior_weight = 1.0 - evidence_weight

        prior_wins = thresholds.prior_win_rate * prior_trades
        posterior_win_rate = (
            (metrics.win_count + prior_wins) / denominator
            if denominator
            else thresholds.prior_win_rate
        )
        observed_avg_win = metrics.avg_win_r if metrics.win_count else thresholds.prior_avg_win_r
        observed_avg_loss = (
            metrics.avg_loss_r if metrics.loss_count else thresholds.prior_avg_loss_r
        )
        posterior_avg_win_r = (
            observed_avg_win * evidence_weight
            + thresholds.prior_avg_win_r * prior_weight
        )
        posterior_avg_loss_r = (
            observed_avg_loss * evidence_weight
            + thresholds.prior_avg_loss_r * prior_weight
        )
        posterior_expected_r = (
            posterior_win_rate * posterior_avg_win_r
            + (1.0 - posterior_win_rate) * posterior_avg_loss_r
        )

        return {
            "evidence_weight": _clamp(evidence_weight),
            "prior_weight": _clamp(prior_weight),
            "win_rate": _clamp(posterior_win_rate),
            "avg_win_r": posterior_avg_win_r,
            "avg_loss_r": posterior_avg_loss_r,
            "expected_r": posterior_expected_r,
        }

    def _classify(
        self,
        *,
        metrics: PerformanceMetrics,
        posterior: Dict[str, float],
    ) -> tuple[str, List[str]]:
        thresholds = self.thresholds
        reasons: List[str] = []
        expected_r = posterior["expected_r"]
        profit_factor = metrics.profit_factor
        finite_profit_factor = _finite_profit_factor(profit_factor)

        if metrics.trade_count < thresholds.min_trades:
            reasons.append(
                f"sample_size {metrics.trade_count} below minimum {thresholds.min_trades}"
            )
            return SETUP_STATE_INSUFFICIENT_EVIDENCE, reasons

        if metrics.trade_count >= thresholds.retire_min_trades and (
            expected_r <= thresholds.retire_expected_r
            or finite_profit_factor <= thresholds.retire_profit_factor
            or metrics.max_drawdown_r >= thresholds.retire_drawdown_r
        ):
            reasons.append("sufficient evidence indicates setup should be retired")
            return SETUP_STATE_RETIRED, reasons

        if expected_r <= thresholds.weak_expected_r:
            reasons.append("posterior expected R is not positive")
            return SETUP_STATE_WEAK, reasons

        if finite_profit_factor < thresholds.acceptable_profit_factor:
            reasons.append("profit factor below acceptable threshold")
            return SETUP_STATE_WEAK, reasons

        if metrics.max_drawdown_r > thresholds.max_live_drawdown_r:
            reasons.append("drawdown too high for live eligibility")
            return SETUP_STATE_PAPER_ONLY, reasons

        if (
            metrics.trade_count >= thresholds.live_eligible_min_trades
            and expected_r >= thresholds.live_eligible_expected_r
            and finite_profit_factor >= thresholds.live_eligible_profit_factor
        ):
            reasons.append("large positive evidence sample supports live eligibility")
            return SETUP_STATE_LIVE_ELIGIBLE, reasons

        if (
            metrics.trade_count >= thresholds.strong_min_trades
            and expected_r >= thresholds.strong_expected_r
            and finite_profit_factor >= thresholds.strong_profit_factor
        ):
            reasons.append("positive evidence sample supports strong setup state")
            return SETUP_STATE_STRONG, reasons

        if expected_r >= thresholds.acceptable_expected_r:
            reasons.append("positive evidence sample supports acceptable setup state")
            return SETUP_STATE_ACCEPTABLE, reasons

        reasons.append("positive but not yet acceptable calibrated edge")
        return SETUP_STATE_PAPER_ONLY, reasons

    def _confidence(self, *, metrics: PerformanceMetrics, posterior_expected_r: float) -> float:
        thresholds = self.thresholds
        sample_score = _clamp(metrics.trade_count / max(1, thresholds.live_eligible_min_trades))
        edge_score = _clamp(
            (posterior_expected_r - thresholds.weak_expected_r)
            / max(0.000001, thresholds.strong_expected_r - thresholds.weak_expected_r)
        )
        profit_factor = _finite_profit_factor(metrics.profit_factor)
        profit_score = _clamp(
            (profit_factor - thresholds.retire_profit_factor)
            / max(0.000001, thresholds.strong_profit_factor - thresholds.retire_profit_factor)
        )
        drawdown_score = 1.0 - _clamp(
            metrics.max_drawdown_r / max(0.000001, thresholds.retire_drawdown_r)
        )
        return _clamp(
            0.50 * sample_score
            + 0.25 * edge_score
            + 0.15 * profit_score
            + 0.10 * drawdown_score
        )


def calibrate_setup_evidence(
    records: Iterable[Dict[str, Any]],
    *,
    thresholds: Optional[EvidenceCalibrationThresholds] = None,
    setup_registry: Optional[SetupRegistry] = None,
) -> Dict[str, SetupEvidenceSummary]:
    """Convenience wrapper for EL3 setup evidence calibration."""

    return EvidenceCalibrator(
        thresholds=thresholds,
        setup_registry=setup_registry,
    ).summarize(records)


def _finite_profit_factor(value: float) -> float:
    if math.isinf(value):
        return 999999.0
    if math.isnan(value):
        return 0.0
    return value


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))
