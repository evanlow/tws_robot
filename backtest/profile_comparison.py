"""
Profile Comparison Framework for Backtesting

This module provides tools for comparing multiple risk profiles
through side-by-side backtesting and performance analysis.

Features:
- Multi-profile backtest execution
- Side-by-side performance comparison
- Statistical analysis and rankings
- Visualization of comparison results
- Profile optimization recommendations

Author: Trading Bot Team
Week 4 Day 5
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import statistics

from backtest.profiles import RiskProfile, ProfileManager
from backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from backtest.strategy import Strategy
from backtest.performance import PerformanceMetrics, PerformanceAnalyzer


@dataclass
class ProfileComparisonResult:
    """
    Results from comparing multiple risk profiles
    
    Contains:
    - Individual backtest results for each profile
    - Comparative metrics
    - Rankings
    - Statistical analysis
    """
    
    # Profile results
    profile_results: Dict[str, BacktestResult] = field(default_factory=dict)
    
    # Comparison timestamp
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Backtest parameters
    start_date: str = ""
    end_date: str = ""
    symbols: List[str] = field(default_factory=list)
    initial_capital: float = 100000.0
    
    # Rankings (profile_name -> rank)
    sharpe_ranking: Dict[str, int] = field(default_factory=dict)
    return_ranking: Dict[str, int] = field(default_factory=dict)
    drawdown_ranking: Dict[str, int] = field(default_factory=dict)
    winrate_ranking: Dict[str, int] = field(default_factory=dict)
    
    # Statistical summary
    summary_stats: Dict[str, Any] = field(default_factory=dict)
    
    def get_best_profile(self, metric: str = "sharpe") -> Optional[str]:
        """
        Get the best performing profile by specified metric
        
        Args:
            metric: Metric to use ('sharpe', 'return', 'drawdown', 'winrate')
            
        Returns:
            Profile name with best performance, None if no results
        """
        if not self.profile_results:
            return None
        
        ranking_map = {
            'sharpe': self.sharpe_ranking,
            'return': self.return_ranking,
            'drawdown': self.drawdown_ranking,
            'winrate': self.winrate_ranking
        }
        
        ranking = ranking_map.get(metric.lower())
        if not ranking:
            return None
        
        # Find profile with rank 1
        for profile, rank in ranking.items():
            if rank == 1:
                return profile
        
        return None
    
    def get_profile_metrics(self, profile_name: str) -> Optional[PerformanceMetrics]:
        """Get performance metrics for a specific profile"""
        result = self.profile_results.get(profile_name)
        if result:
            return result.metrics
        return None
    
    def get_comparison_table(self) -> Dict[str, Dict[str, Any]]:
        """
        Generate comparison table with key metrics
        
        Returns:
            Dictionary mapping profile names to their metrics
        """
        table = {}
        
        for profile_name, result in self.profile_results.items():
            if result.metrics:
                table[profile_name] = {
                    'total_return': result.metrics.total_return,
                    'sharpe_ratio': result.metrics.sharpe_ratio,
                    'sortino_ratio': result.metrics.sortino_ratio,
                    'max_drawdown': result.metrics.max_drawdown,
                    'win_rate': result.metrics.win_rate,
                    'profit_factor': result.metrics.profit_factor,
                    'total_trades': result.metrics.total_trades,
                    'sharpe_rank': self.sharpe_ranking.get(profile_name, 0),
                    'return_rank': self.return_ranking.get(profile_name, 0),
                    'drawdown_rank': self.drawdown_ranking.get(profile_name, 0),
                    'winrate_rank': self.winrate_ranking.get(profile_name, 0)
                }
        
        return table


class ProfileComparator:
    """
    Compare multiple risk profiles through backtesting
    
    Responsibilities:
    - Execute backtests with different profiles
    - Compare performance metrics
    - Generate rankings
    - Provide optimization insights
    """
    
    def __init__(self, profile_manager: Optional[ProfileManager] = None):
        """
        Initialize profile comparator
        
        Args:
            profile_manager: ProfileManager instance (creates new if None)
        """
        self.profile_manager = profile_manager or ProfileManager()
        self.comparison_results: List[ProfileComparisonResult] = []
    
    def compare_profiles(
        self,
        strategy_class: type,
        profile_names: List[str],
        start_date: str,
        end_date: str,
        symbols: List[str],
        initial_capital: float = 100000.0,
        strategy_params: Optional[Dict[str, Any]] = None
    ) -> ProfileComparisonResult:
        """
        Compare multiple profiles by running backtests
        
        Args:
            strategy_class: Strategy class to instantiate
            profile_names: List of profile names to compare
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            symbols: List of symbols to trade
            initial_capital: Starting capital
            strategy_params: Additional strategy parameters
            
        Returns:
            ProfileComparisonResult with comparative analysis
        """
        if not profile_names:
            raise ValueError("Must provide at least one profile name")
        
        # Initialize result
        result = ProfileComparisonResult(
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            initial_capital=initial_capital
        )
        
        # Run backtest for each profile
        for profile_name in profile_names:
            profile = self.profile_manager.get_profile(profile_name)
            
            if not profile:
                print(f"Warning: Profile '{profile_name}' not found, skipping")
                continue
            
            # Create strategy instance with profile
            strategy_params_with_profile = strategy_params or {}
            strategy_params_with_profile['profile'] = profile
            
            strategy = strategy_class(**strategy_params_with_profile)
            
            # Configure and run backtest
            config = BacktestConfig(
                strategy=strategy,
                start_date=start_date,
                end_date=end_date,
                symbols=symbols
            )
            
            engine = BacktestEngine(config)
            backtest_result = engine.run()
            
            # Store result
            result.profile_results[profile_name] = backtest_result
        
        # Calculate rankings
        self._calculate_rankings(result)
        
        # Calculate summary statistics
        self._calculate_summary_stats(result)
        
        # Store for history
        self.comparison_results.append(result)
        
        return result
    
    def _calculate_rankings(self, result: ProfileComparisonResult) -> None:
        """Calculate rankings for each metric"""
        if not result.profile_results:
            return
        
        # Extract metrics for ranking
        sharpe_values = {}
        return_values = {}
        drawdown_values = {}
        winrate_values = {}
        
        for profile_name, backtest_result in result.profile_results.items():
            metrics = backtest_result.metrics
            if metrics:
                sharpe_values[profile_name] = metrics.sharpe_ratio or -999
                return_values[profile_name] = metrics.total_return
                drawdown_values[profile_name] = metrics.max_drawdown  # Lower is better
                winrate_values[profile_name] = metrics.win_rate
        
        # Calculate rankings (1 = best)
        result.sharpe_ranking = self._rank_values(sharpe_values, higher_is_better=True)
        result.return_ranking = self._rank_values(return_values, higher_is_better=True)
        result.drawdown_ranking = self._rank_values(drawdown_values, higher_is_better=False)
        result.winrate_ranking = self._rank_values(winrate_values, higher_is_better=True)
    
    def _rank_values(
        self,
        values: Dict[str, float],
        higher_is_better: bool = True
    ) -> Dict[str, int]:
        """
        Rank values
        
        Args:
            values: Dictionary of profile_name -> value
            higher_is_better: True if higher values are better
            
        Returns:
            Dictionary of profile_name -> rank (1 = best)
        """
        if not values:
            return {}
        
        # Sort by value
        sorted_items = sorted(
            values.items(),
            key=lambda x: x[1],
            reverse=higher_is_better
        )
        
        # Assign ranks
        rankings = {}
        for rank, (profile_name, _) in enumerate(sorted_items, start=1):
            rankings[profile_name] = rank
        
        return rankings
    
    def _calculate_summary_stats(self, result: ProfileComparisonResult) -> None:
        """Calculate summary statistics across all profiles"""
        if not result.profile_results:
            return
        
        # Collect metrics
        sharpe_ratios = []
        total_returns = []
        max_drawdowns = []
        win_rates = []
        
        for backtest_result in result.profile_results.values():
            metrics = backtest_result.metrics
            if metrics:
                if metrics.sharpe_ratio is not None:
                    sharpe_ratios.append(metrics.sharpe_ratio)
                total_returns.append(metrics.total_return)
                max_drawdowns.append(metrics.max_drawdown)
                win_rates.append(metrics.win_rate)
        
        # Calculate statistics
        result.summary_stats = {
            'num_profiles': len(result.profile_results),
            'sharpe_mean': statistics.mean(sharpe_ratios) if sharpe_ratios else 0.0,
            'sharpe_std': statistics.stdev(sharpe_ratios) if len(sharpe_ratios) > 1 else 0.0,
            'return_mean': statistics.mean(total_returns) if total_returns else 0.0,
            'return_std': statistics.stdev(total_returns) if len(total_returns) > 1 else 0.0,
            'drawdown_mean': statistics.mean(max_drawdowns) if max_drawdowns else 0.0,
            'drawdown_std': statistics.stdev(max_drawdowns) if len(max_drawdowns) > 1 else 0.0,
            'winrate_mean': statistics.mean(win_rates) if win_rates else 0.0,
            'winrate_std': statistics.stdev(win_rates) if len(win_rates) > 1 else 0.0
        }
    
    def print_comparison(self, result: ProfileComparisonResult) -> None:
        """
        Print formatted comparison results
        
        Args:
            result: ProfileComparisonResult to display
        """
        print("=" * 80)
        print("PROFILE COMPARISON RESULTS")
        print("=" * 80)
        print(f"Period: {result.start_date} to {result.end_date}")
        print(f"Symbols: {', '.join(result.symbols)}")
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Profiles Compared: {len(result.profile_results)}")
        print()
        
        # Comparison table
        table = result.get_comparison_table()
        
        if not table:
            print("No results to display")
            return
        
        # Print header
        print(f"{'Profile':<20} {'Return':<10} {'Sharpe':<8} {'MaxDD':<8} {'Win%':<8} {'Trades':<8} {'Ranks (S/R/D/W)':<18}")
        print("-" * 80)
        
        # Print each profile
        for profile_name in sorted(table.keys()):
            metrics = table[profile_name]
            
            return_str = f"{metrics['total_return']*100:>6.2f}%"
            sharpe_str = f"{metrics['sharpe_ratio']:>6.2f}" if metrics['sharpe_ratio'] else "N/A"
            drawdown_str = f"{metrics['max_drawdown']*100:>6.2f}%"
            winrate_str = f"{metrics['win_rate']*100:>6.2f}%"
            trades_str = f"{metrics['total_trades']:>6}"
            ranks_str = f"{metrics['sharpe_rank']}/{metrics['return_rank']}/{metrics['drawdown_rank']}/{metrics['winrate_rank']}"
            
            print(f"{profile_name:<20} {return_str:<10} {sharpe_str:<8} {drawdown_str:<8} {winrate_str:<8} {trades_str:<8} {ranks_str:<18}")
        
        print()
        
        # Best performers
        print("Best Performers:")
        print(f"  Sharpe Ratio: {result.get_best_profile('sharpe')}")
        print(f"  Total Return: {result.get_best_profile('return')}")
        print(f"  Max Drawdown: {result.get_best_profile('drawdown')}")
        print(f"  Win Rate: {result.get_best_profile('winrate')}")
        print()
        
        # Summary statistics
        print("Summary Statistics:")
        stats = result.summary_stats
        print(f"  Average Sharpe Ratio: {stats.get('sharpe_mean', 0):.2f} (±{stats.get('sharpe_std', 0):.2f})")
        print(f"  Average Return: {stats.get('return_mean', 0)*100:.2f}% (±{stats.get('return_std', 0)*100:.2f}%)")
        print(f"  Average Max Drawdown: {stats.get('drawdown_mean', 0)*100:.2f}% (±{stats.get('drawdown_std', 0)*100:.2f}%)")
        print(f"  Average Win Rate: {stats.get('winrate_mean', 0)*100:.2f}% (±{stats.get('winrate_std', 0)*100:.2f}%)")
        print("=" * 80)
    
    def get_optimization_insights(
        self,
        result: ProfileComparisonResult
    ) -> List[str]:
        """
        Generate optimization insights based on comparison
        
        Args:
            result: ProfileComparisonResult to analyze
            
        Returns:
            List of insight strings
        """
        insights = []
        
        if not result.profile_results:
            return ["No results available for analysis"]
        
        # Get best profiles
        best_sharpe = result.get_best_profile('sharpe')
        best_return = result.get_best_profile('return')
        best_drawdown = result.get_best_profile('drawdown')
        best_winrate = result.get_best_profile('winrate')
        
        # Overall winner
        if best_sharpe == best_return == best_drawdown:
            insights.append(f"🏆 '{best_sharpe}' dominates across all metrics")
        else:
            insights.append(f"📊 Different profiles excel in different metrics")
        
        # Risk-adjusted performance
        if best_sharpe:
            best_sharpe_metrics = result.get_profile_metrics(best_sharpe)
            if best_sharpe_metrics:
                insights.append(
                    f"✅ '{best_sharpe}' has best risk-adjusted returns "
                    f"(Sharpe: {best_sharpe_metrics.sharpe_ratio:.2f})"
                )
        
        # Return analysis
        if best_return:
            best_return_metrics = result.get_profile_metrics(best_return)
            if best_return_metrics:
                insights.append(
                    f"💰 '{best_return}' has highest returns "
                    f"({best_return_metrics.total_return*100:.2f}%)"
                )
        
        # Drawdown analysis
        if best_drawdown:
            best_dd_metrics = result.get_profile_metrics(best_drawdown)
            if best_dd_metrics:
                insights.append(
                    f"🛡️ '{best_drawdown}' has lowest drawdown "
                    f"({best_dd_metrics.max_drawdown*100:.2f}%)"
                )
        
        # Consistency analysis
        stats = result.summary_stats
        if stats.get('sharpe_std', 0) < 0.5:
            insights.append("📈 Consistent performance across profiles")
        else:
            insights.append("⚠️ High variance in performance across profiles")
        
        # Trade frequency
        avg_trades = statistics.mean([
            r.metrics.total_trades for r in result.profile_results.values()
            if r.metrics
        ]) if result.profile_results else 0
        
        if avg_trades < 10:
            insights.append("⚠️ Low trade frequency - consider longer backtest period")
        elif avg_trades > 100:
            insights.append("📊 High trade frequency - suitable for active strategies")
        
        return insights
    
    def compare_two_profiles(
        self,
        profile1_name: str,
        profile2_name: str,
        result: ProfileComparisonResult
    ) -> Dict[str, Any]:
        """
        Detailed comparison of two specific profiles
        
        Args:
            profile1_name: First profile name
            profile2_name: Second profile name
            result: ProfileComparisonResult containing both profiles
            
        Returns:
            Dictionary with detailed comparison
        """
        metrics1 = result.get_profile_metrics(profile1_name)
        metrics2 = result.get_profile_metrics(profile2_name)
        
        if not metrics1 or not metrics2:
            return {'error': 'One or both profiles not found in results'}
        
        comparison = {
            'profile1': profile1_name,
            'profile2': profile2_name,
            'metrics': {
                'total_return': {
                    profile1_name: metrics1.total_return,
                    profile2_name: metrics2.total_return,
                    'difference': metrics1.total_return - metrics2.total_return,
                    'winner': profile1_name if metrics1.total_return > metrics2.total_return else profile2_name
                },
                'sharpe_ratio': {
                    profile1_name: metrics1.sharpe_ratio,
                    profile2_name: metrics2.sharpe_ratio,
                    'difference': (metrics1.sharpe_ratio or 0) - (metrics2.sharpe_ratio or 0),
                    'winner': profile1_name if (metrics1.sharpe_ratio or 0) > (metrics2.sharpe_ratio or 0) else profile2_name
                },
                'max_drawdown': {
                    profile1_name: metrics1.max_drawdown,
                    profile2_name: metrics2.max_drawdown,
                    'difference': metrics1.max_drawdown - metrics2.max_drawdown,
                    'winner': profile1_name if metrics1.max_drawdown < metrics2.max_drawdown else profile2_name
                },
                'win_rate': {
                    profile1_name: metrics1.win_rate,
                    profile2_name: metrics2.win_rate,
                    'difference': metrics1.win_rate - metrics2.win_rate,
                    'winner': profile1_name if metrics1.win_rate > metrics2.win_rate else profile2_name
                }
            }
        }
        
        return comparison
