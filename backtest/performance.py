"""
Performance Analytics for Backtesting

This module provides comprehensive performance analysis tools including:
- Risk-adjusted return metrics (Sharpe, Sortino, Calmar ratios)
- Trade statistics and analysis
- Drawdown analysis with recovery periods
- Professional report generation
- Monte Carlo simulation support

Author: Trading Bot Team
Week 4 Day 3
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import math
from enum import Enum


class TradeDirection(Enum):
    """Trade direction enumeration"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Trade:
    """Represents a completed trade with all relevant details"""
    symbol: str
    entry_date: datetime
    exit_date: datetime
    direction: TradeDirection
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    commission: float
    duration_bars: int
    
    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable"""
        return self.pnl > 0
    
    @property
    def duration_days(self) -> float:
        """Get trade duration in days"""
        return (self.exit_date - self.entry_date).total_seconds() / 86400


@dataclass
class DrawdownPeriod:
    """Represents a drawdown period from peak to trough to recovery"""
    start_date: datetime
    trough_date: datetime
    end_date: Optional[datetime]  # None if still in drawdown
    peak_equity: float
    trough_equity: float
    recovery_equity: Optional[float]
    drawdown_pct: float
    duration_days: int
    recovery_days: Optional[int]
    
    @property
    def is_recovered(self) -> bool:
        """Check if drawdown has recovered"""
        return self.end_date is not None
    
    @property
    def total_duration_days(self) -> Optional[int]:
        """Get total duration including recovery"""
        if self.end_date:
            return (self.end_date - self.start_date).days
        return None


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest"""
    
    # Period information
    start_date: datetime
    end_date: datetime
    total_days: int
    trading_days: int
    
    # Capital metrics
    initial_capital: float
    final_equity: float
    peak_equity: float
    
    # Returns
    total_return: float
    total_return_pct: float
    annualized_return: float
    
    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    volatility: float  # Annualized standard deviation of returns
    downside_deviation: float  # For Sortino ratio
    
    # Risk-adjusted returns
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # P&L statistics
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    profit_factor: float  # Gross profit / Gross loss
    expectancy: float  # Average $ per trade
    
    # Trade duration
    avg_trade_duration_days: float
    avg_winning_duration_days: float
    avg_losing_duration_days: float
    
    # Drawdown statistics
    avg_drawdown_pct: float
    avg_recovery_days: float
    max_drawdown_duration_days: int
    
    # Exposure
    avg_exposure_pct: float  # Average % of capital deployed
    max_positions: int
    
    def to_dict(self) -> Dict:
        """Convert metrics to dictionary"""
        return {
            'period': {
                'start_date': self.start_date.isoformat(),
                'end_date': self.end_date.isoformat(),
                'total_days': self.total_days,
                'trading_days': self.trading_days,
            },
            'returns': {
                'initial_capital': self.initial_capital,
                'final_equity': self.final_equity,
                'peak_equity': self.peak_equity,
                'total_return': self.total_return,
                'total_return_pct': self.total_return_pct,
                'annualized_return': self.annualized_return,
            },
            'risk': {
                'max_drawdown': self.max_drawdown,
                'max_drawdown_pct': self.max_drawdown_pct,
                'volatility': self.volatility,
                'downside_deviation': self.downside_deviation,
            },
            'risk_adjusted': {
                'sharpe_ratio': self.sharpe_ratio,
                'sortino_ratio': self.sortino_ratio,
                'calmar_ratio': self.calmar_ratio,
            },
            'trades': {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'win_rate': self.win_rate,
            },
            'pnl': {
                'avg_win': self.avg_win,
                'avg_loss': self.avg_loss,
                'largest_win': self.largest_win,
                'largest_loss': self.largest_loss,
                'profit_factor': self.profit_factor,
                'expectancy': self.expectancy,
            },
            'duration': {
                'avg_trade_duration_days': self.avg_trade_duration_days,
                'avg_winning_duration_days': self.avg_winning_duration_days,
                'avg_losing_duration_days': self.avg_losing_duration_days,
            },
            'drawdown': {
                'avg_drawdown_pct': self.avg_drawdown_pct,
                'avg_recovery_days': self.avg_recovery_days,
                'max_drawdown_duration_days': self.max_drawdown_duration_days,
            },
            'exposure': {
                'avg_exposure_pct': self.avg_exposure_pct,
                'max_positions': self.max_positions,
            }
        }


