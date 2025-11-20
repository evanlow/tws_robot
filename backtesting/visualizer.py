"""
Performance visualization for backtest results.

Generates charts and visual reports for trading strategy analysis including
equity curves, drawdown plots, monthly returns heatmaps, and trade distributions.
"""

import logging
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10


class BacktestVisualizer:
    """
    Generate visual reports for backtest results.
    
    Creates charts for equity curves, drawdowns, returns distributions,
    and other performance visualizations.
    
    Example:
        >>> visualizer = BacktestVisualizer()
        >>> visualizer.plot_equity_curve(results, save_path="equity.png")
        >>> visualizer.plot_drawdown(results, save_path="drawdown.png")
        >>> visualizer.generate_full_report(results, output_dir="reports/")
    """
    
    def __init__(self):
        """Initialize visualizer"""
        self.colors = {
            'equity': '#2E86AB',
            'drawdown': '#A23B72',
            'positive': '#06A77D',
            'negative': '#D32F2F',
            'neutral': '#757575'
        }
        logger.debug("BacktestVisualizer initialized")
    
    def plot_equity_curve(
        self,
        results: Any,
        save_path: Optional[str] = None,
        show: bool = False
    ) -> Optional[str]:
        """
        Plot equity curve over time.
        
        Args:
            results: BacktestResults object
            save_path: Path to save figure (if None, generates default)
            show: Whether to display the plot
            
        Returns:
            Path where figure was saved
        """
        if not results.equity_curve:
            logger.warning("No equity curve data to plot")
            return None
        
        # Extract data
        timestamps = [t for t, _ in results.equity_curve]
        equity = [e for _, e in results.equity_curve]
        
        # Create figure
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # Plot equity
        ax.plot(timestamps, equity, color=self.colors['equity'], linewidth=2, label='Portfolio Value')
        
        # Add initial capital line
        ax.axhline(y=results.initial_capital, color=self.colors['neutral'], 
                   linestyle='--', linewidth=1, alpha=0.7, label='Initial Capital')
        
        # Format
        ax.set_title('Equity Curve', fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Portfolio Value ($)', fontsize=12)
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')
        
        # Add statistics text box
        stats_text = f"Total Return: {results.total_return_percent:.2f}%\n"
        stats_text += f"Initial: ${results.initial_capital:,.0f}\n"
        stats_text += f"Final: ${results.final_capital:,.0f}"
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        
        # Save
        if save_path is None:
            save_path = f"equity_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Equity curve saved to {save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return save_path
    
    def plot_drawdown(
        self,
        results: Any,
        save_path: Optional[str] = None,
        show: bool = False
    ) -> Optional[str]:
        """
        Plot drawdown over time.
        
        Args:
            results: BacktestResults object
            save_path: Path to save figure
            show: Whether to display the plot
            
        Returns:
            Path where figure was saved
        """
        if not results.equity_curve:
            logger.warning("No equity curve data to plot")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(results.equity_curve, columns=['timestamp', 'equity'])
        df['cummax'] = df['equity'].cummax()
        df['drawdown_pct'] = ((df['equity'] - df['cummax']) / df['cummax']) * 100
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
        
        # Plot 1: Equity with drawdown periods shaded
        ax1.plot(df['timestamp'], df['equity'], color=self.colors['equity'], 
                linewidth=2, label='Portfolio Value')
        ax1.plot(df['timestamp'], df['cummax'], color=self.colors['positive'], 
                linestyle='--', linewidth=1, alpha=0.7, label='Peak Value')
        
        # Shade drawdown periods
        drawdown_mask = df['drawdown_pct'] < 0
        if drawdown_mask.any():
            ax1.fill_between(df['timestamp'], df['equity'], df['cummax'], 
                            where=drawdown_mask, alpha=0.3, 
                            color=self.colors['drawdown'], label='Drawdown')
        
        ax1.set_title('Equity & Drawdown Analysis', fontsize=16, fontweight='bold', pad=20)
        ax1.set_ylabel('Portfolio Value ($)', fontsize=12)
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Plot 2: Drawdown percentage
        ax2.fill_between(df['timestamp'], 0, df['drawdown_pct'], 
                        color=self.colors['drawdown'], alpha=0.5)
        ax2.plot(df['timestamp'], df['drawdown_pct'], color=self.colors['drawdown'], 
                linewidth=2)
        
        # Mark maximum drawdown
        max_dd_idx = df['drawdown_pct'].idxmin()
        max_dd_date = df.loc[max_dd_idx, 'timestamp']
        max_dd_value = df.loc[max_dd_idx, 'drawdown_pct']
        ax2.scatter([max_dd_date], [max_dd_value], color='red', s=100, 
                   zorder=5, label=f'Max DD: {max_dd_value:.2f}%')
        
        ax2.set_xlabel('Date', fontsize=12)
        ax2.set_ylabel('Drawdown (%)', fontsize=12)
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        # Format x-axis
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Save
        if save_path is None:
            save_path = f"drawdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Drawdown chart saved to {save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return save_path
    
    def plot_monthly_returns(
        self,
        results: Any,
        save_path: Optional[str] = None,
        show: bool = False
    ) -> Optional[str]:
        """
        Plot monthly returns as a heatmap.
        
        Args:
            results: BacktestResults object
            save_path: Path to save figure
            show: Whether to display the plot
            
        Returns:
            Path where figure was saved
        """
        if not results.equity_curve or len(results.equity_curve) < 2:
            logger.warning("Insufficient data for monthly returns")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(results.equity_curve, columns=['timestamp', 'equity'])
        df['returns'] = df['equity'].pct_change()
        df.set_index('timestamp', inplace=True)
        
        # Resample to monthly returns
        monthly = df['returns'].resample('ME').apply(lambda x: (1 + x).prod() - 1) * 100
        
        if len(monthly) == 0:
            logger.warning("No monthly data available")
            return None
        
        # Create year-month pivot table
        monthly_df = pd.DataFrame(monthly)
        monthly_df['year'] = monthly_df.index.year
        monthly_df['month'] = monthly_df.index.month
        
        pivot = monthly_df.pivot(index='year', columns='month', values='returns')
        
        # Create figure
        fig, ax = plt.subplots(figsize=(14, max(6, len(pivot) * 0.8)))
        
        # Create heatmap
        sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn', center=0,
                   cbar_kws={'label': 'Monthly Return (%)'}, linewidths=0.5,
                   ax=ax)
        
        ax.set_title('Monthly Returns (%)', fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Month', fontsize=12)
        ax.set_ylabel('Year', fontsize=12)
        
        # Set month labels (only for existing months in data)
        month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        existing_months = [int(col) for col in pivot.columns]
        month_names = [month_labels[m-1] for m in existing_months]
        ax.set_xticklabels(month_names, rotation=0)
        
        plt.tight_layout()
        
        # Save
        if save_path is None:
            save_path = f"monthly_returns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Monthly returns chart saved to {save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return save_path
    
    def plot_trade_distribution(
        self,
        results: Any,
        save_path: Optional[str] = None,
        show: bool = False
    ) -> Optional[str]:
        """
        Plot trade P&L distribution.
        
        Args:
            results: BacktestResults object
            save_path: Path to save figure
            show: Whether to display the plot
            
        Returns:
            Path where figure was saved
        """
        if not results.trades:
            logger.warning("No trades to plot")
            return None
        
        # Extract trade P&L
        pnls = [t.pnl for t in results.trades]
        pnl_pcts = [t.pnl_percent for t in results.trades]
        
        # Create figure with 2 subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Plot 1: P&L histogram (dollar)
        colors = [self.colors['positive'] if p > 0 else self.colors['negative'] for p in pnls]
        ax1.bar(range(len(pnls)), pnls, color=colors, alpha=0.7, edgecolor='black')
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=1)
        ax1.set_title('Trade P&L Distribution ($)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Trade Number', fontsize=12)
        ax1.set_ylabel('P&L ($)', fontsize=12)
        ax1.grid(True, alpha=0.3, axis='y')
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Add statistics
        win_count = sum(1 for p in pnls if p > 0)
        loss_count = len(pnls) - win_count
        win_rate = (win_count / len(pnls)) * 100 if pnls else 0
        
        stats_text = f"Trades: {len(pnls)}\n"
        stats_text += f"Winners: {win_count}\n"
        stats_text += f"Losers: {loss_count}\n"
        stats_text += f"Win Rate: {win_rate:.1f}%"
        
        ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        # Plot 2: P&L percentage histogram
        bins = 20
        ax2.hist(pnl_pcts, bins=bins, color=self.colors['equity'], alpha=0.7, 
                edgecolor='black')
        ax2.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
        ax2.axvline(x=np.mean(pnl_pcts), color='green', linestyle='--', linewidth=2,
                   label=f'Mean: {np.mean(pnl_pcts):.2f}%')
        
        ax2.set_title('Trade P&L Distribution (%)', fontsize=14, fontweight='bold')
        ax2.set_xlabel('P&L (%)', fontsize=12)
        ax2.set_ylabel('Frequency', fontsize=12)
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        # Save
        if save_path is None:
            save_path = f"trade_distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Trade distribution chart saved to {save_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return save_path
    
    def generate_full_report(
        self,
        results: Any,
        output_dir: str = "reports",
        symbol: str = "Portfolio"
    ) -> Dict[str, str]:
        """
        Generate complete visual report with all charts.
        
        Args:
            results: BacktestResults object
            output_dir: Directory to save charts
            symbol: Symbol name for filenames
            
        Returns:
            Dictionary mapping chart type to file path
        """
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp for this report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Generate all charts
        charts = {}
        
        logger.info(f"Generating full visual report for {symbol}...")
        
        # Equity curve
        equity_path = output_path / f"{symbol}_equity_{timestamp}.png"
        if self.plot_equity_curve(results, save_path=str(equity_path)):
            charts['equity_curve'] = str(equity_path)
        
        # Drawdown
        dd_path = output_path / f"{symbol}_drawdown_{timestamp}.png"
        if self.plot_drawdown(results, save_path=str(dd_path)):
            charts['drawdown'] = str(dd_path)
        
        # Monthly returns (if enough data)
        if len(results.equity_curve) >= 30:
            monthly_path = output_path / f"{symbol}_monthly_{timestamp}.png"
            if self.plot_monthly_returns(results, save_path=str(monthly_path)):
                charts['monthly_returns'] = str(monthly_path)
        
        # Trade distribution
        if results.trades:
            trade_path = output_path / f"{symbol}_trades_{timestamp}.png"
            if self.plot_trade_distribution(results, save_path=str(trade_path)):
                charts['trade_distribution'] = str(trade_path)
        
        logger.info(f"Generated {len(charts)} charts in {output_dir}")
        
        return charts
