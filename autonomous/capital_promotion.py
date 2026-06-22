"""Advisory capital promotion and demotion reports.

The evaluator consumes realized autonomous outcome evidence and optional
operational incident records.  It never changes trading mode, capital caps, or
broker state; operators must approve any promotion outside this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from autonomous.evidence_utils import _realized_r


PROMOTION_APPROVE = "approve"
PROMOTION_HOLD = "hold"
PROMOTION_DEMOTE = "demote"


@dataclass(frozen=True)
class CapitalLevel:
    """One human-approved capital stage."""

    level: int
    name: str
    mode: str
    requirement: str
    typical_cap: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "mode": self.mode,
            "requirement": self.requirement,
            "typical_cap": self.typical_cap,
        }


DEFAULT_CAPITAL_LEVELS: Tuple[CapitalLevel, ...] = (
    CapitalLevel(0, "Recommend only", "recommend_only", "System healthy", "0"),
    CapitalLevel(1, "Paper single", "paper_single", "Clean paper recommendations", "0"),
    CapitalLevel(2, "Paper basket", "paper_basket", "Clean paper basket evidence", "0"),
    CapitalLevel(3, "Tiny assisted-live", "tiny_assisted_live", "Clean paper evidence and operator-approved tiny live trial", "0.05%-0.10% equity"),
    CapitalLevel(4, "Assisted-live basket", "assisted_live_basket", "Tiny live fills, slippage, and reconciliation clean", "0.10%-0.20% equity"),
    CapitalLevel(5, "Limited continuous", "limited_continuous", "Supervisor and recovery behavior proven", "tightly capped"),
    CapitalLevel(6, "Mature continuous", "mature_continuous", "Long evidence history and operator approval", "operator-approved"),
)


@dataclass
class CapitalPromotionThresholds:
    """Evidence thresholds used to evaluate the next capital level."""

    min_trades_by_level: Dict[int, int] = field(
        default_factory=lambda: {1: 10, 2: 25, 3: 50, 4: 75, 5: 100, 6: 200}
    )
    min_live_trades_by_level: Dict[int, int] = field(
        default_factory=lambda: {4: 10, 5: 25, 6: 50}
    )
    min_avg_r: float = 0.05
    min_expected_r: float = 0.05
    min_win_rate: float = 0.45
    min_profit_factor: float = 1.10
    max_drawdown_r: float = 6.0
    demotion_drawdown_r: float = 6.0
    max_avg_slippage_bps: float = 25.0
    max_partial_fill_rate: float = 0.25
    max_operational_incidents: int = 0
    recent_window_days: int = 30
    stale_after_days: int = 45
    rolling_trade_window: int = 30
    consistency_min_trades: int = 3
    max_paper_live_avg_r_delta: float = 0.35
    min_live_avg_r: float = 0.0


@dataclass
class PaperLiveConsistency:
    """Paper-vs-live consistency diagnostics."""

    evaluated: bool
    consistent: bool
    paper_trades: int = 0
    live_trades: int = 0
    paper_avg_r: float = 0.0
    live_avg_r: float = 0.0
    avg_r_delta: float = 0.0
    reason: str = "insufficient paper/live samples"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "consistent": self.consistent,
            "paper_trades": self.paper_trades,
            "live_trades": self.live_trades,
            "paper_avg_r": round(self.paper_avg_r, 6),
            "live_avg_r": round(self.live_avg_r, 6),
            "avg_r_delta": round(self.avg_r_delta, 6),
            "reason": self.reason,
        }


@dataclass
class CapitalPromotionMetrics:
    """Performance and operational metrics used by the report."""

    completed_trade_count: int
    recent_trade_count: int
    avg_r: float
    expected_r: float
    win_rate: float
    profit_factor: float
    rolling_sharpe: Optional[float]
    sortino: Optional[float]
    max_drawdown_r: float
    avg_slippage_bps: Optional[float]
    max_slippage_bps: Optional[float]
    partial_fill_rate: float
    operational_incidents: int
    latest_evidence_age_days: Optional[float]
    paper_trades: int
    live_trades: int
    paper_live_consistency: PaperLiveConsistency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completed_trade_count": self.completed_trade_count,
            "recent_trade_count": self.recent_trade_count,
            "avg_r": round(self.avg_r, 6),
            "expected_r": round(self.expected_r, 6),
            "win_rate": round(self.win_rate, 6),
            "profit_factor": _round_optional(self.profit_factor),
            "profit_factor_unbounded": math.isinf(self.profit_factor),
            "rolling_sharpe": _round_optional(self.rolling_sharpe),
            "sortino": _round_optional(self.sortino),
            "max_drawdown_r": round(self.max_drawdown_r, 6),
            "avg_slippage_bps": _round_optional(self.avg_slippage_bps),
            "max_slippage_bps": _round_optional(self.max_slippage_bps),
            "partial_fill_rate": round(self.partial_fill_rate, 6),
            "operational_incidents": self.operational_incidents,
            "latest_evidence_age_days": _round_optional(self.latest_evidence_age_days),
            "paper_trades": self.paper_trades,
            "live_trades": self.live_trades,
            "paper_live_consistency": self.paper_live_consistency.to_dict(),
        }


@dataclass
class CapitalPromotionReport:
    """Advisory promotion, hold, or demotion report."""

    current_level: int
    recommended_level: int
    action: str
    target_level: Optional[CapitalLevel]
    metrics: CapitalPromotionMetrics
    approval_reasons: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    demotion_reasons: List[str] = field(default_factory=list)
    operator_approval_required: bool = True
    automatic_capital_scaling_allowed: bool = False

    @property
    def passed(self) -> bool:
        return self.action == PROMOTION_APPROVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_level": self.current_level,
            "recommended_level": self.recommended_level,
            "action": self.action,
            "target_level": self.target_level.to_dict() if self.target_level else None,
            "metrics": self.metrics.to_dict(),
            "approval_reasons": list(self.approval_reasons),
            "rejection_reasons": list(self.rejection_reasons),
            "demotion_reasons": list(self.demotion_reasons),
            "operator_approval_required": self.operator_approval_required,
            "automatic_capital_scaling_allowed": self.automatic_capital_scaling_allowed,
        }


class CapitalPromotionEvaluator:
    """Evaluate evidence for capital promotion without applying changes."""

    def __init__(
        self,
        thresholds: Optional[CapitalPromotionThresholds] = None,
        *,
        levels: Iterable[CapitalLevel] = DEFAULT_CAPITAL_LEVELS,
    ) -> None:
        self.thresholds = thresholds or CapitalPromotionThresholds()
        self.levels = tuple(sorted(levels, key=lambda item: item.level))
        self._level_by_number = {item.level: item for item in self.levels}

    def evaluate(
        self,
        records: Iterable[Dict[str, Any]],
        *,
        current_level: int = 0,
        operational_events: Optional[Iterable[Dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> CapitalPromotionReport:
        """Return an advisory promotion report.

        The report may recommend approval, hold, or demotion, but it does not
        mutate any trading configuration or capital limit.
        """

        ref = _ensure_aware(now or datetime.now(timezone.utc))
        current = self._normalize_level(current_level)
        rows = _outcome_rows(records)
        metrics = self._metrics(rows, operational_events or [], ref)

        demotion_reasons = self._demotion_reasons(metrics, current)
        if demotion_reasons:
            return CapitalPromotionReport(
                current_level=current,
                recommended_level=max(0, current - 1),
                action=PROMOTION_DEMOTE,
                target_level=self._level_by_number.get(max(0, current - 1)),
                metrics=metrics,
                demotion_reasons=demotion_reasons,
            )

        target = self._level_by_number.get(current + 1)
        if target is None:
            return CapitalPromotionReport(
                current_level=current,
                recommended_level=current,
                action=PROMOTION_HOLD,
                target_level=None,
                metrics=metrics,
                rejection_reasons=["already at maximum configured capital level"],
            )

        rejection_reasons = self._promotion_rejection_reasons(metrics, target.level)
        if rejection_reasons:
            return CapitalPromotionReport(
                current_level=current,
                recommended_level=current,
                action=PROMOTION_HOLD,
                target_level=target,
                metrics=metrics,
                rejection_reasons=rejection_reasons,
            )

        return CapitalPromotionReport(
            current_level=current,
            recommended_level=target.level,
            action=PROMOTION_APPROVE,
            target_level=target,
            metrics=metrics,
            approval_reasons=[
                f"capital level {target.level} evidence thresholds satisfied",
                "operator approval is still required before any capital change",
            ],
        )

    def _normalize_level(self, current_level: int) -> int:
        try:
            value = int(current_level)
        except (TypeError, ValueError):
            return 0
        min_level = self.levels[0].level
        max_level = self.levels[-1].level
        return max(min_level, min(max_level, value))

    def _metrics(
        self,
        rows: List[Dict[str, Any]],
        operational_events: Iterable[Dict[str, Any]],
        now: datetime,
    ) -> CapitalPromotionMetrics:
        values = [row["r"] for row in rows]
        completed = len(values)
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        avg_r = sum(values) / completed if completed else 0.0
        profit_factor = _profit_factor(wins, losses)
        win_rate = len(wins) / completed if completed else 0.0
        recent_cutoff = now - timedelta(days=max(1, self.thresholds.recent_window_days))
        recent = [row for row in rows if row["timestamp"] >= recent_cutoff]
        slippage_values = [
            abs(row["slippage_pct"]) * 10_000.0
            for row in rows
            if row.get("slippage_pct") is not None
        ]
        latest_ts = max((row["timestamp"] for row in rows), default=None)
        latest_age = ((now - latest_ts).total_seconds() / 86400.0) if latest_ts else None
        paper_values = [row["r"] for row in rows if row["mode"] == "paper"]
        live_values = [row["r"] for row in rows if row["mode"] == "live"]
        consistency = _paper_live_consistency(
            paper_values,
            live_values,
            min_trades=self.thresholds.consistency_min_trades,
            max_delta=self.thresholds.max_paper_live_avg_r_delta,
            min_live_avg_r=self.thresholds.min_live_avg_r,
        )
        rolling_values = values[-max(1, self.thresholds.rolling_trade_window):]
        incidents = _count_operational_incidents(operational_events)

        return CapitalPromotionMetrics(
            completed_trade_count=completed,
            recent_trade_count=len(recent),
            avg_r=avg_r,
            expected_r=avg_r,
            win_rate=win_rate,
            profit_factor=profit_factor,
            rolling_sharpe=_sharpe(rolling_values),
            sortino=_sortino(rolling_values),
            max_drawdown_r=_max_drawdown(values),
            avg_slippage_bps=(sum(slippage_values) / len(slippage_values)) if slippage_values else None,
            max_slippage_bps=max(slippage_values) if slippage_values else None,
            partial_fill_rate=(
                sum(1 for row in rows if row["partial_fill"]) / completed if completed else 0.0
            ),
            operational_incidents=incidents,
            latest_evidence_age_days=latest_age,
            paper_trades=len(paper_values),
            live_trades=len(live_values),
            paper_live_consistency=consistency,
        )

    def _demotion_reasons(self, metrics: CapitalPromotionMetrics, current_level: int) -> List[str]:
        if current_level <= 0:
            return []
        reasons: List[str] = []
        t = self.thresholds
        if metrics.max_drawdown_r > t.demotion_drawdown_r:
            reasons.append(
                f"max_drawdown_r {metrics.max_drawdown_r:.4f} > demotion limit {t.demotion_drawdown_r:.4f}"
            )
        if metrics.operational_incidents > t.max_operational_incidents:
            reasons.append(
                f"operational_incidents {metrics.operational_incidents} > max {t.max_operational_incidents}"
            )
        if (
            metrics.latest_evidence_age_days is not None
            and metrics.latest_evidence_age_days > t.stale_after_days
        ):
            reasons.append(
                f"latest evidence age {metrics.latest_evidence_age_days:.1f}d > stale limit {t.stale_after_days}d"
            )
        if current_level >= 4 and metrics.paper_live_consistency.evaluated and not metrics.paper_live_consistency.consistent:
            reasons.append(f"paper/live consistency failed: {metrics.paper_live_consistency.reason}")
        return reasons

    def _promotion_rejection_reasons(self, metrics: CapitalPromotionMetrics, target_level: int) -> List[str]:
        reasons: List[str] = []
        t = self.thresholds
        min_trades = t.min_trades_by_level.get(target_level, 0)
        min_live = t.min_live_trades_by_level.get(target_level, 0)
        if metrics.completed_trade_count < min_trades:
            reasons.append(f"completed_trade_count {metrics.completed_trade_count} < min {min_trades}")
        if metrics.live_trades < min_live:
            reasons.append(f"live_trades {metrics.live_trades} < min {min_live}")
        if metrics.avg_r < t.min_avg_r:
            reasons.append(f"avg_r {metrics.avg_r:.4f} < min {t.min_avg_r:.4f}")
        if metrics.expected_r < t.min_expected_r:
            reasons.append(f"expected_r {metrics.expected_r:.4f} < min {t.min_expected_r:.4f}")
        if metrics.win_rate < t.min_win_rate:
            reasons.append(f"win_rate {metrics.win_rate:.4f} < min {t.min_win_rate:.4f}")
        if metrics.profit_factor < t.min_profit_factor:
            reasons.append(f"profit_factor {metrics.profit_factor:.4f} < min {t.min_profit_factor:.4f}")
        if metrics.max_drawdown_r > t.max_drawdown_r:
            reasons.append(f"max_drawdown_r {metrics.max_drawdown_r:.4f} > max {t.max_drawdown_r:.4f}")
        if metrics.avg_slippage_bps is not None and metrics.avg_slippage_bps > t.max_avg_slippage_bps:
            reasons.append(
                f"avg_slippage_bps {metrics.avg_slippage_bps:.2f} > max {t.max_avg_slippage_bps:.2f}"
            )
        if metrics.partial_fill_rate > t.max_partial_fill_rate:
            reasons.append(
                f"partial_fill_rate {metrics.partial_fill_rate:.4f} > max {t.max_partial_fill_rate:.4f}"
            )
        if metrics.operational_incidents > t.max_operational_incidents:
            reasons.append(
                f"operational_incidents {metrics.operational_incidents} > max {t.max_operational_incidents}"
            )
        if metrics.latest_evidence_age_days is None:
            reasons.append("no realized outcome evidence")
        elif metrics.latest_evidence_age_days > t.stale_after_days:
            reasons.append(
                f"latest evidence age {metrics.latest_evidence_age_days:.1f}d > stale limit {t.stale_after_days}d"
            )
        if target_level >= 4 and metrics.paper_live_consistency.evaluated and not metrics.paper_live_consistency.consistent:
            reasons.append(f"paper/live consistency failed: {metrics.paper_live_consistency.reason}")
        return reasons


def _outcome_rows(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        r_value = _realized_r(record)
        if r_value is None:
            continue
        outcome = record.get("outcome") or {}
        rows.append(
            {
                "timestamp": _parse_ts(record.get("timestamp")),
                "r": r_value,
                "mode": _mode(record),
                "slippage_pct": _slippage_pct(outcome),
                "partial_fill": bool(outcome.get("partial_fill")),
            }
        )
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def _mode(record: Dict[str, Any]) -> str:
    candidates = [
        record.get("mode"),
        record.get("account_mode"),
        (record.get("config_snapshot") or {}).get("mode"),
        (record.get("trade_plan") or {}).get("mode"),
    ]
    text = " ".join(str(value).lower() for value in candidates if value is not None)
    if "live" in text:
        return "live"
    if "paper" in text:
        return "paper"
    return "unknown"


def _slippage_pct(outcome: Dict[str, Any]) -> Optional[float]:
    for key in ("entry_slippage_pct", "slippage_pct", "avg_slippage_pct"):
        value = _float(outcome.get(key))
        if value is not None and math.isfinite(value):
            return value
    return None


def _paper_live_consistency(
    paper_values: List[float],
    live_values: List[float],
    *,
    min_trades: int,
    max_delta: float,
    min_live_avg_r: float,
) -> PaperLiveConsistency:
    if len(paper_values) < min_trades or len(live_values) < min_trades:
        return PaperLiveConsistency(
            evaluated=False,
            consistent=False,
            paper_trades=len(paper_values),
            live_trades=len(live_values),
        )
    paper_avg = sum(paper_values) / len(paper_values)
    live_avg = sum(live_values) / len(live_values)
    delta = abs(paper_avg - live_avg)
    if live_avg < min_live_avg_r:
        reason = f"live_avg_r {live_avg:.4f} < min {min_live_avg_r:.4f}"
        consistent = False
    elif delta > max_delta:
        reason = f"paper/live avg R delta {delta:.4f} > max {max_delta:.4f}"
        consistent = False
    else:
        reason = "paper/live evidence is consistent"
        consistent = True
    return PaperLiveConsistency(
        evaluated=True,
        consistent=consistent,
        paper_trades=len(paper_values),
        live_trades=len(live_values),
        paper_avg_r=paper_avg,
        live_avg_r=live_avg,
        avg_r_delta=delta,
        reason=reason,
    )


def _profit_factor(wins: List[float], losses: List[float]) -> float:
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _sharpe(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return None
    return avg / stdev * math.sqrt(len(values))


def _sortino(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    downside = [min(0.0, value) for value in values]
    if not any(value < 0 for value in downside):
        return None
    variance = sum(value ** 2 for value in downside) / len(downside)
    downside_dev = math.sqrt(variance)
    if downside_dev == 0:
        return None
    return avg / downside_dev * math.sqrt(len(values))


def _count_operational_incidents(events: Iterable[Dict[str, Any]]) -> int:
    incident_levels = {"incident", "fault", "error", "critical", "fatal", "halt", "paused"}
    count = 0
    for event in events:
        if event.get("resolved") is True:
            continue
        severity = str(event.get("severity") or event.get("type") or event.get("status") or "").lower()
        if not severity or severity in incident_levels:
            count += 1
    return count


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, str):
        try:
            return _ensure_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round_optional(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if math.isinf(value):
        return None
    return round(value, 6)
