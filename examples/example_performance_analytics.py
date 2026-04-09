"""
Comprehensive Performance Analytics Example

Demonstrates the full performance analytics workflow:
1. Run backtest (from Day 2)
2. Convert backtest results to analytics format
3. Calculate comprehensive performance metrics
4. Generate professional reports
5. Create visualizations

Author: Trading Bot Team
Week 4 Day 3
"""


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
del _os, _sys

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from backtest import (
    # Data & Simulation
    HistoricalDataManager,
    TimeFrame,
    
    # Strategy & Engine
    Strategy,
    StrategyConfig,
    BacktestEngine,
    BacktestConfig,
    
    # Performance Analytics (NEW - Day 3)
    Trade as AnalyticsTrade,
    TradeDirection,
    PerformanceAnalyzer,
    ReportGenerator,
    PerformanceVisualizer,
)


class MovingAverageCrossover(Strategy):
    """Simple MA crossover strategy for demonstration"""
    
    def __init__(self, config: StrategyConfig, short_period: int = 10, long_period: int = 20):
        super().__init__(config)
        self.short_period = short_period
        self.long_period = long_period
        
        # Track MA state
        self.short_ma = {}
        self.long_ma = {}
        self.prev_signal = {}
    
    def on_start(self):
        """Initialize strategy"""
        print(f"\n{'='*80}")
        print(f"Starting {self.config.name}")
        print(f"Short MA: {self.short_period}, Long MA: {self.long_period}")
        print(f"Symbols: {', '.join(self.config.symbols)}")
        print(f"{'='*80}\n")
    
    def on_bar(self, market_data):
        """Process each bar"""
        # Process all symbols
        for symbol in market_data.symbols:
            bar = market_data.get_bar(symbol)
            if not bar:
                continue
            
            # Get price history
            prices = self.get_price_history(symbol, lookback=self.long_period + 1)
            
            if len(prices) < self.long_period:
                continue  # Not enough data
            
            # Calculate MAs
            short_ma = sum(prices[-self.short_period:]) / self.short_period
            long_ma = sum(prices[-self.long_period:]) / self.long_period
            
            self.short_ma[symbol] = short_ma
            self.long_ma[symbol] = long_ma
            
            # Determine signal
            signal = 1 if short_ma > long_ma else -1
            prev_signal = self.prev_signal.get(symbol, 0)
            
            # Trading logic
            position = self.get_position(symbol) or 0
            
            # Bullish crossover
            if signal == 1 and prev_signal != 1 and position <= 0:
                if position < 0:
                    self.close_position(symbol)  # Close short first
                
                # Calculate position size (10% of equity)
                size = self.calculate_position_size(symbol, bar.close, fraction_of_capital=0.10)
                if size > 0:
                    self.buy(symbol, size, f"MA Bullish Cross ({short_ma:.2f} > {long_ma:.2f})")
            
            # Bearish crossover
            elif signal == -1 and prev_signal != -1 and position > 0:
                self.close_position(symbol, f"MA Bearish Cross ({short_ma:.2f} < {long_ma:.2f})")
            
            self.prev_signal[symbol] = signal
    
    def on_stop(self):
        """Cleanup"""
        print(f"\n{'='*80}")
        print(f"Strategy {self.config.name} completed")
        print(f"Total bars processed: {self.state.bars_processed}")
        print(f"Final P&L: ${self.state.unrealized_pnl + self.state.realized_pnl:,.2f}")
        print(f"{'='*80}\n")


def convert_backtest_trades_to_analytics(backtest_trades) -> list:
    """
    Convert backtest Trade objects to analytics Trade objects
    
    In a real implementation, this would match entry/exit trades.
    For this example, we'll create simplified conversions.
    """
    analytics_trades = []
    
    # Group trades by symbol and match entries/exits
    entries = {}
    
    for trade in backtest_trades:
        if trade.quantity > 0:  # Buy = Entry for long
            entries[trade.symbol] = trade
        elif trade.quantity < 0 and trade.symbol in entries:  # Sell = Exit
            entry = entries.pop(trade.symbol)
            
            # Calculate P&L
            pnl = (trade.price - entry.price) * abs(entry.quantity) - entry.commission - trade.commission
            pnl_pct = ((trade.price - entry.price) / entry.price) * 100
            
            # Create analytics trade
            analytics_trade = AnalyticsTrade(
                symbol=trade.symbol,
                entry_date=entry.timestamp,
                exit_date=trade.timestamp,
                direction=TradeDirection.LONG,
                entry_price=entry.price,
                exit_price=trade.price,
                quantity=abs(entry.quantity),
                pnl=pnl,
                pnl_pct=pnl_pct,
                commission=entry.commission + trade.commission,
                duration_bars=0  # Would calculate from bar indices
            )
            analytics_trades.append(analytics_trade)
    
    return analytics_trades


