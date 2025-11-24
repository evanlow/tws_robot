"""
Sprint 3 Task 4: Performance Attribution System
Analyzes P&L sources, identifies top/bottom contributors, and breaks down performance.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class AttributionMetric(Enum):
    """Types of attribution metrics."""
    STRATEGY = "strategy"  # Attribute by strategy name
    SYMBOL = "symbol"      # Attribute by trading symbol
    DATE = "date"          # Attribute by trading date
    HOUR = "hour"          # Attribute by hour of day
    DAY_OF_WEEK = "day_of_week"  # Attribute by day of week


class AttributionPeriod(Enum):
    """Time periods for attribution analysis."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TradeAttribution:
    """
    Represents a single trade with attribution metadata.
    
    Attributes:
        symbol: Trading symbol
        entry_time: Trade entry timestamp
        exit_time: Trade exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Number of shares/contracts
        pnl: Profit/loss (gross)
        strategy: Strategy that generated the trade
        commission: Total commissions paid
    """
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    strategy: str
    commission: float = 0.0
    
    @classmethod
    def from_dict(cls, trade_dict: Dict) -> 'TradeAttribution':
        """Create TradeAttribution from trade dictionary."""
        return cls(
            symbol=trade_dict["symbol"],
            entry_time=trade_dict["entry_time"],
            exit_time=trade_dict["exit_time"],
            entry_price=trade_dict["entry_price"],
            exit_price=trade_dict["exit_price"],
            quantity=trade_dict["quantity"],
            pnl=trade_dict["pnl"],
            strategy=trade_dict["strategy"],
            commission=trade_dict.get("commission", 0.0)
        )
    
    def get_net_pnl(self) -> float:
        """Calculate net P&L after commissions."""
        return self.pnl - self.commission
    
    def get_return_pct(self) -> float:
        """Calculate return percentage."""
        if self.entry_price == 0:
            return 0.0
        return ((self.exit_price - self.entry_price) / self.entry_price) * 100.0
    
    def get_hold_time_hours(self) -> float:
        """Calculate hold time in hours."""
        delta = self.exit_time - self.entry_time
        return delta.total_seconds() / 3600.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "strategy": self.strategy,
            "commission": self.commission
        }


@dataclass
class AttributionBreakdown:
    """
    Breakdown of attribution by a specific metric.
    
    Attributes:
        metric: The attribution metric type
        attributions: Dict mapping keys to P&L contributions
    """
    metric: AttributionMetric
    attributions: Dict[str, float] = field(default_factory=dict)
    
    def add_attribution(self, key: str, pnl: float) -> None:
        """Add P&L attribution for a key."""
        if key not in self.attributions:
            self.attributions[key] = 0.0
        self.attributions[key] += pnl
        
        logger.debug(f"Added {pnl:.2f} to {self.metric.value}:{key}, total: {self.attributions[key]:.2f}")
    
    def get_attribution(self, key: str) -> float:
        """Get P&L attribution for a key."""
        return self.attributions.get(key, 0.0)
    
    def get_total(self) -> float:
        """Get total attribution across all keys."""
        return sum(self.attributions.values())
    
    def get_all_keys(self) -> List[str]:
        """Get all attribution keys."""
        return list(self.attributions.keys())
    
    def get_sorted_by_contribution(self) -> List[Tuple[str, float]]:
        """Get keys sorted by contribution (descending)."""
        return sorted(self.attributions.items(), key=lambda x: x[1], reverse=True)
    
    def get_percentage_contribution(self, key: str) -> float:
        """Get percentage contribution for a key."""
        total = self.get_total()
        if total == 0:
            return 0.0
        
        attribution = self.get_attribution(key)
        return (attribution / total) * 100.0


# ============================================================================
# Performance Attribution Analyzer
# ============================================================================

