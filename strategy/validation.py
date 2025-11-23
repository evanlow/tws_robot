"""
Strategy Validation Enforcement

Enforces validation criteria for paper trading performance before allowing
strategies to transition to validated state. Generates detailed validation
reports showing progress toward validation requirements.

Usage:
    from strategy.validation import ValidationEnforcer
    from strategy.metrics_tracker import PaperMetricsTracker
    
    tracker = PaperMetricsTracker("metrics.db", "my_strategy")
    enforcer = ValidationEnforcer()
    
    if enforcer.can_validate(tracker):
        print("Strategy ready for validation!")
    else:
        report = enforcer.get_validation_report(tracker)
        print(report.summary())
"""

import logging
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .lifecycle import ValidationCriteria, StrategyMetrics
from .metrics_tracker import PaperMetricsTracker, MetricsSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ValidationCheck:
    """Result of a single validation criterion check"""
    
    criterion: str
    passed: bool
    current_value: Any
    required_value: Any
    message: str
    
    def __str__(self) -> str:
        """String representation"""
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.message}"


@dataclass
class ValidationReport:
    """Comprehensive validation report"""
    
    strategy_name: str
    report_date: date
    overall_passed: bool
    checks: List[ValidationCheck]
    days_remaining: int = 0
    trades_remaining: int = 0
    
    def summary(self) -> str:
        """Generate human-readable summary"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"VALIDATION REPORT: {self.strategy_name}")
        lines.append(f"Report Date: {self.report_date}")
        lines.append("=" * 60)
        lines.append("")
        
        if self.overall_passed:
            lines.append("✓ STRATEGY VALIDATION: PASSED")
            lines.append("  All criteria met - ready for VALIDATED state")
        else:
            lines.append("✗ STRATEGY VALIDATION: FAILED")
            lines.append("  Criteria not met - continue paper trading")
        
        lines.append("")
        lines.append("VALIDATION CRITERIA:")
        lines.append("-" * 60)
        
        for check in self.checks:
            lines.append(str(check))
            if not check.passed:
                lines.append(f"  Current: {check.current_value}, Required: {check.required_value}")
        
        lines.append("")
        
        if not self.overall_passed:
            lines.append("PROGRESS:")
            lines.append("-" * 60)
            if self.days_remaining > 0:
                lines.append(f"  Days remaining: {self.days_remaining}")
            if self.trades_remaining > 0:
                lines.append(f"  Trades remaining: {self.trades_remaining}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy_name": self.strategy_name,
            "report_date": str(self.report_date),
            "overall_passed": self.overall_passed,
            "checks": [
                {
                    "criterion": c.criterion,
                    "passed": c.passed,
                    "current_value": c.current_value,
                    "required_value": c.required_value,
                    "message": c.message
                }
                for c in self.checks
            ],
            "days_remaining": self.days_remaining,
            "trades_remaining": self.trades_remaining
        }


class ValidationEnforcer:
    """
    Enforces validation criteria for strategy promotion.
    
    Checks paper trading metrics against ValidationCriteria and generates
    detailed reports showing progress toward validation requirements.
    """
    
    def __init__(self, criteria: Optional[ValidationCriteria] = None):
        """
        Initialize enforcer.
        
        Args:
            criteria: Validation criteria (uses defaults if not provided)
        """
        self.criteria = criteria or ValidationCriteria()
        logger.info(f"ValidationEnforcer initialized with criteria: "
                   f"days={self.criteria.min_days}, trades={self.criteria.min_trades}, "
                   f"sharpe={self.criteria.min_sharpe_ratio:.2f}, "
                   f"dd={self.criteria.max_drawdown:.1%}")
    
    def can_validate(self, tracker: PaperMetricsTracker) -> bool:
        """
        Check if strategy meets all validation criteria.
        
        Args:
            tracker: Metrics tracker for the strategy
            
        Returns:
            True if all criteria met, False otherwise
        """
        snapshot = tracker.get_metrics_snapshot()
        metrics = self._snapshot_to_metrics(snapshot)
        is_valid, _ = self.criteria.validate(metrics)
        
        if is_valid:
            logger.info(f"Strategy '{snapshot.strategy_name}' PASSED validation")
        else:
            logger.warning(f"Strategy '{snapshot.strategy_name}' FAILED validation")
        
        return is_valid
    
    def get_validation_report(self, tracker: PaperMetricsTracker) -> ValidationReport:
        """
        Generate comprehensive validation report.
        
        Args:
            tracker: Metrics tracker for the strategy
            
        Returns:
            Detailed validation report
        """
        snapshot = tracker.get_metrics_snapshot()
        metrics = self._snapshot_to_metrics(snapshot)
        
        checks = []
        
        # Check 1: Minimum days
        days_passed = metrics.days_running >= self.criteria.min_days
        checks.append(ValidationCheck(
            criterion="minimum_days",
            passed=days_passed,
            current_value=metrics.days_running,
            required_value=self.criteria.min_days,
            message=f"Trading days: {metrics.days_running} / {self.criteria.min_days}"
        ))
        
        # Check 2: Minimum trades
        trades_passed = metrics.total_trades >= self.criteria.min_trades
        checks.append(ValidationCheck(
            criterion="minimum_trades",
            passed=trades_passed,
            current_value=metrics.total_trades,
            required_value=self.criteria.min_trades,
            message=f"Total trades: {metrics.total_trades} / {self.criteria.min_trades}"
        ))
        
        # Check 3: Sharpe ratio
        sharpe_passed = metrics.sharpe_ratio >= self.criteria.min_sharpe_ratio
        checks.append(ValidationCheck(
            criterion="sharpe_ratio",
            passed=sharpe_passed,
            current_value=round(metrics.sharpe_ratio, 2),
            required_value=self.criteria.min_sharpe_ratio,
            message=f"Sharpe ratio: {metrics.sharpe_ratio:.2f} (min {self.criteria.min_sharpe_ratio:.2f})"
        ))
        
        # Check 4: Maximum drawdown
        dd_passed = metrics.max_drawdown <= self.criteria.max_drawdown
        checks.append(ValidationCheck(
            criterion="max_drawdown",
            passed=dd_passed,
            current_value=round(metrics.max_drawdown, 4),
            required_value=self.criteria.max_drawdown,
            message=f"Max drawdown: {metrics.max_drawdown:.1%} (max {self.criteria.max_drawdown:.1%})"
        ))
        
        # Check 5: Win rate
        win_rate_passed = metrics.win_rate >= self.criteria.min_win_rate
        checks.append(ValidationCheck(
            criterion="win_rate",
            passed=win_rate_passed,
            current_value=round(metrics.win_rate, 4),
            required_value=self.criteria.min_win_rate,
            message=f"Win rate: {metrics.win_rate:.1%} (min {self.criteria.min_win_rate:.1%})"
        ))
        
        # Check 6: Profit factor
        pf_passed = metrics.profit_factor >= self.criteria.min_profit_factor
        checks.append(ValidationCheck(
            criterion="profit_factor",
            passed=pf_passed,
            current_value=round(metrics.profit_factor, 2),
            required_value=self.criteria.min_profit_factor,
            message=f"Profit factor: {metrics.profit_factor:.2f} (min {self.criteria.min_profit_factor:.2f})"
        ))
        
        # Check 7: Consecutive losses
        losses_passed = metrics.consecutive_losses <= self.criteria.max_consecutive_losses
        checks.append(ValidationCheck(
            criterion="consecutive_losses",
            passed=losses_passed,
            current_value=metrics.consecutive_losses,
            required_value=self.criteria.max_consecutive_losses,
            message=f"Consecutive losses: {metrics.consecutive_losses} (max {self.criteria.max_consecutive_losses})"
        ))
        
        # Calculate overall status and remaining requirements
        overall_passed = all(check.passed for check in checks)
        
        days_remaining = max(0, self.criteria.min_days - metrics.days_running)
        trades_remaining = max(0, self.criteria.min_trades - metrics.total_trades)
        
        # Convert as_of_date to date if it's datetime
        report_date = snapshot.as_of_date
        if isinstance(report_date, datetime):
            report_date = report_date.date()
        
        report = ValidationReport(
            strategy_name=snapshot.strategy_name,
            report_date=report_date,
            overall_passed=overall_passed,
            checks=checks,
            days_remaining=days_remaining,
            trades_remaining=trades_remaining
        )
        
        logger.info(f"Generated validation report for '{snapshot.strategy_name}': "
                   f"{'PASSED' if overall_passed else 'FAILED'}")
        
        return report
    
    def check_criterion(self, tracker: PaperMetricsTracker, criterion: str) -> bool:
        """
        Check a single validation criterion.
        
        Args:
            tracker: Metrics tracker
            criterion: Criterion name (e.g., 'minimum_days', 'sharpe_ratio')
            
        Returns:
            True if criterion passed, False otherwise
            
        Raises:
            ValueError: If criterion name invalid
        """
        snapshot = tracker.get_metrics_snapshot()
        metrics = self._snapshot_to_metrics(snapshot)
        
        if criterion == "minimum_days":
            return metrics.days_running >= self.criteria.min_days
        elif criterion == "minimum_trades":
            return metrics.total_trades >= self.criteria.min_trades
        elif criterion == "sharpe_ratio":
            return metrics.sharpe_ratio >= self.criteria.min_sharpe_ratio
        elif criterion == "max_drawdown":
            return metrics.max_drawdown <= self.criteria.max_drawdown
        elif criterion == "win_rate":
            return metrics.win_rate >= self.criteria.min_win_rate
        elif criterion == "profit_factor":
            return metrics.profit_factor >= self.criteria.min_profit_factor
        elif criterion == "consecutive_losses":
            return metrics.consecutive_losses <= self.criteria.max_consecutive_losses
        else:
            raise ValueError(f"Invalid criterion: {criterion}")
    
    def get_failed_criteria(self, tracker: PaperMetricsTracker) -> List[str]:
        """
        Get list of failed validation criteria.
        
        Args:
            tracker: Metrics tracker
            
        Returns:
            List of criterion names that failed
        """
        snapshot = tracker.get_metrics_snapshot()
        metrics = self._snapshot_to_metrics(snapshot)
        _, failures = self.criteria.validate(metrics)
        
        # Extract criterion names from failure messages
        failed = []
        for failure in failures:
            if "Insufficient days" in failure:
                failed.append("minimum_days")
            elif "Insufficient trades" in failure:
                failed.append("minimum_trades")
            elif "Low Sharpe ratio" in failure:
                failed.append("sharpe_ratio")
            elif "Excessive drawdown" in failure:
                failed.append("max_drawdown")
            elif "Low win rate" in failure:
                failed.append("win_rate")
            elif "Low profit factor" in failure:
                failed.append("profit_factor")
            elif "Too many consecutive losses" in failure:
                failed.append("consecutive_losses")
        
        return failed
    
    def _snapshot_to_metrics(self, snapshot: MetricsSnapshot) -> StrategyMetrics:
        """Convert MetricsSnapshot to StrategyMetrics"""
        return StrategyMetrics(
            days_running=snapshot.days_running,
            total_trades=snapshot.total_trades,
            sharpe_ratio=snapshot.sharpe_ratio,
            max_drawdown=snapshot.max_drawdown,
            win_rate=snapshot.win_rate,
            profit_factor=snapshot.profit_factor,
            consecutive_losses=snapshot.consecutive_losses,
            total_pnl=snapshot.total_pnl
        )