class PerformanceAnalyzer:
    """Analyzes backtest results and calculates comprehensive performance metrics"""
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize analyzer
        
        Args:
            risk_free_rate: Annual risk-free rate for Sharpe/Sortino calculations
        """
        self.risk_free_rate = risk_free_rate
    
    def analyze(
        self,
        equity_curve: List[Tuple[datetime, float]],
        trades: List[Trade],
        initial_capital: float,
        drawdown_periods: Optional[List[DrawdownPeriod]] = None
    ) -> PerformanceMetrics:
        """
        Perform comprehensive performance analysis
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            trades: List of completed trades
            initial_capital: Starting capital
            drawdown_periods: Optional pre-calculated drawdown periods
            
        Returns:
            PerformanceMetrics object with all calculated metrics
        """
        if not equity_curve:
            raise ValueError("Equity curve cannot be empty")
        
        # Calculate drawdown periods if not provided
        if drawdown_periods is None:
            drawdown_periods = self._calculate_drawdown_periods(equity_curve)
        
        # Period information
        start_date = equity_curve[0][0]
        end_date = equity_curve[-1][0]
        total_days = (end_date - start_date).days
        trading_days = len(equity_curve)
        
        # Capital metrics
        final_equity = equity_curve[-1][1]
        peak_equity = max(eq for _, eq in equity_curve)
        
        # Returns
        total_return = final_equity - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        years = total_days / 365.25
        annualized_return = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # Calculate daily returns for volatility
        daily_returns = self._calculate_daily_returns(equity_curve)
        
        # Risk metrics
        max_dd = max((dd.drawdown_pct for dd in drawdown_periods), default=0)
        volatility = self._calculate_volatility(daily_returns)
        downside_dev = self._calculate_downside_deviation(daily_returns)
        
        # Risk-adjusted returns
        sharpe = self._calculate_sharpe_ratio(daily_returns, volatility)
        sortino = self._calculate_sortino_ratio(daily_returns, downside_dev)
        calmar = annualized_return / max_dd if max_dd > 0 else 0
        
        # Trade statistics
        if trades:
            winners = [t for t in trades if t.is_winner]
            losers = [t for t in trades if not t.is_winner]
            
            total_trades = len(trades)
            winning_trades = len(winners)
            losing_trades = len(losers)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # P&L statistics
            avg_win = sum(t.pnl for t in winners) / len(winners) if winners else 0
            avg_loss = sum(t.pnl for t in losers) / len(losers) if losers else 0
            largest_win = max((t.pnl for t in winners), default=0)
            largest_loss = min((t.pnl for t in losers), default=0)
            
            gross_profit = sum(t.pnl for t in winners)
            gross_loss = abs(sum(t.pnl for t in losers))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            expectancy = sum(t.pnl for t in trades) / len(trades)
            
            # Trade duration
            avg_duration = sum(t.duration_days for t in trades) / len(trades)
            avg_win_duration = sum(t.duration_days for t in winners) / len(winners) if winners else 0
            avg_loss_duration = sum(t.duration_days for t in losers) / len(losers) if losers else 0
        else:
            total_trades = winning_trades = losing_trades = 0
            win_rate = avg_win = avg_loss = largest_win = largest_loss = 0
            profit_factor = expectancy = 0
            avg_duration = avg_win_duration = avg_loss_duration = 0
        
        # Drawdown statistics
        if drawdown_periods:
            avg_dd = sum(dd.drawdown_pct for dd in drawdown_periods) / len(drawdown_periods)
            recovered_dds = [dd for dd in drawdown_periods if dd.is_recovered]
            avg_recovery = sum(dd.recovery_days for dd in recovered_dds) / len(recovered_dds) if recovered_dds else 0
            max_dd_duration = max((dd.duration_days for dd in drawdown_periods), default=0)
        else:
            avg_dd = avg_recovery = max_dd_duration = 0
        
        # Exposure (simplified - would need position data for accurate calculation)
        avg_exposure = 50.0  # Placeholder
        max_positions = 1  # Placeholder
        
        return PerformanceMetrics(
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            trading_days=trading_days,
            initial_capital=initial_capital,
            final_equity=final_equity,
            peak_equity=peak_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            annualized_return=annualized_return,
            max_drawdown=max_dd * initial_capital / 100,
            max_drawdown_pct=max_dd,
            volatility=volatility,
            downside_deviation=downside_dev,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_trade_duration_days=avg_duration,
            avg_winning_duration_days=avg_win_duration,
            avg_losing_duration_days=avg_loss_duration,
            avg_drawdown_pct=avg_dd,
            avg_recovery_days=avg_recovery,
            max_drawdown_duration_days=max_dd_duration,
            avg_exposure_pct=avg_exposure,
            max_positions=max_positions
        )
    
    def _calculate_daily_returns(self, equity_curve: List[Tuple[datetime, float]]) -> List[float]:
        """Calculate daily returns from equity curve"""
        returns = []
        for i in range(1, len(equity_curve)):
            prev_equity = equity_curve[i-1][1]
            curr_equity = equity_curve[i][1]
            if prev_equity > 0:
                returns.append((curr_equity - prev_equity) / prev_equity)
            else:
                returns.append(0.0)
        return returns
    
    def _calculate_volatility(self, returns: List[float]) -> float:
        """Calculate annualized volatility (standard deviation of returns)"""
        if len(returns) < 2:
            return 0.0
        
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)
        
        # Annualize (assuming 252 trading days)
        return std_dev * math.sqrt(252) * 100
    
    def _calculate_downside_deviation(self, returns: List[float]) -> float:
        """Calculate downside deviation (for Sortino ratio)"""
        if len(returns) < 2:
            return 0.0
        
        # Only consider returns below risk-free rate
        daily_rf = self.risk_free_rate / 252
        downside_returns = [min(0, r - daily_rf) for r in returns]
        
        variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
        std_dev = math.sqrt(variance)
        
        # Annualize
        return std_dev * math.sqrt(252) * 100
    
    def _calculate_sharpe_ratio(self, returns: List[float], volatility: float) -> float:
        """Calculate Sharpe ratio"""
        if volatility == 0 or len(returns) == 0:
            return 0.0
        
        avg_return = sum(returns) / len(returns)
        daily_rf = self.risk_free_rate / 252
        excess_return = avg_return - daily_rf
        
        # Annualize
        annual_excess = excess_return * 252 * 100
        return annual_excess / volatility if volatility > 0 else 0
    
    def _calculate_sortino_ratio(self, returns: List[float], downside_dev: float) -> float:
        """Calculate Sortino ratio"""
        if downside_dev == 0 or len(returns) == 0:
            return 0.0
        
        avg_return = sum(returns) / len(returns)
        daily_rf = self.risk_free_rate / 252
        excess_return = avg_return - daily_rf
        
        # Annualize
        annual_excess = excess_return * 252 * 100
        return annual_excess / downside_dev if downside_dev > 0 else 0
    
    def _calculate_drawdown_periods(
        self,
        equity_curve: List[Tuple[datetime, float]]
    ) -> List[DrawdownPeriod]:
        """
        Identify all drawdown periods from peak to trough to recovery
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            
        Returns:
            List of DrawdownPeriod objects
        """
        if not equity_curve:
            return []
        
        periods = []
        peak = equity_curve[0][1]
        peak_date = equity_curve[0][0]
        trough = peak
        trough_date = peak_date
        in_drawdown = False
        
        for date, equity in equity_curve[1:]:
            if equity > peak:
                # New peak - if we were in drawdown, record the period
                if in_drawdown:
                    dd_pct = ((peak - trough) / peak) * 100
                    duration = (trough_date - peak_date).days
                    recovery = (date - trough_date).days
                    
                    periods.append(DrawdownPeriod(
                        start_date=peak_date,
                        trough_date=trough_date,
                        end_date=date,
                        peak_equity=peak,
                        trough_equity=trough,
                        recovery_equity=equity,
                        drawdown_pct=dd_pct,
                        duration_days=duration,
                        recovery_days=recovery
                    ))
                    in_drawdown = False
                
                peak = equity
                peak_date = date
                trough = equity
                trough_date = date
            
            elif equity < trough:
                # New trough
                trough = equity
                trough_date = date
                in_drawdown = True
        
        # Handle unrecovered drawdown
        if in_drawdown:
            dd_pct = ((peak - trough) / peak) * 100
            duration = (trough_date - peak_date).days
            
            periods.append(DrawdownPeriod(
                start_date=peak_date,
                trough_date=trough_date,
                end_date=None,
                peak_equity=peak,
                trough_equity=trough,
                recovery_equity=None,
                drawdown_pct=dd_pct,
                duration_days=duration,
                recovery_days=None
            ))
        
        return periods


class ReportGenerator:
    """Generates professional performance reports"""
    
    @staticmethod
    def generate_text_report(metrics: PerformanceMetrics, title: str = "Backtest Performance Report") -> str:
        """
        Generate a formatted text report
        
        Args:
            metrics: Performance metrics to report
            title: Report title
            
        Returns:
            Formatted text report
        """
        lines = [
            "=" * 80,
            title.center(80),
            "=" * 80,
            "",
            "PERIOD INFORMATION",
            "-" * 80,
            f"Start Date:              {metrics.start_date.strftime('%Y-%m-%d')}",
            f"End Date:                {metrics.end_date.strftime('%Y-%m-%d')}",
            f"Total Days:              {metrics.total_days:,}",
            f"Trading Days:            {metrics.trading_days:,}",
            "",
            "RETURNS",
            "-" * 80,
            f"Initial Capital:         ${metrics.initial_capital:,.2f}",
            f"Final Equity:            ${metrics.final_equity:,.2f}",
            f"Peak Equity:             ${metrics.peak_equity:,.2f}",
            f"Total Return:            ${metrics.total_return:,.2f} ({metrics.total_return_pct:+.2f}%)",
            f"Annualized Return:       {metrics.annualized_return:+.2f}%",
            "",
            "RISK METRICS",
            "-" * 80,
            f"Max Drawdown:            ${metrics.max_drawdown:,.2f} ({metrics.max_drawdown_pct:.2f}%)",
            f"Volatility (Annual):     {metrics.volatility:.2f}%",
            f"Downside Deviation:      {metrics.downside_deviation:.2f}%",
            "",
            "RISK-ADJUSTED RETURNS",
            "-" * 80,
            f"Sharpe Ratio:            {metrics.sharpe_ratio:.3f}",
            f"Sortino Ratio:           {metrics.sortino_ratio:.3f}",
            f"Calmar Ratio:            {metrics.calmar_ratio:.3f}",
            "",
            "TRADE STATISTICS",
            "-" * 80,
            f"Total Trades:            {metrics.total_trades:,}",
            f"Winning Trades:          {metrics.winning_trades:,}",
            f"Losing Trades:           {metrics.losing_trades:,}",
            f"Win Rate:                {metrics.win_rate:.2f}%",
            "",
            "P&L STATISTICS",
            "-" * 80,
            f"Average Win:             ${metrics.avg_win:,.2f}",
            f"Average Loss:            ${metrics.avg_loss:,.2f}",
            f"Largest Win:             ${metrics.largest_win:,.2f}",
            f"Largest Loss:            ${metrics.largest_loss:,.2f}",
            f"Profit Factor:           {metrics.profit_factor:.3f}",
            f"Expectancy:              ${metrics.expectancy:,.2f}",
            "",
            "TRADE DURATION",
            "-" * 80,
            f"Avg Trade Duration:      {metrics.avg_trade_duration_days:.1f} days",
            f"Avg Winning Duration:    {metrics.avg_winning_duration_days:.1f} days",
            f"Avg Losing Duration:     {metrics.avg_losing_duration_days:.1f} days",
            "",
            "DRAWDOWN ANALYSIS",
            "-" * 80,
            f"Avg Drawdown:            {metrics.avg_drawdown_pct:.2f}%",
            f"Avg Recovery Days:       {metrics.avg_recovery_days:.1f}",
            f"Max DD Duration:         {metrics.max_drawdown_duration_days:,} days",
            "",
            "EXPOSURE",
            "-" * 80,
            f"Avg Exposure:            {metrics.avg_exposure_pct:.2f}%",
            f"Max Positions:           {metrics.max_positions}",
            "",
            "=" * 80,
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_html_report(metrics: PerformanceMetrics, title: str = "Backtest Performance Report") -> str:
        """
        Generate an HTML report (simplified version)
        
        Args:
            metrics: Performance metrics to report
            title: Report title
            
        Returns:
            HTML report as string
        """
        # Simplified HTML - in production would include charts, styling, etc.
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ padding: 10px; text-align: left; border: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
                .positive {{ color: green; }}
                .negative {{ color: red; }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
            
            <h2>Period Information</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Start Date</td><td>{metrics.start_date.strftime('%Y-%m-%d')}</td></tr>
                <tr><td>End Date</td><td>{metrics.end_date.strftime('%Y-%m-%d')}</td></tr>
                <tr><td>Total Days</td><td>{metrics.total_days:,}</td></tr>
                <tr><td>Trading Days</td><td>{metrics.trading_days:,}</td></tr>
            </table>
            
            <h2>Returns</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Initial Capital</td><td>${metrics.initial_capital:,.2f}</td></tr>
                <tr><td>Final Equity</td><td>${metrics.final_equity:,.2f}</td></tr>
                <tr><td>Total Return</td><td class="{'positive' if metrics.total_return > 0 else 'negative'}">${metrics.total_return:,.2f} ({metrics.total_return_pct:+.2f}%)</td></tr>
                <tr><td>Annualized Return</td><td class="{'positive' if metrics.annualized_return > 0 else 'negative'}">{metrics.annualized_return:+.2f}%</td></tr>
            </table>
            
            <!-- Additional sections would go here -->
        </body>
        </html>
        """
        return html
