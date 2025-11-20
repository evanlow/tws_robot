"""
Backtest Runner Script

Runs backtests for strategies with comprehensive reporting and analysis.
Supports multiple symbols, timeframes, and strategy configurations.

Usage:
    python run_backtest.py --strategy bollinger_bands --symbols AAPL MSFT --days 180
    python run_backtest.py --config backtest_config.json
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import json

from backtesting import (
    HistoricalDataManager,
    BacktestEngine,
    PerformanceAnalytics,
    RiskManager
)
from strategies import BollingerBandsStrategy
from strategies.base_strategy import StrategyState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    Orchestrates backtest execution and reporting.
    
    Features:
    - Multi-symbol backtesting
    - Strategy configuration
    - Risk management
    - Performance analytics
    - Detailed reporting
    
    Example:
        >>> runner = BacktestRunner()
        >>> results = runner.run_backtest(
        ...     strategy_name="bollinger_bands",
        ...     symbols=["AAPL", "MSFT"],
        ...     start_date=datetime(2024, 1, 1),
        ...     end_date=datetime(2024, 6, 30)
        ... )
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        position_sizing: str = "percent",
        position_size_pct: float = 0.1,
        risk_per_trade: float = 0.02,
        use_risk_manager: bool = True
    ):
        """
        Initialize backtest runner.
        
        Args:
            initial_capital: Starting capital
            commission: Commission rate
            slippage: Slippage rate
            position_sizing: Position sizing method
            position_size_pct: Position size percentage
            risk_per_trade: Risk per trade percentage
            use_risk_manager: Whether to use risk management
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.position_sizing = position_sizing
        self.position_size_pct = position_size_pct
        self.risk_per_trade = risk_per_trade
        self.use_risk_manager = use_risk_manager
        
        # Initialize components
        self.data_manager = HistoricalDataManager()
        
        # Create risk manager if enabled
        self.risk_manager = None
        if use_risk_manager:
            self.risk_manager = RiskManager(
                max_positions=10,
                max_drawdown_pct=0.20,
                daily_loss_limit=0.05,
                max_position_pct=0.25,
                max_leverage=1.0
            )
        
        self.engine = BacktestEngine(
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            position_sizing=position_sizing,
            position_size_pct=position_size_pct,
            risk_per_trade=risk_per_trade,
            max_position_size=0.25,
            risk_manager=self.risk_manager
        )
        
        logger.info(
            f"BacktestRunner initialized: capital=${initial_capital:,.2f}, "
            f"commission={commission:.4f}, slippage={slippage:.4f}"
        )
    
    def run_backtest(
        self,
        strategy_name: str,
        symbols: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: int = 180,
        strategy_params: Optional[Dict] = None
    ) -> Dict:
        """
        Run backtest for given strategy and symbols.
        
        Args:
            strategy_name: Name of strategy to test
            symbols: List of symbols to trade
            start_date: Start date (if None, calculated from days)
            end_date: End date (if None, uses today)
            days: Number of days to backtest (if dates not specified)
            strategy_params: Strategy-specific parameters
            
        Returns:
            Dictionary with results for each symbol
        """
        # Set date range
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=days)
        
        logger.info(
            f"\n{'='*60}\n"
            f"Starting Backtest\n"
            f"{'='*60}\n"
            f"Strategy: {strategy_name}\n"
            f"Symbols: {', '.join(symbols)}\n"
            f"Period: {start_date.date()} to {end_date.date()} ({days} days)\n"
            f"Initial Capital: ${self.initial_capital:,.2f}\n"
            f"{'='*60}\n"
        )
        
        # Create strategy
        strategy = self._create_strategy(strategy_name, symbols, strategy_params)
        
        # Run backtest for each symbol
        all_results = {}
        
        for symbol in symbols:
            logger.info(f"\n{'='*60}")
            logger.info(f"Backtesting {symbol}")
            logger.info(f"{'='*60}\n")
            
            try:
                # Reset strategy state for new symbol
                strategy.reset()
                strategy.state = StrategyState.READY
                
                # Create fresh risk manager and backtest engine for each symbol
                risk_manager = None
                if self.use_risk_manager:
                    risk_manager = RiskManager(
                        max_positions=10,
                        max_drawdown_pct=0.20,
                        daily_loss_limit=0.05,
                        max_position_pct=0.25,
                        max_leverage=1.0
                    )
                
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    commission=self.commission,
                    slippage=self.slippage,
                    position_sizing=self.position_sizing,
                    position_size_pct=self.position_size_pct,
                    risk_per_trade=self.risk_per_trade,
                    max_position_size=0.25,
                    risk_manager=risk_manager
                )
                
                # Get historical data
                bars = self.data_manager.get_historical_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    bar_size="1 day"
                )
                
                # If no data from IB, create sample data
                if not bars:
                    logger.info(f"No IB data available, creating sample data for {symbol}")
                    bars = self.data_manager.create_sample_data(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        bar_size="1 day",
                        base_price=150.0,
                        volatility=0.02
                    )
                
                if not bars:
                    logger.warning(f"Unable to get data for {symbol}")
                    continue
                
                logger.info(f"Loaded {len(bars)} bars for {symbol}")
                
                # Run backtest
                results = engine.run_backtest(strategy, bars, symbol)
                
                # Print results
                self._print_results(symbol, results)
                
                # Store results
                all_results[symbol] = {
                    'results': results,
                    'bars': len(bars),
                    'start_date': start_date,
                    'end_date': end_date
                }
                
            except Exception as e:
                logger.error(f"Error backtesting {symbol}: {e}", exc_info=True)
                continue
        
        # Print summary
        self._print_summary(all_results)
        
        return all_results
    
    def _create_strategy(
        self,
        strategy_name: str,
        symbols: List[str],
        params: Optional[Dict] = None
    ):
        """Create strategy instance"""
        params = params or {}
        
        if strategy_name == "bollinger_bands":
            return BollingerBandsStrategy(
                name=strategy_name,
                symbols=symbols,
                period=params.get('period', 20),
                std_dev=params.get('std_dev', 2.0),
                min_volume=params.get('min_volume', 100000),
                position_size=self.position_size_pct,
                stop_loss_pct=params.get('stop_loss_pct', 0.02)
            )
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")
    
    def _print_results(self, symbol: str, results):
        """Print detailed results for a symbol"""
        print(f"\n{'='*60}")
        print(f"Results for {symbol}")
        print(f"{'='*60}\n")
        
        # Basic metrics
        print(f"Initial Capital:    ${results.initial_capital:>12,.2f}")
        print(f"Final Capital:      ${results.final_capital:>12,.2f}")
        print(f"Total Return:       {results.total_return_percent:>12.2f}%")
        print(f"Total Trades:       {results.total_trades:>12}")
        
        if results.total_trades > 0 and results.metrics:
            print(f"Win Rate:           {results.metrics.get('win_rate', 0):>12.2f}%")
            print(f"Profit Factor:      {results.metrics.get('profit_factor', 0):>12.2f}")
            print(f"Avg Trade:          ${results.metrics.get('avg_trade', 0):>12,.2f}")
        
        # Advanced metrics
        if results.metrics:
            metrics = results.metrics
            print(f"\nRisk-Adjusted Returns:")
            print(f"Sharpe Ratio:       {metrics.get('sharpe_ratio', 0):>12.2f}")
            print(f"Sortino Ratio:      {metrics.get('sortino_ratio', 0):>12.2f}")
            print(f"Calmar Ratio:       {metrics.get('calmar_ratio', 0):>12.2f}")
            
            print(f"\nDrawdown Analysis:")
            print(f"Max Drawdown:       {metrics.get('max_drawdown_pct', 0):>12.2f}%")
            print(f"Max DD Duration:    {metrics.get('max_drawdown_duration', 0):>12} days")
            print(f"Recovery Factor:    {metrics.get('recovery_factor', 0):>12.2f}")
            
            print(f"\nTrade Analysis:")
            print(f"Avg Trade P&L:      ${metrics.get('avg_trade_pnl', 0):>12,.2f}")
            print(f"Best Trade:         ${metrics.get('best_trade', 0):>12,.2f}")
            print(f"Worst Trade:        ${metrics.get('worst_trade', 0):>12,.2f}")
            print(f"Expectancy:         ${metrics.get('expectancy', 0):>12,.2f}")
        
        print(f"{'='*60}\n")
    
    def _print_summary(self, all_results: Dict):
        """Print summary across all symbols"""
        if not all_results:
            logger.warning("No results to summarize")
            return
        
        print(f"\n{'='*60}")
        print(f"Backtest Summary - All Symbols")
        print(f"{'='*60}\n")
        
        total_return = sum(
            r['results'].total_return_percent 
            for r in all_results.values()
        ) / len(all_results)
        
        total_trades = sum(
            r['results'].total_trades 
            for r in all_results.values()
        )
        
        avg_win_rate = sum(
            r['results'].metrics.get('win_rate', 0.0) 
            for r in all_results.values() 
            if r['results'].total_trades > 0
        ) / len([r for r in all_results.values() if r['results'].total_trades > 0]) if any(r['results'].total_trades > 0 for r in all_results.values()) else 0.0
        
        print(f"Symbols Tested:     {len(all_results)}")
        print(f"Avg Return:         {total_return:>12.2f}%")
        print(f"Total Trades:       {total_trades:>12}")
        print(f"Avg Win Rate:       {avg_win_rate:>12.2f}%")
        
        # Best and worst performers
        best_symbol = max(
            all_results.items(),
            key=lambda x: x[1]['results'].total_return_percent
        )
        worst_symbol = min(
            all_results.items(),
            key=lambda x: x[1]['results'].total_return_percent
        )
        
        print(f"\nBest Performer:     {best_symbol[0]} "
              f"({best_symbol[1]['results'].total_return_percent:.2f}%)")
        print(f"Worst Performer:    {worst_symbol[0]} "
              f"({worst_symbol[1]['results'].total_return_percent:.2f}%)")
        
        print(f"{'='*60}\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run strategy backtests with comprehensive analysis"
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
        default=['AAPL', 'MSFT', 'GOOGL'],
        help='Symbols to backtest (default: AAPL MSFT GOOGL)'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=180,
        help='Number of days to backtest (default: 180)'
    )
    
    parser.add_argument(
        '--capital',
        type=float,
        default=100000.0,
        help='Initial capital (default: 100000)'
    )
    
    parser.add_argument(
        '--position-size',
        type=float,
        default=0.1,
        help='Position size as percentage (default: 0.1 = 10%%)'
    )
    
    parser.add_argument(
        '--period',
        type=int,
        default=20,
        help='Bollinger Bands period (default: 20)'
    )
    
    parser.add_argument(
        '--std-dev',
        type=float,
        default=2.0,
        help='Bollinger Bands standard deviation (default: 2.0)'
    )
    
    parser.add_argument(
        '--no-risk-manager',
        action='store_true',
        help='Disable risk management'
    )
    
    args = parser.parse_args()
    
    # Create runner
    runner = BacktestRunner(
        initial_capital=args.capital,
        position_size_pct=args.position_size,
        use_risk_manager=not args.no_risk_manager
    )
    
    # Strategy parameters
    strategy_params = {
        'period': args.period,
        'std_dev': args.std_dev
    }
    
    # Run backtest
    try:
        results = runner.run_backtest(
            strategy_name=args.strategy,
            symbols=args.symbols,
            days=args.days,
            strategy_params=strategy_params
        )
        
        logger.info("Backtest completed successfully")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
