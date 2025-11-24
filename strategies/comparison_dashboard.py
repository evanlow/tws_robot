"""
Sprint 3 Task 3: Strategy Comparison Dashboard
Side-by-side strategy comparison, ranking, and visualization.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from decimal import Decimal


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class MetricType(Enum):
    """Classification of metrics."""
    RETURN = "return"
    RISK = "risk"
    RATIO = "ratio"
    TRADE = "trade"
    
    @classmethod
    def classify(cls, metric_name: str) -> 'MetricType':
        """Classify a metric by its name."""
        metric_lower = metric_name.lower()
        
        if "return" in metric_lower or "profit" in metric_lower:
            return cls.RETURN
        elif "drawdown" in metric_lower or "volatility" in metric_lower or "risk" in metric_lower:
            return cls.RISK
        elif "ratio" in metric_lower or "factor" in metric_lower:
            return cls.RATIO
        elif "trade" in metric_lower or "win" in metric_lower or "expectancy" in metric_lower:
            return cls.TRADE
        else:
            return cls.RATIO  # Default


class RankingCriteria(Enum):
    """Criteria for ranking strategies."""
    SHARPE_RATIO = "sharpe_ratio"
    TOTAL_RETURN = "total_return"
    ANNUALIZED_RETURN = "annualized_return"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    SORTINO_RATIO = "sortino_ratio"
    CALMAR_RATIO = "calmar_ratio"
    RISK_ADJUSTED = "risk_adjusted"  # Sharpe / Drawdown
    
    def higher_is_better(self) -> bool:
        """Return True if higher values are better for this criterion."""
        # Only max_drawdown is reverse (lower is better)
        return self != RankingCriteria.MAX_DRAWDOWN


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ComparisonMetrics:
    """Performance metrics for strategy comparison."""
    strategy_name: str
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade: float = 0.0
    expectancy: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    volatility: float = 0.0
    
    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> 'ComparisonMetrics':
        """Create ComparisonMetrics from dictionary."""
        return cls(
            strategy_name=name,
            total_return=data.get("total_return", 0.0),
            annualized_return=data.get("annualized_return", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            win_rate=data.get("win_rate", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            total_trades=data.get("total_trades", 0),
            avg_trade=data.get("avg_trade", 0.0),
            expectancy=data.get("expectancy", 0.0),
            calmar_ratio=data.get("calmar_ratio", 0.0),
            recovery_factor=data.get("recovery_factor", 0.0),
            volatility=data.get("volatility", 0.0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def get_ranking_score(self, criteria: RankingCriteria) -> float:
        """Get score for ranking by specific criteria."""
        if criteria == RankingCriteria.SHARPE_RATIO:
            return self.sharpe_ratio
        elif criteria == RankingCriteria.TOTAL_RETURN:
            return self.total_return
        elif criteria == RankingCriteria.ANNUALIZED_RETURN:
            return self.annualized_return
        elif criteria == RankingCriteria.MAX_DRAWDOWN:
            return self.max_drawdown
        elif criteria == RankingCriteria.WIN_RATE:
            return self.win_rate
        elif criteria == RankingCriteria.PROFIT_FACTOR:
            return self.profit_factor
        elif criteria == RankingCriteria.SORTINO_RATIO:
            return self.sortino_ratio
        elif criteria == RankingCriteria.CALMAR_RATIO:
            return self.calmar_ratio
        elif criteria == RankingCriteria.RISK_ADJUSTED:
            # Risk-adjusted = Sharpe / Drawdown (avoid division by zero)
            if self.max_drawdown > 0:
                return self.sharpe_ratio / self.max_drawdown
            return self.sharpe_ratio
        else:
            return 0.0


# ============================================================================
# Strategy Comparator
# ============================================================================

class StrategyComparator:
    """
    Compares multiple strategy performance metrics side-by-side.
    
    Features:
    - Add/remove strategies with their metrics
    - Rank strategies by various criteria
    - Compare two strategies head-to-head
    - Find best/worst performers
    """
    
    def __init__(self):
        """Initialize the strategy comparator."""
        self._strategies: Dict[str, ComparisonMetrics] = {}
        logger.info("StrategyComparator initialized")
    
    def add_strategy(self, name: str, metrics: Dict[str, Any]) -> None:
        """
        Add or update a strategy's metrics.
        
        Args:
            name: Strategy name
            metrics: Dictionary of performance metrics
        """
        self._strategies[name] = ComparisonMetrics.from_dict(name, metrics)
        logger.info(f"Added strategy '{name}' to comparison")
    
    def remove_strategy(self, name: str) -> bool:
        """
        Remove a strategy from comparison.
        
        Args:
            name: Strategy name to remove
            
        Returns:
            True if strategy was removed, False if not found
        """
        if name in self._strategies:
            del self._strategies[name]
            logger.info(f"Removed strategy '{name}' from comparison")
            return True
        return False
    
    def get_all_strategies(self) -> List[str]:
        """Get list of all strategy names."""
        return list(self._strategies.keys())
    
    def get_strategy_metrics(self, name: str) -> Optional[ComparisonMetrics]:
        """
        Get metrics for a specific strategy.
        
        Args:
            name: Strategy name
            
        Returns:
            ComparisonMetrics or None if not found
        """
        return self._strategies.get(name)
    
    def rank_strategies(
        self,
        criteria: RankingCriteria = RankingCriteria.SHARPE_RATIO
    ) -> List[Tuple[str, float]]:
        """
        Rank all strategies by specified criteria.
        
        Args:
            criteria: Ranking criterion to use
            
        Returns:
            List of (strategy_name, score) tuples, sorted best to worst
        """
        if not self._strategies:
            return []
        
        # Get scores for all strategies
        scores = [
            (name, metrics.get_ranking_score(criteria))
            for name, metrics in self._strategies.items()
        ]
        
        # Sort by score (reverse for higher-is-better, normal for lower-is-better)
        reverse = criteria.higher_is_better()
        scores.sort(key=lambda x: x[1], reverse=reverse)
        
        logger.info(
            f"Ranked {len(scores)} strategies by {criteria.value}: "
            f"Best = {scores[0][0]} ({scores[0][1]:.2f})"
        )
        
        return scores
    
    def compare_strategies(
        self,
        strategy1: str,
        strategy2: str
    ) -> Optional[Dict[str, Any]]:
        """
        Compare two strategies head-to-head.
        
        Args:
            strategy1: First strategy name
            strategy2: Second strategy name
            
        Returns:
            Dictionary with comparison results, or None if either strategy not found
        """
        metrics1 = self.get_strategy_metrics(strategy1)
        metrics2 = self.get_strategy_metrics(strategy2)
        
        if not metrics1 or not metrics2:
            logger.warning(f"Cannot compare: one or both strategies not found")
            return None
        
        # Calculate differences (strategy1 - strategy2)
        differences = {
            "total_return": metrics1.total_return - metrics2.total_return,
            "sharpe_ratio": metrics1.sharpe_ratio - metrics2.sharpe_ratio,
            "max_drawdown": metrics1.max_drawdown - metrics2.max_drawdown,
            "win_rate": metrics1.win_rate - metrics2.win_rate,
            "profit_factor": metrics1.profit_factor - metrics2.profit_factor,
            "total_trades": metrics1.total_trades - metrics2.total_trades,
            "volatility": metrics1.volatility - metrics2.volatility
        }
        
        comparison = {
            strategy1: metrics1.to_dict(),
            strategy2: metrics2.to_dict(),
            "differences": differences
        }
        
        logger.info(f"Compared '{strategy1}' vs '{strategy2}'")
        
        return comparison
    
    def get_best_strategy(
        self,
        criteria: RankingCriteria = RankingCriteria.SHARPE_RATIO
    ) -> Optional[str]:
        """
        Get the best performing strategy by specified criteria.
        
        Args:
            criteria: Ranking criterion
            
        Returns:
            Strategy name or None if no strategies
        """
        ranked = self.rank_strategies(criteria)
        if ranked:
            return ranked[0][0]
        return None
    
    def get_worst_strategy(
        self,
        criteria: RankingCriteria = RankingCriteria.SHARPE_RATIO
    ) -> Optional[str]:
        """
        Get the worst performing strategy by specified criteria.
        
        Args:
            criteria: Ranking criterion
            
        Returns:
            Strategy name or None if no strategies
        """
        ranked = self.rank_strategies(criteria)
        if ranked:
            return ranked[-1][0]
        return None


# ============================================================================
# Comparison Dashboard
# ============================================================================

class ComparisonDashboard:
    """
    Visualization and reporting for strategy comparison.
    
    Features:
    - Summary tables with all metrics
    - Ranking tables by different criteria
    - Sparkline visualizations
    - Risk-return scatter plots
    - Full dashboard generation
    """
    
    def __init__(self, comparator: Optional[StrategyComparator] = None):
        """
        Initialize the comparison dashboard.
        
        Args:
            comparator: Optional existing StrategyComparator to use
        """
        self.comparator = comparator or StrategyComparator()
        logger.info("ComparisonDashboard initialized")
    
    def generate_summary_table(self) -> str:
        """
        Generate a summary table of all strategies.
        
        Returns:
            Formatted table string
        """
        strategies = self.comparator.get_all_strategies()
        
        if not strategies:
            return "No strategies to display"
        
        # Build header
        lines = ["Strategy Comparison Summary", "=" * 80, ""]
        lines.append(f"{'Strategy':<20} {'Return%':<10} {'Sharpe':<8} {'DD%':<8} {'Win%':<8} {'Trades':<8}")
        lines.append("-" * 80)
        
        # Add each strategy
        for name in strategies:
            metrics = self.comparator.get_strategy_metrics(name)
            if metrics:
                lines.append(
                    f"{name:<20} "
                    f"{metrics.total_return:>9.2f} "
                    f"{metrics.sharpe_ratio:>7.2f} "
                    f"{metrics.max_drawdown:>7.2f} "
                    f"{metrics.win_rate * 100:>7.1f} "
                    f"{metrics.total_trades:>7d}"
                )
        
        return "\n".join(lines)
    
    def generate_ranking_table(
        self,
        criteria: RankingCriteria = RankingCriteria.SHARPE_RATIO
    ) -> str:
        """
        Generate a ranking table by specified criteria.
        
        Args:
            criteria: Ranking criterion
            
        Returns:
            Formatted table string
        """
        ranked = self.comparator.rank_strategies(criteria)
        
        if not ranked:
            return "No strategies to rank"
        
        lines = [f"Strategy Rankings by {criteria.value.replace('_', ' ').title()}", "=" * 60, ""]
        lines.append(f"{'Rank':<6} {'Strategy':<25} {'Score':<15}")
        lines.append("-" * 60)
        
        for i, (name, score) in enumerate(ranked, 1):
            lines.append(f"#{i:<5} {name:<25} {score:>14.2f}")
        
        return "\n".join(lines)
    
    def generate_metric_comparison(self, metric_name: str) -> Dict[str, float]:
        """
        Compare a specific metric across all strategies.
        
        Args:
            metric_name: Name of metric to compare
            
        Returns:
            Dictionary mapping strategy names to metric values
        """
        comparison = {}
        
        for name in self.comparator.get_all_strategies():
            metrics = self.comparator.get_strategy_metrics(name)
            if metrics:
                value = getattr(metrics, metric_name, None)
                if value is not None:
                    comparison[name] = value
        
        return comparison
    
    def generate_sparkline(
        self,
        data: List[float],
        width: int = 20
    ) -> str:
        """
        Generate a sparkline visualization.
        
        Args:
            data: List of values
            width: Maximum width of sparkline
            
        Returns:
            Sparkline string using Unicode block characters
        """
        if not data:
            return ""
        
        if len(data) == 1:
            return "▄"
        
        # Sample data if too long
        if len(data) > width:
            step = len(data) / width
            sampled = [data[int(i * step)] for i in range(width)]
            data = sampled
        
        # Normalize to 0-7 range for 8 levels of blocks
        min_val = min(data)
        max_val = max(data)
        
        if max_val == min_val:
            return "▄" * len(data)
        
        blocks = "▁▂▃▄▅▆▇█"
        normalized = [
            int((val - min_val) / (max_val - min_val) * 7)
            for val in data
        ]
        
        return "".join(blocks[n] for n in normalized)
    
    def generate_performance_chart(self) -> str:
        """
        Generate a text-based performance comparison chart.
        
        Returns:
            Formatted chart string
        """
        strategies = self.comparator.get_all_strategies()
        
        if not strategies:
            return "No strategies to chart"
        
        lines = ["Performance Comparison", "=" * 80, ""]
        
        # Get metrics for bar chart
        returns = []
        sharpes = []
        for name in strategies:
            metrics = self.comparator.get_strategy_metrics(name)
            if metrics:
                returns.append((name, metrics.total_return))
                sharpes.append((name, metrics.sharpe_ratio))
        
        # Return chart
        lines.append("Total Return (%)")
        lines.append("-" * 80)
        max_return = max(r[1] for r in returns) if returns else 1
        for name, ret in sorted(returns, key=lambda x: x[1], reverse=True):
            bar_length = int((ret / max_return) * 50) if max_return > 0 else 0
            bar = "█" * bar_length
            lines.append(f"{name:<20} {bar} {ret:>6.2f}%")
        
        lines.append("")
        
        # Sharpe chart
        lines.append("Sharpe Ratio")
        lines.append("-" * 80)
        max_sharpe = max(s[1] for s in sharpes) if sharpes else 1
        for name, sharpe in sorted(sharpes, key=lambda x: x[1], reverse=True):
            bar_length = int((sharpe / max_sharpe) * 50) if max_sharpe > 0 else 0
            bar = "█" * bar_length
            lines.append(f"{name:<20} {bar} {sharpe:>5.2f}")
        
        return "\n".join(lines)
    
    def generate_risk_return_scatter(self) -> str:
        """
        Generate a text-based risk-return scatter plot.
        
        Returns:
            Formatted scatter plot string
        """
        strategies = self.comparator.get_all_strategies()
        
        if not strategies:
            return "No strategies to plot"
        
        lines = ["Risk-Return Profile", "=" * 80, ""]
        lines.append(f"{'Strategy':<20} {'Return%':<12} {'Risk (Vol%)':<12} {'Sharpe':<8}")
        lines.append("-" * 80)
        
        for name in strategies:
            metrics = self.comparator.get_strategy_metrics(name)
            if metrics:
                # Use volatility as risk measure
                risk = metrics.volatility
                ret = metrics.total_return
                sharpe = metrics.sharpe_ratio
                
                lines.append(
                    f"{name:<20} "
                    f"{ret:>11.2f} "
                    f"{risk:>11.2f} "
                    f"{sharpe:>7.2f}"
                )
        
        return "\n".join(lines)
    
    def generate_dashboard(self) -> str:
        """
        Generate complete comparison dashboard.
        
        Returns:
            Full dashboard output string
        """
        if not self.comparator.get_all_strategies():
            return "No strategies available for comparison"
        
        sections = [
            "=" * 80,
            "STRATEGY COMPARISON DASHBOARD",
            "=" * 80,
            "",
            self.generate_summary_table(),
            "",
            self.generate_performance_chart(),
            "",
            self.generate_risk_return_scatter(),
            "",
            self.generate_ranking_table(RankingCriteria.SHARPE_RATIO),
            "",
            "=" * 80
        ]
        
        dashboard = "\n".join(sections)
        logger.info("Generated full comparison dashboard")
        
        return dashboard
