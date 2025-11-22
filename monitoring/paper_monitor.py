"""
Paper Trading Monitor

Real-time terminal-based display of paper trading strategies.

Displays:
1. Strategy Status - Name, state, runtime, positions, P&L
2. Risk Metrics - Portfolio value, margin, drawdown, risk utilization
3. Order Activity - Recent orders with status and fill prices
4. Performance Summary - Return %, Sharpe, win rate, total trades

Author: TWS Robot Development Team
Date: November 22, 2025
Sprint 1 Task 4
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

from strategy.lifecycle import StrategyState, StrategyMetrics
from backtest.data_models import Position
from execution.paper_adapter import PendingOrder

logger = logging.getLogger(__name__)


@dataclass
class StrategySnapshot:
    """Snapshot of strategy state for display"""
    name: str
    state: StrategyState
    start_time: datetime
    positions: Dict[str, Position]
    session_pnl: float
    total_pnl: float
    metrics: StrategyMetrics


@dataclass
class RiskSnapshot:
    """Snapshot of risk metrics for display"""
    portfolio_value: float
    margin_used: float
    margin_available: float
    max_drawdown: float
    position_count: int
    risk_limit_utilization: float  # 0.0 to 1.0


class PaperMonitor:
    """
    Real-time monitor for paper trading strategies.
    
    Displays comprehensive strategy status, risk metrics, orders, and performance
    in a terminal-based dashboard using Rich library.
    """
    
    def __init__(self, console: Optional[Console] = None):
        """
        Initialize paper monitor.
        
        Args:
            console: Rich Console instance (creates new if None)
        """
        self.console = console or Console()
        self._strategy_snapshots: Dict[str, StrategySnapshot] = {}
        self._risk_snapshot: Optional[RiskSnapshot] = None
        self._recent_orders: List[PendingOrder] = []
        self._max_orders_display = 20
        
    def update_strategy(self, snapshot: StrategySnapshot):
        """
        Update strategy snapshot.
        
        Args:
            snapshot: Current strategy state
        """
        self._strategy_snapshots[snapshot.name] = snapshot
        
    def update_risk(self, snapshot: RiskSnapshot):
        """
        Update risk metrics snapshot.
        
        Args:
            snapshot: Current risk state
        """
        self._risk_snapshot = snapshot
        
    def add_order(self, order: PendingOrder):
        """
        Add order to activity feed.
        
        Args:
            order: Order to display
        """
        self._recent_orders.insert(0, order)
        if len(self._recent_orders) > self._max_orders_display:
            self._recent_orders = self._recent_orders[:self._max_orders_display]
    
    def _create_strategy_panel(self) -> Panel:
        """Create strategy status panel"""
        if not self._strategy_snapshots:
            return Panel(
                Text("No active strategies", style="dim"),
                title="Strategy Status",
                border_style="blue"
            )
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Strategy", style="cyan", no_wrap=True)
        table.add_column("State", style="green")
        table.add_column("Runtime", style="yellow")
        table.add_column("Positions", justify="right")
        table.add_column("Session P&L", justify="right")
        table.add_column("Total P&L", justify="right")
        
        for snapshot in self._strategy_snapshots.values():
            runtime = datetime.now() - snapshot.start_time
            hours = int(runtime.total_seconds() // 3600)
            minutes = int((runtime.total_seconds() % 3600) // 60)
            runtime_str = f"{hours}h {minutes}m"
            
            # Count positions
            pos_count = len([p for p in snapshot.positions.values() if p.quantity != 0])
            
            # Color code P&L
            session_pnl_style = "green" if snapshot.session_pnl >= 0 else "red"
            total_pnl_style = "green" if snapshot.total_pnl >= 0 else "red"
            
            table.add_row(
                snapshot.name,
                snapshot.state.value.upper(),
                runtime_str,
                str(pos_count),
                f"[{session_pnl_style}]${snapshot.session_pnl:,.2f}[/{session_pnl_style}]",
                f"[{total_pnl_style}]${snapshot.total_pnl:,.2f}[/{total_pnl_style}]"
            )
        
        return Panel(table, title="Strategy Status", border_style="blue")
    
    def _create_risk_panel(self) -> Panel:
        """Create risk metrics panel"""
        if not self._risk_snapshot:
            return Panel(
                Text("No risk data available", style="dim"),
                title="Risk Metrics",
                border_style="yellow"
            )
        
        risk = self._risk_snapshot
        
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", justify="right")
        
        # Portfolio value
        table.add_row("Portfolio Value", f"${risk.portfolio_value:,.2f}")
        
        # Margin
        margin_pct = (risk.margin_used / risk.portfolio_value * 100) if risk.portfolio_value > 0 else 0
        margin_style = "red" if margin_pct > 80 else "yellow" if margin_pct > 60 else "green"
        table.add_row(
            "Margin Used",
            f"[{margin_style}]${risk.margin_used:,.2f} ({margin_pct:.1f}%)[/{margin_style}]"
        )
        table.add_row("Margin Available", f"${risk.margin_available:,.2f}")
        
        # Drawdown
        dd_style = "red" if risk.max_drawdown > 0.08 else "yellow" if risk.max_drawdown > 0.05 else "green"
        table.add_row(
            "Max Drawdown",
            f"[{dd_style}]{risk.max_drawdown:.2%}[/{dd_style}]"
        )
        
        # Positions
        table.add_row("Open Positions", str(risk.position_count))
        
        # Risk utilization
        util_style = "red" if risk.risk_limit_utilization > 0.9 else "yellow" if risk.risk_limit_utilization > 0.7 else "green"
        table.add_row(
            "Risk Utilization",
            f"[{util_style}]{risk.risk_limit_utilization:.1%}[/{util_style}]"
        )
        
        return Panel(table, title="Risk Metrics", border_style="yellow")
    
    def _create_orders_panel(self) -> Panel:
        """Create order activity panel"""
        if not self._recent_orders:
            return Panel(
                Text("No recent orders", style="dim"),
                title="Order Activity",
                border_style="magenta"
            )
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Time", style="dim", no_wrap=True)
        table.add_column("Symbol", style="cyan")
        table.add_column("Action", style="yellow")
        table.add_column("Qty", justify="right")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Filled", justify="right")
        table.add_column("Avg Price", justify="right")
        
        for order in self._recent_orders:
            # Format time (would come from order timestamp if available)
            time_str = "HH:MM:SS"  # Placeholder
            
            # Status styling
            status_style = {
                "FILLED": "green",
                "PARTIAL": "yellow",
                "PENDING": "blue",
                "CANCELLED": "red",
                "REJECTED": "red"
            }.get(order.status, "white")
            
            # Action styling
            action_style = "green" if order.action == "BUY" else "red"
            
            table.add_row(
                time_str,
                order.symbol,
                f"[{action_style}]{order.action}[/{action_style}]",
                str(order.quantity),
                order.order_type,
                f"[{status_style}]{order.status}[/{status_style}]",
                str(order.filled_qty),
                f"${order.avg_fill_price:.2f}" if order.avg_fill_price > 0 else "-"
            )
        
        return Panel(table, title=f"Order Activity (Last {len(self._recent_orders)})", border_style="magenta")
    
    def _create_performance_panel(self) -> Panel:
        """Create performance summary panel"""
        if not self._strategy_snapshots:
            return Panel(
                Text("No performance data available", style="dim"),
                title="Performance Summary",
                border_style="green"
            )
        
        # Aggregate metrics from all strategies
        total_return = 0.0
        total_trades = 0
        avg_sharpe = 0.0
        avg_win_rate = 0.0
        strategy_count = len(self._strategy_snapshots)
        
        for snapshot in self._strategy_snapshots.values():
            metrics = snapshot.metrics
            total_trades += metrics.total_trades
            avg_sharpe += metrics.sharpe_ratio
            avg_win_rate += metrics.win_rate
            
            # Calculate return from total P&L (simplified)
            if self._risk_snapshot and self._risk_snapshot.portfolio_value > 0:
                total_return = (snapshot.total_pnl / self._risk_snapshot.portfolio_value) * 100
        
        if strategy_count > 0:
            avg_sharpe /= strategy_count
            avg_win_rate /= strategy_count
        
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", justify="right")
        
        # Total return
        return_style = "green" if total_return >= 0 else "red"
        table.add_row(
            "Total Return",
            f"[{return_style}]{total_return:+.2f}%[/{return_style}]"
        )
        
        # Sharpe ratio
        sharpe_style = "green" if avg_sharpe >= 1.0 else "yellow" if avg_sharpe >= 0.5 else "red"
        table.add_row(
            "Sharpe Ratio",
            f"[{sharpe_style}]{avg_sharpe:.2f}[/{sharpe_style}]"
        )
        
        # Win rate
        win_rate_style = "green" if avg_win_rate >= 0.5 else "yellow" if avg_win_rate >= 0.4 else "red"
        table.add_row(
            "Win Rate",
            f"[{win_rate_style}]{avg_win_rate:.1%}[/{win_rate_style}]"
        )
        
        # Total trades
        table.add_row("Total Trades", str(total_trades))
        
        # Active strategies
        table.add_row("Active Strategies", str(strategy_count))
        
        return Panel(table, title="Performance Summary", border_style="green")
    
    def render(self) -> Layout:
        """
        Render complete dashboard layout.
        
        Returns:
            Rich Layout with all panels
        """
        layout = Layout()
        
        # Create 2x2 grid
        layout.split_column(
            Layout(name="top", size=12),
            Layout(name="bottom", size=12)
        )
        
        layout["top"].split_row(
            Layout(self._create_strategy_panel(), name="strategy"),
            Layout(self._create_risk_panel(), name="risk")
        )
        
        layout["bottom"].split_row(
            Layout(self._create_orders_panel(), name="orders"),
            Layout(self._create_performance_panel(), name="performance")
        )
        
        return layout
    
    def display(self):
        """Display current state (one-time render)"""
        self.console.clear()
        self.console.print(self.render())
    
    def start_live_display(self, refresh_rate: float = 1.0):
        """
        Start live updating display.
        
        Args:
            refresh_rate: Update frequency in seconds
            
        Note: This is a blocking call. Use in separate thread if needed.
        """
        with Live(self.render(), console=self.console, refresh_per_second=1/refresh_rate) as live:
            # Live display runs until interrupted
            # Application should call live.stop() or Ctrl+C
            pass
