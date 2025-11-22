"""
Strategy parameter optimization for backtest results.

Provides grid search, walk-forward optimization, and parameter sensitivity
analysis to find optimal strategy parameters.
"""

import logging
import itertools
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from backtesting import HistoricalDataManager, BacktestEngine, RiskManager
from strategies.base_strategy import StrategyState

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Results from a single parameter combination"""
    parameters: Dict[str, Any]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    profit_factor: float
    calmar_ratio: float
    sortino_ratio: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            **self.parameters,
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'total_trades': self.total_trades,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'calmar_ratio': self.calmar_ratio,
            'sortino_ratio': self.sortino_ratio
        }


class StrategyOptimizer:
    """
    Optimize strategy parameters through systematic testing.
    
    Features:
    - Grid search across parameter combinations
    - Walk-forward optimization
    - Parameter sensitivity analysis
    - Visual parameter heat maps
    
    Example:
        >>> optimizer = StrategyOptimizer()
        >>> parameter_grid = {
        ...     'period': [10, 20, 30],
        ...     'std_dev': [1.5, 2.0, 2.5]
        ... }
        >>> results = optimizer.grid_search(
        ...     strategy_class=BollingerBandsStrategy,
        ...     parameter_grid=parameter_grid,
        ...     symbols=['AAPL', 'MSFT'],
        ...     days=180
        ... )
        >>> best = optimizer.find_optimal_parameters(results, metric='sharpe_ratio')
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.001
    ):
        """
        Initialize optimizer.
        
        Args:
            initial_capital: Starting capital for backtests
            commission: Commission rate (0.001 = 0.1%)
            slippage: Slippage rate (0.001 = 0.1%)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.data_manager = HistoricalDataManager()
        logger.debug("StrategyOptimizer initialized")
    
    def grid_search(
        self,
        strategy_class: type,
        parameter_grid: Dict[str, List[Any]],
        symbols: List[str],
        days: int = 180,
        strategy_name: str = "strategy"
    ) -> List[OptimizationResult]:
        """
        Perform grid search over parameter combinations.
        
        Args:
            strategy_class: Strategy class to optimize
            parameter_grid: Dict of parameter names to lists of values
            symbols: Symbols to test
            days: Number of days to backtest
            strategy_name: Name for the strategy
            
        Returns:
            List of OptimizationResult objects
        """
        # Generate all parameter combinations
        param_names = list(parameter_grid.keys())
        param_values = list(parameter_grid.values())
        combinations = list(itertools.product(*param_values))
        
        total_tests = len(combinations)
        logger.info(f"Starting grid search with {total_tests} parameter combinations")
        logger.info(f"Testing on {len(symbols)} symbols over {days} days")
        
        results = []
        
        for i, combo in enumerate(combinations, 1):
            params = dict(zip(param_names, combo))
            
            logger.info(f"\n[{i}/{total_tests}] Testing parameters: {params}")
            
            # Run backtest with these parameters
            result = self._run_single_backtest(
                strategy_class=strategy_class,
                strategy_name=strategy_name,
                symbols=symbols,
                days=days,
                strategy_params=params
            )
            
            if result:
                results.append(result)
                logger.info(
                    f"  Return: {result.total_return:.2f}%, "
                    f"Sharpe: {result.sharpe_ratio:.2f}, "
                    f"DD: {result.max_drawdown:.2f}%"
                )
        
        logger.info(f"\nGrid search complete. Tested {len(results)} combinations")
        
        return results
    
    def _run_single_backtest(
        self,
        strategy_class: type,
        strategy_name: str,
        symbols: List[str],
        days: int,
        strategy_params: Dict[str, Any]
    ) -> Optional[OptimizationResult]:
        """
        Run a single backtest with given parameters.
        
        Args:
            strategy_class: Strategy class
            strategy_name: Strategy name
            symbols: Symbols to trade
            days: Number of days
            strategy_params: Strategy parameters
            
        Returns:
            OptimizationResult or None if backtest failed
        """
        try:
            # Create strategy instance
            strategy = strategy_class(
                name=strategy_name,
                symbols=symbols,
                **strategy_params
            )
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Aggregate results across all symbols
            all_returns = []
            all_sharpe = []
            all_drawdown = []
            all_trades = 0
            all_win_rates = []
            all_profit_factors = []
            all_calmar = []
            all_sortino = []
            
            for symbol in symbols:
                # Get historical data
                bars = self.data_manager.get_historical_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if not bars:
                    continue
                
                # Create fresh engine for each symbol
                strategy.reset()
                strategy.state = StrategyState.READY
                
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    commission=self.commission,
                    slippage=self.slippage
                )
                
                # Run backtest
                results = engine.run(strategy, symbol, bars)
                
                # Collect metrics
                if results.metrics:
                    all_returns.append(results.total_return_percent)
                    all_sharpe.append(results.metrics.get('sharpe_ratio', 0))
                    all_drawdown.append(results.metrics.get('max_drawdown_pct', 0))
                    all_trades += results.total_trades
                    all_win_rates.append(results.metrics.get('win_rate_pct', 0))
                    all_profit_factors.append(results.metrics.get('profit_factor', 0))
                    all_calmar.append(results.metrics.get('calmar_ratio', 0))
                    all_sortino.append(results.metrics.get('sortino_ratio', 0))
            
            # Calculate averages
            if not all_returns:
                return None
            
            import numpy as np
            
            return OptimizationResult(
                parameters=strategy_params,
                total_return=np.mean(all_returns),
                sharpe_ratio=np.mean(all_sharpe),
                max_drawdown=np.mean(all_drawdown),
                total_trades=all_trades,
                win_rate=np.mean(all_win_rates),
                profit_factor=np.mean(all_profit_factors),
                calmar_ratio=np.mean(all_calmar),
                sortino_ratio=np.mean(all_sortino)
            )
            
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            return None
    
    def find_optimal_parameters(
        self,
        results: List[OptimizationResult],
        metric: str = 'sharpe_ratio',
        ascending: bool = False
    ) -> Optional[OptimizationResult]:
        """
        Find best parameter combination based on a metric.
        
        Args:
            results: List of OptimizationResults
            metric: Metric to optimize ('sharpe_ratio', 'total_return', 'calmar_ratio', etc.)
            ascending: Whether lower is better (e.g., for drawdown)
            
        Returns:
            OptimizationResult with best parameters
        """
        if not results:
            logger.warning("No results to optimize")
            return None
        
        # Sort by metric
        sorted_results = sorted(
            results,
            key=lambda x: getattr(x, metric),
            reverse=not ascending
        )
        
        best = sorted_results[0]
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Optimal Parameters (by {metric})")
        logger.info(f"{'='*60}")
        logger.info(f"Parameters: {best.parameters}")
        logger.info(f"Total Return: {best.total_return:.2f}%")
        logger.info(f"Sharpe Ratio: {best.sharpe_ratio:.2f}")
        logger.info(f"Max Drawdown: {best.max_drawdown:.2f}%")
        logger.info(f"Win Rate: {best.win_rate:.2f}%")
        logger.info(f"Profit Factor: {best.profit_factor:.2f}")
        logger.info(f"{'='*60}\n")
        
        return best
    
    def plot_parameter_sensitivity(
        self,
        results: List[OptimizationResult],
        x_param: str,
        y_param: str,
        metric: str = 'sharpe_ratio',
        save_path: Optional[str] = None,
        show: bool = False
    ) -> Optional[str]:
        """
        Plot 2D heatmap of parameter sensitivity.
        
        Args:
            results: List of OptimizationResults
            x_param: Parameter for x-axis
            y_param: Parameter for y-axis
            metric: Metric to visualize
            save_path: Path to save figure
            show: Whether to display plot
            
        Returns:
            Path where figure was saved
        """
        if not results:
            logger.warning("No results to plot")
            return None
        
        # Convert to DataFrame
        data = [r.to_dict() for r in results]
        df = pd.DataFrame(data)
        
        # Create pivot table
        pivot = df.pivot(index=y_param, columns=x_param, values=metric)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Create heatmap
        sns.heatmap(
            pivot,
            annot=True,
            fmt='.2f',
            cmap='RdYlGn',
            center=0 if metric in ['total_return', 'sharpe_ratio'] else None,
            cbar_kws={'label': metric.replace('_', ' ').title()},
            linewidths=0.5,
            ax=ax
        )
        
        ax.set_title(
            f'Parameter Sensitivity: {metric.replace("_", " ").title()}',
            fontsize=16,
            fontweight='bold',
            pad=20
        )
        ax.set_xlabel(x_param.replace('_', ' ').title(), fontsize=12)
        ax.set_ylabel(y_param.replace('_', ' ').title(), fontsize=12)
        
        plt.tight_layout()
        
        # Save
        if save_path is None:
            save_path = f"param_sensitivity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Parameter sensitivity chart saved to {save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return save_path
    
    def export_results(
        self,
        results: List[OptimizationResult],
        output_path: str = "optimization_results.csv"
    ) -> str:
        """
        Export optimization results to CSV.
        
        Args:
            results: List of OptimizationResults
            output_path: Path to save CSV file
            
        Returns:
            Path where CSV was saved
        """
        if not results:
            logger.warning("No results to export")
            return None
        
        # Convert to DataFrame
        data = [r.to_dict() for r in results]
        df = pd.DataFrame(data)
        
        # Sort by Sharpe ratio descending
        df = df.sort_values('sharpe_ratio', ascending=False)
        
        # Save to CSV
        df.to_csv(output_path, index=False)
        logger.info(f"Results exported to {output_path}")
        
        return output_path