def main():
    """Run comprehensive performance analytics example"""
    
    print("\n" + "="*80)
    print("Week 4 Day 3: Comprehensive Performance Analytics Example")
    print("="*80)
    
    # ==================== Step 1: Setup and Run Backtest ====================
    print("\n[Step 1] Setting up backtest...")
    
    # Initialize data manager
    data_dir = Path(__file__).parent / "data" / "historical"
    data_manager = HistoricalDataManager(str(data_dir))
    
    # Load real market data
    symbols = ["AAPL"]
    for symbol in symbols:
        filepath = data_dir / f"{symbol}_daily.csv"
        if not filepath.exists():
            print(f"Warning: Data file not found: {filepath}")
            print("Please run download_real_data.py first!")
            return
        
        data_manager.load_csv(
            filepath=str(filepath),
            symbol=symbol,
            timeframe=TimeFrame.DAY_1
        )
    
    print(f"✓ Loaded data for {len(symbols)} symbol(s)")
    
    # Create strategy
    strategy_config = StrategyConfig(
        name="MA_Crossover_10_20",
        symbols=symbols,
        initial_capital=100000.0
    )
    strategy = MovingAverageCrossover(strategy_config, short_period=10, long_period=20)
    
    # Create backtest engine
    backtest_config = BacktestConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000.0,
        commission_per_share=0.01
    )
    
    engine = BacktestEngine(backtest_config, data_manager)
    engine.set_strategy(strategy)
    
    print("✓ Strategy and engine configured")
    
    # Run backtest
    print("\n[Step 2] Running backtest...")
    result = engine.run()
    
    print(f"\n✓ Backtest completed")
    print(f"  Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
    print(f"  Total Trades: {result.total_trades}")
    print(f"  Initial Capital: ${result.initial_capital:,.2f}")
    print(f"  Final Equity: ${result.final_equity:,.2f}")
    print(f"  Total Return: {result.get_return_pct():.2f}%")
    
    # ==================== Step 3: Convert to Analytics Format ====================
    print("\n[Step 3] Converting to analytics format...")
    
    # Convert equity curve
    equity_curve = [(ep.timestamp, ep.equity) for ep in result.equity_curve]
    
    # Convert trades
    analytics_trades = convert_backtest_trades_to_analytics(result.trades)
    
    print(f"✓ Converted {len(analytics_trades)} completed trades")
    
    # ==================== Step 4: Calculate Performance Metrics ====================
    print("\n[Step 4] Calculating comprehensive performance metrics...")
    
    analyzer = PerformanceAnalyzer(risk_free_rate=0.02)  # 2% risk-free rate
    
    metrics = analyzer.analyze(
        equity_curve=equity_curve,
        trades=analytics_trades,
        initial_capital=backtest_config.initial_capital
    )
    
    print("✓ Performance analysis complete")
    
    # ==================== Step 5: Generate Report ====================
    print("\n[Step 5] Generating professional report...")
    
    report = ReportGenerator.generate_text_report(
        metrics=metrics,
        title=f"Performance Report: {strategy_config.name}"
    )
    
    # Display report
    print("\n" + report)
    
    # Save report to file
    report_path = Path(__file__).parent / "reports"
    report_path.mkdir(exist_ok=True)
    
    report_file = report_path / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n✓ Report saved to: {report_file}")
    
    # ==================== Step 6: Create Visualizations ====================
    print("\n[Step 6] Creating visualizations...")
    
    try:
        visualizer = PerformanceVisualizer()
        
        # Create output directory
        viz_path = Path(__file__).parent / "reports" / "charts"
        viz_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Equity curve
        print("  Creating equity curve...")
        fig = visualizer.plot_equity_curve(equity_curve)
        fig_path = viz_path / "equity_curve.png"
        visualizer.save_figure(fig, str(fig_path))
        print(f"  ✓ Saved: {fig_path}")
        
        # 2. Drawdown chart
        print("  Creating drawdown chart...")
        fig = visualizer.plot_drawdown(equity_curve)
        fig_path = viz_path / "drawdown.png"
        visualizer.save_figure(fig, str(fig_path))
        print(f"  ✓ Saved: {fig_path}")
        
        # 3. Trade distribution
        if analytics_trades:
            print("  Creating trade distribution...")
            fig = visualizer.plot_trade_distribution(analytics_trades)
            fig_path = viz_path / "trade_distribution.png"
            visualizer.save_figure(fig, str(fig_path))
            print(f"  ✓ Saved: {fig_path}")
        
        # 4. Performance dashboard
        print("  Creating performance dashboard...")
        drawdown_periods = analyzer._calculate_drawdown_periods(equity_curve)
        fig = visualizer.create_performance_dashboard(
            equity_curve=equity_curve,
            trades=analytics_trades,
            drawdown_periods=drawdown_periods,
            metrics=metrics
        )
        fig_path = viz_path / "performance_dashboard.png"
        visualizer.save_figure(fig, str(fig_path))
        print(f"  ✓ Saved: {fig_path}")
        
        print(f"\n✓ All visualizations created in: {viz_path}")
        
    except ImportError as e:
        print(f"\n⚠ Visualization skipped: {e}")
        print("  Install matplotlib to enable visualizations: pip install matplotlib")
    
    # ==================== Summary ====================
    print("\n" + "="*80)
    print("SUMMARY - Key Performance Indicators")
    print("="*80)
    print(f"Total Return:           {metrics.total_return_pct:+.2f}%")
    print(f"Annualized Return:      {metrics.annualized_return:+.2f}%")
    print(f"Sharpe Ratio:           {metrics.sharpe_ratio:.3f}")
    print(f"Sortino Ratio:          {metrics.sortino_ratio:.3f}")
    print(f"Calmar Ratio:           {metrics.calmar_ratio:.3f}")
    print(f"Max Drawdown:           {metrics.max_drawdown_pct:.2f}%")
    print(f"Win Rate:               {metrics.win_rate:.2f}%")
    print(f"Profit Factor:          {metrics.profit_factor:.3f}")
    print(f"Expectancy:             ${metrics.expectancy:,.2f}")
    print("="*80)
    
    print("\n✅ Performance analytics example completed successfully!")
    print(f"\nReports and charts saved to: {report_path.absolute()}")


if __name__ == "__main__":
    main()
