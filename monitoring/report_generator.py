"""Automated Report Generator.

Generates daily and weekly portfolio summaries, monitors threshold-based
alerts, and provides a simple notification interface for trading events.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportPeriod(str, Enum):
    """Supported reporting periods."""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NotificationChannel(str, Enum):
    """Supported notification channels."""
    LOG = "LOG"         # Python logging
    CALLBACK = "CALLBACK"  # User-supplied callback
    INTERNAL = "INTERNAL"  # In-memory queue for UI polling


@dataclass
class AlertRule:
    """A threshold-based alert rule."""
    name: str
    metric: str           # e.g. "drawdown", "margin_utilization"
    threshold: float
    comparison: str       # "gt", "lt", "gte", "lte"
    severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_minutes: int = 60
    message_template: str = ""
    _last_triggered: Optional[datetime] = field(default=None, repr=False)

    def evaluate(self, value: float) -> bool:
        """Return True if the rule fires on the given value."""
        ops = {
            "gt": value > self.threshold,
            "lt": value < self.threshold,
            "gte": value >= self.threshold,
            "lte": value <= self.threshold,
        }
        return ops.get(self.comparison, False)

    def is_in_cooldown(self) -> bool:
        if self._last_triggered is None:
            return False
        return (datetime.utcnow() - self._last_triggered) < timedelta(minutes=self.cooldown_minutes)

    def mark_triggered(self) -> None:
        self._last_triggered = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "metric": self.metric,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "severity": self.severity.value,
            "cooldown_minutes": self.cooldown_minutes,
        }


@dataclass
class Alert:
    """A triggered alert instance."""
    rule_name: str
    severity: AlertSeverity
    message: str
    metric_value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "metric_value": round(self.metric_value, 4),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ReportSection:
    """A named section within a report."""
    title: str
    data: Dict[str, Any] = field(default_factory=dict)
    highlights: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "data": self.data,
            "highlights": self.highlights,
        }


@dataclass
class Report:
    """A complete generated report."""
    period: ReportPeriod
    start_date: datetime
    end_date: datetime
    sections: List[ReportSection] = field(default_factory=list)
    alerts_during_period: List[Alert] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "period": self.period.value,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "sections": [s.to_dict() for s in self.sections],
            "alerts_during_period": [a.to_dict() for a in self.alerts_during_period],
            "generated_at": self.generated_at.isoformat(),
        }


class ReportGenerator:
    """Generates portfolio reports and manages threshold-based alerts.

    The generator accumulates daily snapshots and can produce daily,
    weekly, or monthly summary reports.  Alert rules are evaluated
    whenever metrics are pushed in via ``evaluate_metrics``.
    """

    def __init__(self) -> None:
        self._rules: List[AlertRule] = []
        self._alerts: List[Alert] = []
        self._notifications: List[Dict] = []
        self._callbacks: List[Callable[[Alert], None]] = []
        self._snapshots: List[Dict] = []  # daily metric snapshots

    # ------------------------------------------------------------------
    # Alert Rules
    # ------------------------------------------------------------------

    def add_rule(self, rule: AlertRule) -> None:
        """Register a new alert rule."""
        self._rules.append(rule)
        logger.info("Alert rule added: %s", rule.name)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if found."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def add_default_rules(self) -> None:
        """Register a sensible set of default alert rules."""
        defaults = [
            AlertRule(
                name="high_drawdown",
                metric="drawdown_pct",
                threshold=0.10,
                comparison="gte",
                severity=AlertSeverity.WARNING,
                message_template="Drawdown at {value:.1%} — exceeds 10% threshold",
            ),
            AlertRule(
                name="critical_drawdown",
                metric="drawdown_pct",
                threshold=0.20,
                comparison="gte",
                severity=AlertSeverity.CRITICAL,
                message_template="Drawdown at {value:.1%} — CRITICAL (>20%)",
            ),
            AlertRule(
                name="margin_warning",
                metric="margin_utilization",
                threshold=0.70,
                comparison="gte",
                severity=AlertSeverity.WARNING,
                message_template="Margin utilization at {value:.1%}",
            ),
            AlertRule(
                name="low_cash",
                metric="cash_pct",
                threshold=0.05,
                comparison="lte",
                severity=AlertSeverity.WARNING,
                message_template="Cash buffer at {value:.1%} — dangerously low",
            ),
            AlertRule(
                name="daily_loss",
                metric="daily_pnl_pct",
                threshold=-0.03,
                comparison="lte",
                severity=AlertSeverity.WARNING,
                message_template="Daily loss at {value:.1%}",
            ),
        ]
        for rule in defaults:
            self.add_rule(rule)

    # ------------------------------------------------------------------
    # Metric Evaluation
    # ------------------------------------------------------------------

    def evaluate_metrics(self, metrics: Dict[str, float]) -> List[Alert]:
        """Evaluate all rules against current metrics.

        Args:
            metrics: Dict mapping metric name → current value (e.g.
                     ``{"drawdown_pct": 0.12, "margin_utilization": 0.55}``).

        Returns:
            List of newly triggered alerts.
        """
        triggered: List[Alert] = []
        for rule in self._rules:
            value = metrics.get(rule.metric)
            if value is None:
                continue
            if rule.evaluate(value) and not rule.is_in_cooldown():
                msg = rule.message_template.format(value=value) if rule.message_template else (
                    f"{rule.name}: {rule.metric}={value:.4f} {rule.comparison} {rule.threshold}"
                )
                alert = Alert(
                    rule_name=rule.name,
                    severity=rule.severity,
                    message=msg,
                    metric_value=value,
                )
                rule.mark_triggered()
                triggered.append(alert)
                self._alerts.append(alert)
                self._dispatch(alert)
        return triggered

    def push_snapshot(self, snapshot: Dict) -> None:
        """Store a daily metrics snapshot for report generation."""
        snapshot.setdefault("timestamp", datetime.utcnow().isoformat())
        self._snapshots.append(snapshot)

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------

    def generate_report(
        self,
        period: ReportPeriod = ReportPeriod.DAILY,
        end_date: Optional[datetime] = None,
    ) -> Report:
        """Generate a summary report for the given period.

        Args:
            period: DAILY, WEEKLY, or MONTHLY.
            end_date: End of report period (defaults to now).

        Returns:
            Report object with sections and alerts.
        """
        end = end_date or datetime.utcnow()
        if period == ReportPeriod.DAILY:
            start = end - timedelta(days=1)
        elif period == ReportPeriod.WEEKLY:
            start = end - timedelta(days=7)
        else:
            start = end - timedelta(days=30)

        period_snapshots = self._filter_snapshots(start, end)
        period_alerts = self._filter_alerts(start, end)

        sections: List[ReportSection] = []

        # Performance summary
        perf = self._build_performance_section(period_snapshots)
        sections.append(perf)

        # Risk summary
        risk = self._build_risk_section(period_snapshots)
        sections.append(risk)

        # Trading activity
        trading = self._build_trading_section(period_snapshots)
        sections.append(trading)

        return Report(
            period=period,
            start_date=start,
            end_date=end,
            sections=sections,
            alerts_during_period=period_alerts,
        )

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def register_callback(self, callback: Callable[[Alert], None]) -> None:
        """Register a callback function to receive alerts."""
        self._callbacks.append(callback)

    def get_recent_alerts(self, limit: int = 50) -> List[Alert]:
        """Return most recent alerts."""
        return list(reversed(self._alerts[-limit:]))

    def get_notifications(self, limit: int = 50) -> List[Dict]:
        """Return queued notifications (for UI polling)."""
        return list(reversed(self._notifications[-limit:]))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch(self, alert: Alert) -> None:
        """Send alert to all registered channels."""
        log_fn = logger.warning if alert.severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL) else logger.info
        log_fn("[ALERT] %s: %s", alert.severity.value, alert.message)

        self._notifications.append(alert.to_dict())

        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception:
                logger.exception("Alert callback failed")

    def _filter_snapshots(self, start: datetime, end: datetime) -> List[Dict]:
        results: List[Dict] = []
        for snap in self._snapshots:
            ts_str = snap.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str
            except (ValueError, TypeError):
                continue
            if start <= ts <= end:
                results.append(snap)
        return results

    def _filter_alerts(self, start: datetime, end: datetime) -> List[Alert]:
        return [a for a in self._alerts if start <= a.timestamp <= end]

    @staticmethod
    def _build_performance_section(snapshots: List[Dict]) -> ReportSection:
        highlights: List[str] = []
        data: Dict[str, Any] = {"snapshot_count": len(snapshots)}

        if snapshots:
            equities = [s.get("equity", 0) for s in snapshots if "equity" in s]
            if equities:
                data["start_equity"] = round(equities[0], 2)
                data["end_equity"] = round(equities[-1], 2)
                change = equities[-1] - equities[0]
                data["equity_change"] = round(change, 2)
                if equities[0] > 0:
                    data["return_pct"] = round(change / equities[0] * 100, 4)
                    highlights.append(f"Period return: {data['return_pct']:.2f}%")
            pnls = [s.get("daily_pnl", 0) for s in snapshots if "daily_pnl" in s]
            if pnls:
                data["total_pnl"] = round(sum(pnls), 2)
                data["best_day"] = round(max(pnls), 2)
                data["worst_day"] = round(min(pnls), 2)

        return ReportSection(title="Performance Summary", data=data, highlights=highlights)

    @staticmethod
    def _build_risk_section(snapshots: List[Dict]) -> ReportSection:
        highlights: List[str] = []
        data: Dict[str, Any] = {}

        if snapshots:
            dd = [s.get("drawdown_pct", 0) for s in snapshots if "drawdown_pct" in s]
            if dd:
                data["max_drawdown_pct"] = round(max(dd) * 100, 2)
                highlights.append(f"Max drawdown: {data['max_drawdown_pct']:.2f}%")
            mu = [s.get("margin_utilization", 0) for s in snapshots if "margin_utilization" in s]
            if mu:
                data["avg_margin_utilization"] = round(sum(mu) / len(mu) * 100, 2)

        return ReportSection(title="Risk Summary", data=data, highlights=highlights)

    @staticmethod
    def _build_trading_section(snapshots: List[Dict]) -> ReportSection:
        data: Dict[str, Any] = {}
        highlights: List[str] = []

        trades = sum(s.get("trades_count", 0) for s in snapshots)
        data["total_trades"] = trades
        if trades > 0:
            highlights.append(f"{trades} trades executed")

        return ReportSection(title="Trading Activity", data=data, highlights=highlights)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        return {
            "rules_count": len(self._rules),
            "total_alerts": len(self._alerts),
            "snapshots_stored": len(self._snapshots),
            "notification_queue": len(self._notifications),
            "callbacks_registered": len(self._callbacks),
        }
