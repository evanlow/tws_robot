"""
Visualization Helpers for Backtesting

This module provides helpers for creating performance visualizations:
- Equity curve plots
- Drawdown charts
- Trade distribution analysis
- Monthly/yearly performance heatmaps

Note: Uses matplotlib for plotting. Install with: pip install matplotlib

Author: Trading Bot Team
Week 4 Day 3
"""

from typing import List, Tuple, Optional
from datetime import datetime
import sys

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    Figure = None  # Set to None when matplotlib not available
    print("Warning: matplotlib not available. Install with: pip install matplotlib")


from backtest.performance import Trade, DrawdownPeriod, PerformanceMetrics


class PerformanceVisualizer:
    """Creates visualizations for backtest performance analysis"""
    
    def __init__(self, style: str = 'seaborn-v0_8'):
        """
        Initialize visualizer
        
        Args:
            style: Matplotlib style to use
        """
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("matplotlib is required for visualization. Install with: pip install matplotlib")
        
        try:
            plt.style.use(style)
        except:
            # Fallback to default if style not available
            pass
    
    def plot_equity_curve(
        self,
        equity_curve: List[Tuple[datetime, float]],
        title: str = "Equity Curve",
        show_grid: bool = True,
        figsize: Tuple[int, int] = (12, 6)
    ) -> "Figure":
        """
        Plot equity curve over time
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            title: Plot title
            show_grid: Whether to show grid
            figsize: Figure size in inches
            
        Returns:
            Matplotlib Figure object
        """
        dates = [point[0] for point in equity_curve]
        equity = [point[1] for point in equity_curve]
        
        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(dates, equity, linewidth=2, color='#2E86AB', label='Equity')
        
        # Add horizontal line at initial capital
        initial = equity[0]
        ax.axhline(y=initial, color='gray', linestyle='--', alpha=0.5, label='Initial Capital')
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Equity ($)', fontsize=12)
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        if show_grid:
            ax.grid(True, alpha=0.3)
        
        ax.legend(loc='best')
        plt.tight_layout()
        
        return fig
    
    def plot_drawdown(
        self,
        equity_curve: List[Tuple[datetime, float]],
        title: str = "Drawdown Chart",
        show_grid: bool = True,
        figsize: Tuple[int, int] = (12, 6)
    ) -> Figure:
        """
        Plot drawdown over time
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            title: Plot title
            show_grid: Whether to show grid
            figsize: Figure size in inches
            
        Returns:
            Matplotlib Figure object
        """
        dates = [point[0] for point in equity_curve]
        equity = [point[1] for point in equity_curve]
        
        # Calculate drawdown
        peak = equity[0]
        drawdowns = []
        
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = ((eq - peak) / peak) * 100
            drawdowns.append(dd)
        
        fig, ax = plt.subplots(figsize=figsize)
        ax.fill_between(dates, drawdowns, 0, alpha=0.3, color='red', label='Drawdown')
        ax.plot(dates, drawdowns, linewidth=2, color='darkred')
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Drawdown (%)', fontsize=12)
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        if show_grid:
            ax.grid(True, alpha=0.3)
        
        ax.legend(loc='best')
        plt.tight_layout()
        
        return fig
    
    def plot_underwater_curve(
        self,
        drawdown_periods: List[DrawdownPeriod],
        equity_curve: List[Tuple[datetime, float]],
        title: str = "Underwater Equity Curve",
        figsize: Tuple[int, int] = (12, 6)
    ) -> Figure:
        """
        Plot underwater curve showing time in drawdown
        
        Args:
            drawdown_periods: List of DrawdownPeriod objects
            equity_curve: List of (timestamp, equity) tuples for date alignment
            title: Plot title
            figsize: Figure size in inches
            
        Returns:
            Matplotlib Figure object
        """
        dates = [point[0] for point in equity_curve]
        equity = [point[1] for point in equity_curve]
        
        # Calculate running drawdown
        peak = equity[0]
        drawdowns = []
        
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = ((eq - peak) / peak) * 100
            drawdowns.append(dd)
        
        fig, ax = plt.subplots(figsize=figsize)
        
        # Plot the underwater curve
        ax.fill_between(dates, drawdowns, 0, alpha=0.4, color='#A23B72')
        ax.plot(dates, drawdowns, linewidth=1.5, color='#A23B72')
        
        # Mark major drawdown periods
        for dd in drawdown_periods:
            if dd.drawdown_pct > 5:  # Only mark significant drawdowns
                ax.axvline(x=dd.trough_date, color='red', linestyle='--', alpha=0.5, linewidth=1)
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Drawdown (%)', fontsize=12)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        
        return fig
    
    def plot_trade_distribution(
        self,
        trades: List[Trade],
        title: str = "Trade P&L Distribution",
        bins: int = 30,
        figsize: Tuple[int, int] = (10, 6)
    ) -> Figure:
        """
        Plot distribution of trade P&L
        
        Args:
            trades: List of Trade objects
            title: Plot title
            bins: Number of histogram bins
            figsize: Figure size in inches
            
        Returns:
            Matplotlib Figure object
        """
        pnls = [trade.pnl for trade in trades]
        
        fig, ax = plt.subplots(figsize=figsize)
        
        # Plot histogram
        n, bins_edges, patches = ax.hist(pnls, bins=bins, alpha=0.7, edgecolor='black')
        
        # Color bars based on profit/loss
        for i, patch in enumerate(patches):
            if bins_edges[i] >= 0:
                patch.set_facecolor('green')
            else:
                patch.set_facecolor('red')
        
        # Add vertical line at zero
        ax.axvline(x=0, color='black', linestyle='--', linewidth=2, label='Break-even')
        
        # Add mean line
        mean_pnl = sum(pnls) / len(pnls) if pnls else 0
        ax.axvline(x=mean_pnl, color='blue', linestyle='--', linewidth=2, label=f'Mean: ${mean_pnl:.2f}')
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('P&L ($)', fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)
        
        # Format x-axis as currency
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        
        return fig
    
    def plot_monthly_returns(
        self,
        equity_curve: List[Tuple[datetime, float]],
        title: str = "Monthly Returns (%)",
        figsize: Tuple[int, int] = (12, 8)
    ) -> Figure:
        """
        Plot monthly returns heatmap
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            title: Plot title
            figsize: Figure size in inches
            
        Returns:
            Matplotlib Figure object
        """
        # Group by month and calculate returns
        monthly_data = {}
        current_month = None
        month_start_equity = None
        
        for date, equity in equity_curve:
            month_key = (date.year, date.month)
            
            if current_month != month_key:
                if current_month is not None and month_start_equity is not None:
                    # Calculate previous month's return
                    prev_equity = equity_curve[equity_curve.index((date, equity)) - 1][1]
                    ret = ((prev_equity - month_start_equity) / month_start_equity) * 100
                    monthly_data[current_month] = ret
                
                current_month = month_key
                month_start_equity = equity
        
        # Add last month
        if current_month and month_start_equity:
            final_equity = equity_curve[-1][1]
            ret = ((final_equity - month_start_equity) / month_start_equity) * 100
            monthly_data[current_month] = ret
        
        if not monthly_data:
            # Return empty figure if no data
            fig, ax = plt.subplots(figsize=figsize)
            ax.text(0.5, 0.5, 'Insufficient data for monthly returns', 
                   ha='center', va='center', fontsize=14)
            return fig
        
        # Organize data by year and month
        years = sorted(set(year for year, month in monthly_data.keys()))
        months = list(range(1, 13))
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Create matrix
        data_matrix = []
        for year in years:
            year_data = []
            for month in months:
                ret = monthly_data.get((year, month), None)
                year_data.append(ret)
            data_matrix.append(year_data)
        
        fig, ax = plt.subplots(figsize=figsize)
        
        # Create heatmap manually (simplified version)
        for i, year in enumerate(years):
            for j, month in enumerate(months):
                value = data_matrix[i][j]
                if value is not None:
                    color = 'green' if value > 0 else 'red'
                    alpha = min(abs(value) / 10, 1.0)  # Scale alpha by magnitude
                    rect = plt.Rectangle((j, i), 1, 1, facecolor=color, alpha=alpha, edgecolor='black')
                    ax.add_patch(rect)
                    
                    # Add text
                    text_color = 'white' if alpha > 0.5 else 'black'
                    ax.text(j + 0.5, i + 0.5, f'{value:.1f}%',
                           ha='center', va='center', color=text_color, fontsize=10)
        
        ax.set_xlim(0, 12)
        ax.set_ylim(0, len(years))
        ax.set_xticks([i + 0.5 for i in range(12)])
        ax.set_xticklabels(month_names)
        ax.set_yticks([i + 0.5 for i in range(len(years))])
        ax.set_yticklabels(years)
        ax.set_title(title, fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        return fig
    
    def create_performance_dashboard(
        self,
        equity_curve: List[Tuple[datetime, float]],
        trades: List[Trade],
        drawdown_periods: List[DrawdownPeriod],
        metrics: PerformanceMetrics,
        save_path: Optional[str] = None
    ) -> Figure:
        """
        Create comprehensive performance dashboard with multiple charts
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            trades: List of Trade objects
            drawdown_periods: List of DrawdownPeriod objects
            metrics: PerformanceMetrics object
            save_path: Optional path to save figure
            
        Returns:
            Matplotlib Figure object
        """
        fig = plt.figure(figsize=(16, 12))
        
        # Create 2x2 grid
        gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
        
        # 1. Equity Curve
        ax1 = fig.add_subplot(gs[0, :])
        dates = [point[0] for point in equity_curve]
        equity = [point[1] for point in equity_curve]
        ax1.plot(dates, equity, linewidth=2, color='#2E86AB')
        ax1.axhline(y=equity[0], color='gray', linestyle='--', alpha=0.5)
        ax1.set_title('Equity Curve', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Equity ($)', fontsize=12)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax1.grid(True, alpha=0.3)
        
        # 2. Drawdown
        ax2 = fig.add_subplot(gs[1, :])
        peak = equity[0]
        drawdowns = []
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = ((eq - peak) / peak) * 100
            drawdowns.append(dd)
        ax2.fill_between(dates, drawdowns, 0, alpha=0.3, color='red')
        ax2.plot(dates, drawdowns, linewidth=2, color='darkred')
        ax2.set_title('Drawdown', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Drawdown (%)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        
        # 3. Trade Distribution
        ax3 = fig.add_subplot(gs[2, 0])
        if trades:
            pnls = [trade.pnl for trade in trades]
            n, bins_edges, patches = ax3.hist(pnls, bins=20, alpha=0.7, edgecolor='black')
            for i, patch in enumerate(patches):
                if bins_edges[i] >= 0:
                    patch.set_facecolor('green')
                else:
                    patch.set_facecolor('red')
            ax3.axvline(x=0, color='black', linestyle='--', linewidth=2)
        ax3.set_title('Trade P&L Distribution', fontsize=12, fontweight='bold')
        ax3.set_xlabel('P&L ($)', fontsize=10)
        ax3.set_ylabel('Frequency', fontsize=10)
        ax3.grid(True, alpha=0.3, axis='y')
        
        # 4. Key Metrics Table
        ax4 = fig.add_subplot(gs[2, 1])
        ax4.axis('off')
        
        metrics_text = [
            ['Metric', 'Value'],
            ['Total Return', f'{metrics.total_return_pct:+.2f}%'],
            ['Sharpe Ratio', f'{metrics.sharpe_ratio:.2f}'],
            ['Max Drawdown', f'{metrics.max_drawdown_pct:.2f}%'],
            ['Win Rate', f'{metrics.win_rate:.1f}%'],
            ['Profit Factor', f'{metrics.profit_factor:.2f}'],
            ['Total Trades', f'{metrics.total_trades}'],
        ]
        
        table = ax4.table(cellText=metrics_text, cellLoc='left', loc='center',
                         colWidths=[0.5, 0.5])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)
        
        # Style header row
        for i in range(2):
            table[(0, i)].set_facecolor('#2E86AB')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
        return fig
    
    @staticmethod
    def save_figure(fig: Figure, filepath: str, dpi: int = 150):
        """
        Save figure to file
        
        Args:
            fig: Matplotlib Figure object
            filepath: Path to save file
            dpi: Resolution in dots per inch
        """
        fig.savefig(filepath, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
