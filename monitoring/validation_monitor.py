"""
Validation Dashboard Enhancement

Extends PaperMonitor with validation status tracking, performance charts,
and alert panels for comprehensive strategy monitoring.

Features:
1. Validation Status Panel - Progress toward promotion criteria
2. Performance Charts - Equity curve, drawdown, win/loss distribution
3. Alerts Panel - Risk breaches, milestones, manual actions

Author: TWS Robot Development Team
Date: November 23, 2025
Sprint 2 Task 5
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn
from rich import box

from monitoring.paper_monitor import PaperMonitor, StrategySnapshot, RiskSnapshot
from strategy.validation import ValidationReport, ValidationCheck, ValidationEnforcer
from strategy.metrics_tracker import PaperMetricsTracker, MetricsSnapshot
from strategy.promotion import PromotionWorkflow, ApprovalGate
from strategy.lifecycle import StrategyState

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """System alert for monitoring"""
    level: AlertLevel
    timestamp: datetime
    strategy_name: str
    message: str
    action_required: bool = False


@dataclass
class ValidationStatus:
    """Validation progress for a strategy"""
    strategy_name: str
    report: ValidationReport
    days_remaining: int
    trades_remaining: int
    promotion_gate: Optional[ApprovalGate]


class ValidationMonitor(PaperMonitor):
    """
    Enhanced paper trading monitor with validation tracking.
    
    Extends PaperMonitor with:
    - Validation progress panel
    - Performance visualization (sparklines)
    - Alert panel for breaches and milestones
    """
    
    def __init__(self, console: Optional[Console] = None):
        """
        Initialize validation monitor.
        
        Args:
            console: Rich Console instance (creates new if None)
        """
        super().__init__(console)
        self._validation_statuses: Dict[str, ValidationStatus] = {}
        self._alerts: List[Alert] = []
        self._max_alerts_display = 10
        self._equity_curves: Dict[str, List[float]] = {}  # Strategy -> value history
        self._max_sparkline_points = 30
        
    def update_validation_status(
        self,
        strategy_name: str,
        report: ValidationReport,
        days_remaining: int,
        trades_remaining: int,
        promotion_gate: Optional[ApprovalGate] = None
    ):
        """
        Update validation status for strategy.
        
        Args:
            strategy_name: Strategy identifier
            report: Current validation report
            days_remaining: Days until minimum trading period
            trades_remaining: Trades until minimum count
            promotion_gate: Current promotion workflow gate
        """
        self._validation_statuses[strategy_name] = ValidationStatus(
            strategy_name=strategy_name,
            report=report,
            days_remaining=days_remaining,
            trades_remaining=trades_remaining,
            promotion_gate=promotion_gate
        )
        
    def add_alert(self, alert: Alert):
        """
        Add alert to monitoring feed.
        
        Args:
            alert: Alert to display
        """
        self._alerts.insert(0, alert)
        if len(self._alerts) > self._max_alerts_display:
            self._alerts = self._alerts[:self._max_alerts_display]
            
        # Log alert
        if alert.level == AlertLevel.CRITICAL:
            logger.critical(f"[{alert.strategy_name}] {alert.message}")
        elif alert.level == AlertLevel.WARNING:
            logger.warning(f"[{alert.strategy_name}] {alert.message}")
        else:
            logger.info(f"[{alert.strategy_name}] {alert.message}")
    
    def update_equity_curve(self, strategy_name: str, portfolio_value: float):
        """
        Update equity curve data for strategy.
        
        Args:
            strategy_name: Strategy identifier
            portfolio_value: Current portfolio value
        """
        if strategy_name not in self._equity_curves:
            self._equity_curves[strategy_name] = []
        
        self._equity_curves[strategy_name].append(portfolio_value)
        
        # Keep only recent points
        if len(self._equity_curves[strategy_name]) > self._max_sparkline_points:
            self._equity_curves[strategy_name] = self._equity_curves[strategy_name][-self._max_sparkline_points:]
    
    def _create_validation_panel(self) -> Panel:
        """Create validation status panel"""
        if not self._validation_statuses:
            return Panel(
                Text("No validation data available", style="dim"),
                title="Validation Status",
                border_style="cyan"
            )
        
        # Create table for each strategy
        tables = []
        for status in self._validation_statuses.values():
            table = Table(
                show_header=True,
                header_style="bold cyan",
                title=f"{status.strategy_name}",
                title_style="bold white",
                box=box.SIMPLE
            )
            table.add_column("Criterion", style="cyan", no_wrap=True)
            table.add_column("Status", justify="center", width=8)
            table.add_column("Progress", justify="left", width=40)
            
            report = status.report
            
            # Add each validation check
            for check in report.checks:
                # Status indicator
                if check.passed:
                    status_icon = "[green]✓ PASS[/green]"
                else:
                    status_icon = "[red]✗ FAIL[/red]"
                
                # Progress bar
                if isinstance(check.current_value, (int, float)) and isinstance(check.required_value, (int, float)):
                    current = float(check.current_value)
                    required = float(check.required_value)
                    
                    if required > 0:
                        pct = min(100, (current / required) * 100)
                    else:
                        pct = 100 if check.passed else 0
                    
                    # Create simple ASCII progress bar
                    bar_width = 20
                    filled = int((pct / 100) * bar_width)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    
                    if check.passed:
                        progress_text = f"[green]{bar}[/green] {pct:.0f}%"
                    else:
                        progress_text = f"[yellow]{bar}[/yellow] {pct:.0f}%"
                else:
                    progress_text = check.message
                
                # Criterion name (clean up underscores)
                criterion_name = check.criterion.replace("_", " ").title()
                
                table.add_row(criterion_name, status_icon, progress_text)
            
            # Add countdown info
            if status.days_remaining > 0:
                table.add_row(
                    "",
                    "",
                    f"[yellow]⏱ {status.days_remaining} days until eligible[/yellow]"
                )
            elif status.trades_remaining > 0:
                table.add_row(
                    "",
                    "",
                    f"[yellow]⏱ {status.trades_remaining} trades until minimum[/yellow]"
                )
            
            # Add promotion gate status
            if status.promotion_gate:
                gate_names = {
                    ApprovalGate.GATE_1_VALIDATION: "Gate 1 (Validation)",
                    ApprovalGate.GATE_2_LIVE_APPROVAL: "Gate 2 (Live Approval)",
                    ApprovalGate.GATE_3_LIVE_ACTIVATION: "Gate 3 (Activation)"
                }
                gate_name = gate_names.get(status.promotion_gate, "Unknown Gate")
                table.add_row(
                    "",
                    "",
                    f"[blue]📋 Current: {gate_name}[/blue]"
                )
            
            # Overall status
            if report.overall_passed:
                table.add_row(
                    "",
                    "[green bold]READY[/green bold]",
                    "[green]All criteria met - Ready for promotion[/green]"
                )
            else:
                failed_count = len([c for c in report.checks if not c.passed])
                table.add_row(
                    "",
                    "[yellow bold]PENDING[/yellow bold]",
                    f"[yellow]{failed_count} criteria remaining[/yellow]"
                )
            
            tables.append(table)
        
        # Combine all tables
        if len(tables) == 1:
            content = tables[0]
        else:
            # Multiple strategies - stack them
            content = Text("")  # Placeholder, would stack tables
            for table in tables:
                content = table  # For now, just show first
                break
        
        return Panel(content, title="Validation Status", border_style="cyan")
    
    def _create_performance_charts_panel(self) -> Panel:
        """Create performance visualization panel"""
        if not self._equity_curves:
            return Panel(
                Text("No performance data available", style="dim"),
                title="Performance Charts",
                border_style="magenta"
            )
        
        # Create sparklines for each strategy
        lines = []
        
        for strategy_name, values in self._equity_curves.items():
            if not values:
                continue
            
            # Calculate simple sparkline
            sparkline = self._create_sparkline(values)
            
            # Calculate stats
            start_value = values[0]
            current_value = values[-1]
            change = current_value - start_value
            change_pct = (change / start_value * 100) if start_value > 0 else 0
            
            # Color code
            if change_pct >= 0:
                color = "green"
                indicator = "↑"
            else:
                color = "red"
                indicator = "↓"
            
            # Format line
            line = Text()
            line.append(f"{strategy_name:20s} ", style="cyan")
            line.append(sparkline + " ", style=color)
            line.append(f"{indicator} ", style=color)
            line.append(f"${current_value:,.0f} ", style="white")
            line.append(f"({change_pct:+.2f}%)", style=color)
            
            lines.append(line)
        
        # Combine lines
        if not lines:
            content = Text("No equity data", style="dim")
        else:
            content = Text("\n").join(lines)
        
        return Panel(content, title="Equity Curves", border_style="magenta")
    
    def _create_sparkline(self, values: List[float], width: int = 20) -> str:
        """
        Create ASCII sparkline from values.
        
        Args:
            values: Data points
            width: Character width
            
        Returns:
            Sparkline string
        """
        if not values or len(values) < 2:
            return "─" * width
        
        # Sample values if too many
        if len(values) > width:
            step = len(values) / width
            sampled = [values[int(i * step)] for i in range(width)]
        else:
            sampled = values
        
        # Normalize to 0-7 range (for Unicode block characters)
        min_val = min(sampled)
        max_val = max(sampled)
        
        if max_val == min_val:
            return "─" * width
        
        range_val = max_val - min_val
        
        # Unicode block characters for sparklines
        blocks = " ▁▂▃▄▅▆▇█"
        
        sparkline = ""
        for val in sampled:
            normalized = (val - min_val) / range_val
            block_idx = int(normalized * (len(blocks) - 1))
            sparkline += blocks[block_idx]
        
        return sparkline
    
    def _create_alerts_panel(self) -> Panel:
        """Create alerts panel"""
        if not self._alerts:
            return Panel(
                Text("No alerts", style="dim green"),
                title="System Alerts",
                border_style="red"
            )
        
        table = Table(show_header=True, header_style="bold red", box=box.SIMPLE)
        table.add_column("Time", style="dim", no_wrap=True, width=8)
        table.add_column("Level", justify="center", width=10)
        table.add_column("Strategy", style="cyan", width=15)
        table.add_column("Message", style="white")
        
        for alert in self._alerts:
            # Format timestamp
            time_str = alert.timestamp.strftime("%H:%M:%S")
            
            # Level styling
            level_styles = {
                AlertLevel.INFO: ("INFO", "blue"),
                AlertLevel.WARNING: ("WARN", "yellow"),
                AlertLevel.CRITICAL: ("CRIT", "red bold")
            }
            level_text, level_style = level_styles.get(alert.level, ("INFO", "white"))
            
            # Add action required indicator
            message = alert.message
            if alert.action_required:
                message = "⚠ " + message
            
            table.add_row(
                time_str,
                f"[{level_style}]{level_text}[/{level_style}]",
                alert.strategy_name,
                message
            )
        
        return Panel(
            table,
            title=f"System Alerts ({len(self._alerts)})",
            border_style="red"
        )
    
    def render(self) -> Layout:
        """
        Render enhanced dashboard layout.
        
        Returns:
            Rich Layout with all panels including validation
        """
        layout = Layout()
        
        # Create 3-row layout
        layout.split_column(
            Layout(name="top", size=12),
            Layout(name="middle", size=15),
            Layout(name="bottom", size=12)
        )
        
        # Top row: Strategy Status + Risk Metrics (from parent class)
        layout["top"].split_row(
            Layout(self._create_strategy_panel(), name="strategy"),
            Layout(self._create_risk_panel(), name="risk")
        )
        
        # Middle row: Validation Status + Performance Charts (NEW)
        layout["middle"].split_row(
            Layout(self._create_validation_panel(), name="validation"),
            Layout(self._create_performance_charts_panel(), name="charts")
        )
        
        # Bottom row: Order Activity + Alerts (NEW)
        layout["bottom"].split_row(
            Layout(self._create_orders_panel(), name="orders"),
            Layout(self._create_alerts_panel(), name="alerts")
        )
        
        return layout


def create_validation_alert(
    strategy_name: str,
    level: AlertLevel,
    message: str,
    action_required: bool = False
) -> Alert:
    """
    Convenience function to create validation alert.
    
    Args:
        strategy_name: Strategy identifier
        level: Alert severity
        message: Alert message
        action_required: Whether manual action needed
        
    Returns:
        Alert instance
    """
    return Alert(
        level=level,
        timestamp=datetime.now(),
        strategy_name=strategy_name,
        message=message,
        action_required=action_required
    )