class PerformanceAttribution:
    """
    Analyzes performance attribution across trades.
    
    Breaks down P&L by strategy, symbol, time period, and other dimensions.
    Identifies top/bottom contributors and calculates win/loss statistics.
    """
    
    def __init__(self):
        """Initialize performance attribution analyzer."""
        self.trades: List[TradeAttribution] = []
        
        logger.info("PerformanceAttribution initialized")
    
    def add_trade(self, trade_dict: Dict) -> None:
        """
        Add a trade for attribution analysis.
        
        Args:
            trade_dict: Trade data dictionary
        """
        trade = TradeAttribution.from_dict(trade_dict)
        self.trades.append(trade)
        
        logger.debug(f"Added trade: {trade.symbol} {trade.strategy} P&L={trade.pnl:.2f}")
    
    def get_total_pnl(self) -> float:
        """Calculate total P&L across all trades."""
        return sum(trade.pnl for trade in self.trades)
    
    def get_attribution_by(self, metric: AttributionMetric) -> AttributionBreakdown:
        """
        Get attribution breakdown by specified metric.
        
        Args:
            metric: The attribution metric to use
        
        Returns:
            AttributionBreakdown for the specified metric
        """
        breakdown = AttributionBreakdown(metric=metric)
        
        for trade in self.trades:
            if metric == AttributionMetric.STRATEGY:
                key = trade.strategy
            elif metric == AttributionMetric.SYMBOL:
                key = trade.symbol
            elif metric == AttributionMetric.DATE:
                key = trade.exit_time.strftime("%Y-%m-%d")
            elif metric == AttributionMetric.HOUR:
                key = str(trade.exit_time.hour)
            elif metric == AttributionMetric.DAY_OF_WEEK:
                key = trade.exit_time.strftime("%A")
            else:
                logger.warning(f"Unknown attribution metric: {metric}")
                continue
            
            breakdown.add_attribution(key, trade.pnl)
        
        logger.info(f"Generated {metric.value} breakdown: {len(breakdown.get_all_keys())} keys, total P&L={breakdown.get_total():.2f}")
        return breakdown
    
    def get_winning_trades(self) -> List[TradeAttribution]:
        """Get all winning trades."""
        return [trade for trade in self.trades if trade.pnl > 0]
    
    def get_losing_trades(self) -> List[TradeAttribution]:
        """Get all losing trades."""
        return [trade for trade in self.trades if trade.pnl < 0]
    
    def get_average_winner(self) -> float:
        """Calculate average winning trade P&L."""
        winners = self.get_winning_trades()
        if not winners:
            return 0.0
        return sum(trade.pnl for trade in winners) / len(winners)
    
    def get_average_loser(self) -> float:
        """Calculate average losing trade P&L."""
        losers = self.get_losing_trades()
        if not losers:
            return 0.0
        return sum(trade.pnl for trade in losers) / len(losers)
    
    def get_largest_winner(self) -> Optional[TradeAttribution]:
        """Get the largest winning trade."""
        winners = self.get_winning_trades()
        if not winners:
            return None
        return max(winners, key=lambda t: t.pnl)
    
    def get_largest_loser(self) -> Optional[TradeAttribution]:
        """Get the largest losing trade."""
        losers = self.get_losing_trades()
        if not losers:
            return None
        return min(losers, key=lambda t: t.pnl)
    
    def get_win_rate(self) -> float:
        """Calculate win rate (percentage of winning trades)."""
        if not self.trades:
            return 0.0
        
        winners = len(self.get_winning_trades())
        return winners / len(self.trades)
    
    def generate_summary(self) -> str:
        """
        Generate a summary of attribution statistics.
        
        Returns:
            Formatted summary string
        """
        lines = []
        lines.append("=" * 60)
        lines.append("PERFORMANCE ATTRIBUTION SUMMARY")
        lines.append("=" * 60)
        lines.append("")
        
        # Overall stats
        total_pnl = self.get_total_pnl()
        total_trades = len(self.trades)
        win_rate = self.get_win_rate() * 100
        
        lines.append(f"Total P&L:        ${total_pnl:,.2f}")
        lines.append(f"Total Trades:     {total_trades}")
        lines.append(f"Win Rate:         {win_rate:.1f}%")
        lines.append("")
        
        # Win/Loss stats
        winners = self.get_winning_trades()
        losers = self.get_losing_trades()
        
        lines.append(f"Winning Trades:   {len(winners)}")
        lines.append(f"Losing Trades:    {len(losers)}")
        
        if winners:
            avg_winner = self.get_average_winner()
            largest_winner = self.get_largest_winner()
            lines.append(f"Average Winner:   ${avg_winner:,.2f}")
            lines.append(f"Largest Winner:   ${largest_winner.pnl:,.2f} ({largest_winner.symbol})")
        
        if losers:
            avg_loser = self.get_average_loser()
            largest_loser = self.get_largest_loser()
            lines.append(f"Average Loser:    ${avg_loser:,.2f}")
            lines.append(f"Largest Loser:    ${largest_loser.pnl:,.2f} ({largest_loser.symbol})")
        
        lines.append("")
        lines.append("=" * 60)
        
        summary = "\n".join(lines)
        logger.info("Generated performance attribution summary")
        return summary
    
    def generate_breakdown_report(self, metric: AttributionMetric) -> str:
        """
        Generate detailed breakdown report for a metric.
        
        Args:
            metric: The attribution metric to report on
        
        Returns:
            Formatted breakdown report
        """
        breakdown = self.get_attribution_by(metric)
        sorted_items = breakdown.get_sorted_by_contribution()
        
        lines = []
        lines.append("=" * 60)
        lines.append(f"ATTRIBUTION BY {metric.value.upper()}")
        lines.append("=" * 60)
        lines.append("")
        
        total = breakdown.get_total()
        lines.append(f"Total P&L: ${total:,.2f}")
        lines.append("")
        
        # Create table header
        lines.append(f"{'Key':<20} {'P&L':>15} {'% of Total':>12} {'Bar':>10}")
        lines.append("-" * 60)
        
        # Add each contribution
        for key, pnl in sorted_items:
            pct = breakdown.get_percentage_contribution(key)
            
            # Create simple bar chart
            bar_width = int(abs(pct) / 5)  # Scale to max ~20 chars
            if pnl >= 0:
                bar = "+" * bar_width
            else:
                bar = "-" * bar_width
            
            lines.append(f"{key:<20} ${pnl:>13,.2f} {pct:>11.1f}% {bar:>10}")
        
        lines.append("")
        lines.append("=" * 60)
        
        report = "\n".join(lines)
        logger.info(f"Generated {metric.value} breakdown report")
        return report


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    'PerformanceAttribution',
    'AttributionBreakdown',
    'TradeAttribution',
    'AttributionMetric',
    'AttributionPeriod'
]
