"""
Strategy Parameter Optimization Script

Runs grid search optimization to find optimal strategy parameters.

Usage:
    python optimize_strategy.py --strategy bollinger_bands --symbols AAPL MSFT --days 180
"""

import argparse
import logging
import sys
from pathlib import Path

from backtesting.optimizer import StrategyOptimizer
from strategies import BollingerBandsStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Optimize strategy parameters through grid search"
    )
    
    parser.add_argument(
        '--strategy',
        type=str,
        default='bollinger_bands',
        help='Strategy name (default: bollinger_bands)'
    )
    
    parser.add_argument(
        '--symbols',
        nargs='+',
        default=['AAPL'],
        help='Symbols to test (default: AAPL)'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=180,
        help='Number of days to backtest (default: 180)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='optimization',
        help='Output directory for results (default: optimization)'
    )
    
    parser.add_argument(
        '--metric',
        type=str,
        default='sharpe_ratio',
        choices=['sharpe_ratio', 'total_return', 'calmar_ratio', 'sortino_ratio'],
        help='Metric to optimize (default: sharpe_ratio)'
    )
    
    args = parser.parse_args()
    
    # Create output directory
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Define parameter grid based on strategy
    if args.strategy == 'bollinger_bands':
        parameter_grid = {
            'period': [10, 15, 20, 25, 30],
            'std_dev': [1.5, 2.0, 2.5, 3.0],
            'stop_loss_pct': [0.01, 0.02, 0.03]
        }
        strategy_class = BollingerBandsStrategy
    else:
        logger.error(f"Unknown strategy: {args.strategy}")
        return 1
    
    logger.info(
        f"\n{'='*60}\n"
        f"Strategy Parameter Optimization\n"
        f"{'='*60}\n"
        f"Strategy: {args.strategy}\n"
        f"Symbols: {', '.join(args.symbols)}\n"
        f"Days: {args.days}\n"
        f"Parameter Grid: {parameter_grid}\n"
        f"Total Combinations: {len(parameter_grid['period']) * len(parameter_grid['std_dev']) * len(parameter_grid['stop_loss_pct'])}\n"
        f"{'='*60}\n"
    )
    
    # Create optimizer
    optimizer = StrategyOptimizer()
    
    try:
        # Run grid search
        results = optimizer.grid_search(
            strategy_class=strategy_class,
            parameter_grid=parameter_grid,
            symbols=args.symbols,
            days=args.days,
            strategy_name=args.strategy
        )
        
        if not results:
            logger.error("No successful backtests completed")
            return 1
        
        # Find optimal parameters
        best = optimizer.find_optimal_parameters(results, metric=args.metric)
        
        # Export results
        csv_path = output_path / "optimization_results.csv"
        optimizer.export_results(results, str(csv_path))
        
        # Generate sensitivity plots
        if len(parameter_grid) >= 2:
            param_names = list(parameter_grid.keys())
            
            # Plot for each metric
            metrics_to_plot = ['sharpe_ratio', 'total_return', 'max_drawdown']
            
            for metric in metrics_to_plot:
                plot_path = output_path / f"sensitivity_{metric}_{param_names[0]}_{param_names[1]}.png"
                optimizer.plot_parameter_sensitivity(
                    results=results,
                    x_param=param_names[0],
                    y_param=param_names[1],
                    metric=metric,
                    save_path=str(plot_path)
                )
            
            logger.info(f"\n✅ Optimization complete!")
            logger.info(f"   Results saved to: {args.output_dir}/")
            logger.info(f"   CSV: optimization_results.csv")
            logger.info(f"   Charts: sensitivity_*.png")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Optimization interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Optimization failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
