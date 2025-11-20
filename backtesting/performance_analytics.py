"""
Performance analytics for backtesting results.

Calculates advanced metrics like Sharpe ratio, maximum drawdown,
Sortino ratio, and other risk-adjusted performance measures.
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DrawdownPeriod:
    """
    Period of drawdown from peak to recovery.
    
    Attributes:
        start_date: When drawdown started
        end_date: When recovery completed (None if ongoing)
        peak_date: Date of peak before drawdown
        valley_date: Date of lowest point
        peak_value: Portfolio value at peak
        valley_value: Portfolio value at valley
        drawdown: Maximum drawdown amount
        drawdown_pct: Maximum drawdown percentage
        duration_days: Length of drawdown period
        recovery_days: Days from valley to recovery
    """
    start_date: datetime
    end_date: Optional[datetime]
    peak_date: datetime
    valley_date: datetime
    peak_value: float
    valley_value: float
    drawdown: float
    drawdown_pct: float
    duration_days: int
    recovery_days: Optional[int] = None


class PerformanceAnalytics:
    """
    Calculate advanced performance metrics for backtest results.
    
    Provides risk-adjusted returns, drawdown analysis, and statistical measures.
    
    Example:
        >>> analytics = PerformanceAnalytics()
        >>> metrics = analytics.calculate_metrics(
        ...     equity_curve=results.equity_curve,
        ...     trades=results.trades,
        ...     risk_free_rate=0.02
        ... )
        >>> 
        >>> print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        >>> print(f"Max Drawdown: {metrics['max_drawdown_pct']:.2%}")
        >>> print(f"Sortino Ratio: {metrics['sortino_ratio']:.2f}")
    """
    
    def __init__(self):
        """Initialize performance analytics"""
        self.metrics: Dict[str, Any] = {}
        logger.debug("PerformanceAnalytics initialized")
    
    def calculate_metrics(
        self,
        equity_curve: List[Tuple[datetime, float]],
        trades: List,
        initial_capital: float,
        risk_free_rate: float = 0.02
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics.
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            trades: List of BacktestTrade objects
            initial_capital: Starting capital
            risk_free_rate: Annual risk-free rate (default 2%)
            
        Returns:
            Dictionary of performance metrics
        """
        if not equity_curve:
            return self._empty_metrics()
        
        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(equity_curve, columns=['timestamp', 'equity'])
        df['returns'] = df['equity'].pct_change()
        df['daily_returns'] = df['returns']
        
        # Calculate basic metrics
        total_return = (df['equity'].iloc[-1] - initial_capital) / initial_capital
        
        # Calculate returns-based metrics
        sharpe = self._calculate_sharpe_ratio(df['returns'].dropna(), risk_free_rate)
        sortino = self._calculate_sortino_ratio(df['returns'].dropna(), risk_free_rate)
        
        # Calculate drawdown metrics
        dd_metrics = self._calculate_drawdown_metrics(df)
        
        # Calculate trade metrics
        trade_metrics = self._calculate_trade_metrics(trades)
        
        # Calculate time-based metrics
        time_metrics = self._calculate_time_metrics(df)
        
        # Combine all metrics
        self.metrics = {
            # Returns
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'annualized_return': self._annualize_return(total_return, time_metrics['days']),
            'annualized_return_pct': self._annualize_return(total_return, time_metrics['days']) * 100,
            
            # Risk-adjusted returns
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'calmar_ratio': self._calculate_calmar_ratio(
                self._annualize_return(total_return, time_metrics['days']),
                dd_metrics['max_drawdown_pct']
            ),
            
            # Drawdown
            'max_drawdown': dd_metrics['max_drawdown'],
            'max_drawdown_pct': dd_metrics['max_drawdown_pct'],
            'max_drawdown_duration': dd_metrics['max_drawdown_duration'],
            'avg_drawdown_pct': dd_metrics['avg_drawdown_pct'],
            'drawdown_periods': dd_metrics['drawdown_periods'],
            'recovery_factor': self._calculate_recovery_factor(total_return, dd_metrics['max_drawdown_pct']),
            
            # Volatility
            'volatility': df['returns'].std(),
            'annualized_volatility': df['returns'].std() * np.sqrt(252),
            'downside_volatility': self._calculate_downside_volatility(df['returns'].dropna()),
            
            # Trade metrics
            **trade_metrics,
            
            # Time metrics
            **time_metrics
        }
        
        logger.info(f"Calculated metrics: Sharpe={sharpe:.2f}, MaxDD={dd_metrics['max_drawdown_pct']:.2%}")
        
        return self.metrics
    
    def _calculate_sharpe_ratio(
        self,
        returns: pd.Series,
        risk_free_rate: float
    ) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: Series of returns
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Sharpe ratio (annualized)
        """
        if len(returns) < 2 or returns.std() == 0:
            return 0.0
        
        # Convert annual risk-free rate to period rate
        daily_rf = risk_free_rate / 252
        
        excess_returns = returns - daily_rf
        sharpe = excess_returns.mean() / returns.std()
        
        # Annualize
        return sharpe * np.sqrt(252)
    
    def _calculate_sortino_ratio(
        self,
        returns: pd.Series,
        risk_free_rate: float
    ) -> float:
        """
        Calculate Sortino ratio (uses downside deviation).
        
        Args:
            returns: Series of returns
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Sortino ratio (annualized)
        """
        if len(returns) < 2:
            return 0.0
        
        daily_rf = risk_free_rate / 252
        excess_returns = returns - daily_rf
        
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0
        
        sortino = excess_returns.mean() / downside_returns.std()
        
        # Annualize
        return sortino * np.sqrt(252)
    
    def _calculate_calmar_ratio(
        self,
        annualized_return: float,
        max_drawdown_pct: float
    ) -> float:
        """
        Calculate Calmar ratio (return / max drawdown).
        
        Args:
            annualized_return: Annual return
            max_drawdown_pct: Maximum drawdown percentage
            
        Returns:
            Calmar ratio
        """
        if max_drawdown_pct == 0:
            return 0.0
        
        return annualized_return / abs(max_drawdown_pct)
    
    def _calculate_recovery_factor(
        self,
        total_return: float,
        max_drawdown_pct: float
    ) -> float:
        """
        Calculate recovery factor (total return / max drawdown).
        
        Args:
            total_return: Total return
            max_drawdown_pct: Maximum drawdown percentage
            
        Returns:
            Recovery factor
        """
        if max_drawdown_pct == 0:
            return 0.0
        
        return total_return / abs(max_drawdown_pct)
    
    def _calculate_downside_volatility(self, returns: pd.Series) -> float:
        """
        Calculate downside volatility (annualized).
        
        Args:
            returns: Series of returns
            
        Returns:
            Annualized downside volatility
        """
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return 0.0
        
        return downside_returns.std() * np.sqrt(252)
    
    def _calculate_drawdown_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate drawdown metrics.
        
        Args:
            df: DataFrame with equity curve
            
        Returns:
            Dictionary of drawdown metrics
        """
        # Calculate running maximum
        df['cummax'] = df['equity'].cummax()
        df['drawdown'] = df['equity'] - df['cummax']
        df['drawdown_pct'] = (df['drawdown'] / df['cummax']) * 100
        
        # Find maximum drawdown
        max_dd_idx = df['drawdown'].idxmin()
        max_drawdown = df.loc[max_dd_idx, 'drawdown']
        max_drawdown_pct = df.loc[max_dd_idx, 'drawdown_pct']
        
        # Find drawdown periods
        drawdown_periods = self._identify_drawdown_periods(df)
        
        # Calculate max drawdown duration
        max_dd_duration = 0
        if drawdown_periods:
            max_dd_duration = max(dd.duration_days for dd in drawdown_periods)
        
        # Calculate average drawdown
        avg_drawdown_pct = 0.0
        if drawdown_periods:
            avg_drawdown_pct = sum(dd.drawdown_pct for dd in drawdown_periods) / len(drawdown_periods)
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'max_drawdown_duration': max_dd_duration,
            'avg_drawdown_pct': avg_drawdown_pct,
            'num_drawdown_periods': len(drawdown_periods),
            'drawdown_periods': drawdown_periods
        }
    
    def _identify_drawdown_periods(self, df: pd.DataFrame) -> List[DrawdownPeriod]:
        """
        Identify discrete drawdown periods.
        
        Args:
            df: DataFrame with equity and drawdown columns
            
        Returns:
            List of DrawdownPeriod objects
        """
        periods = []
        in_drawdown = False
        peak_idx = 0
        valley_idx = 0
        start_idx = 0
        
        for i in range(len(df)):
            if df['drawdown'].iloc[i] < 0:
                if not in_drawdown:
                    # Starting new drawdown
                    in_drawdown = True
                    start_idx = i - 1 if i > 0 else i
                    peak_idx = start_idx
                    valley_idx = i
                else:
                    # Update valley if this is lower
                    if df['drawdown'].iloc[i] < df['drawdown'].iloc[valley_idx]:
                        valley_idx = i
            else:
                if in_drawdown:
                    # Recovered from drawdown
                    peak_value = df['equity'].iloc[peak_idx]
                    valley_value = df['equity'].iloc[valley_idx]
                    drawdown = valley_value - peak_value
                    drawdown_pct = (drawdown / peak_value) * 100
                    
                    duration = (df['timestamp'].iloc[i] - df['timestamp'].iloc[start_idx]).days
                    recovery = (df['timestamp'].iloc[i] - df['timestamp'].iloc[valley_idx]).days
                    
                    period = DrawdownPeriod(
                        start_date=df['timestamp'].iloc[start_idx],
                        end_date=df['timestamp'].iloc[i],
                        peak_date=df['timestamp'].iloc[peak_idx],
                        valley_date=df['timestamp'].iloc[valley_idx],
                        peak_value=peak_value,
                        valley_value=valley_value,
                        drawdown=drawdown,
                        drawdown_pct=drawdown_pct,
                        duration_days=duration,
                        recovery_days=recovery
                    )
                    periods.append(period)
                    
                    in_drawdown = False
        
        # Handle ongoing drawdown
        if in_drawdown:
            peak_value = df['equity'].iloc[peak_idx]
            valley_value = df['equity'].iloc[valley_idx]
            drawdown = valley_value - peak_value
            drawdown_pct = (drawdown / peak_value) * 100
            
            duration = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[start_idx]).days
            
            period = DrawdownPeriod(
                start_date=df['timestamp'].iloc[start_idx],
                end_date=None,
                peak_date=df['timestamp'].iloc[peak_idx],
                valley_date=df['timestamp'].iloc[valley_idx],
                peak_value=peak_value,
                valley_value=valley_value,
                drawdown=drawdown,
                drawdown_pct=drawdown_pct,
                duration_days=duration,
                recovery_days=None
            )
            periods.append(period)
        
        return periods
    
    def _calculate_trade_metrics(self, trades: List) -> Dict[str, Any]:
        """
        Calculate trade-based metrics.
        
        Args:
            trades: List of BacktestTrade objects
            
        Returns:
            Dictionary of trade metrics
        """
        if not trades:
            return {
                'avg_trade_pnl': 0.0,
                'avg_trade_pnl_pct': 0.0,
                'best_trade': 0.0,
                'worst_trade': 0.0,
                'avg_winning_trade': 0.0,
                'avg_losing_trade': 0.0,
                'largest_winning_trade': 0.0,
                'largest_losing_trade': 0.0,
                'avg_trade_duration': 0.0,
                'expectancy': 0.0
            }
        
        pnls = [t.pnl for t in trades]
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        
        # Calculate durations
        durations = [(t.exit_time - t.entry_time).total_seconds() / 3600 for t in trades]  # in hours
        
        # Calculate expectancy (average P&L per trade)
        expectancy = sum(pnls) / len(pnls) if pnls else 0.0
        
        return {
            'avg_trade_pnl': np.mean(pnls),
            'avg_trade_pnl_pct': np.mean([t.pnl_percent for t in trades]),
            'best_trade': max(pnls) if pnls else 0.0,
            'worst_trade': min(pnls) if pnls else 0.0,
            'avg_winning_trade': np.mean([t.pnl for t in winning_trades]) if winning_trades else 0.0,
            'avg_losing_trade': np.mean([t.pnl for t in losing_trades]) if losing_trades else 0.0,
            'largest_winning_trade': max([t.pnl for t in winning_trades]) if winning_trades else 0.0,
            'largest_losing_trade': min([t.pnl for t in losing_trades]) if losing_trades else 0.0,
            'avg_trade_duration': np.mean(durations) if durations else 0.0,
            'expectancy': expectancy
        }
    
    def _calculate_time_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate time-based metrics.
        
        Args:
            df: DataFrame with equity curve
            
        Returns:
            Dictionary of time metrics
        """
        start_date = df['timestamp'].iloc[0]
        end_date = df['timestamp'].iloc[-1]
        duration = (end_date - start_date).days
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'days': duration,
            'years': duration / 365.25
        }
    
    def _annualize_return(self, total_return: float, days: int) -> float:
        """
        Annualize a total return.
        
        Args:
            total_return: Total return
            days: Number of days
            
        Returns:
            Annualized return
        """
        if days == 0:
            return 0.0
        
        years = days / 365.25
        if years == 0:
            return 0.0
        
        return (1 + total_return) ** (1 / years) - 1
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics dictionary"""
        return {
            'total_return': 0.0,
            'total_return_pct': 0.0,
            'annualized_return': 0.0,
            'annualized_return_pct': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_pct': 0.0,
            'max_drawdown_duration': 0,
            'avg_drawdown_pct': 0.0,
            'num_drawdown_periods': 0,
            'drawdown_periods': [],
            'recovery_factor': 0.0,
            'volatility': 0.0,
            'annualized_volatility': 0.0,
            'downside_volatility': 0.0
        }
    
    def print_summary(self):
        """Print formatted summary of metrics"""
        if not self.metrics:
            print("No metrics calculated")
            return
        
        print("\n" + "="*60)
        print("PERFORMANCE SUMMARY")
        print("="*60)
        
        print("\nReturns:")
        print(f"  Total Return:        {self.metrics['total_return_pct']:>10.2f}%")
        print(f"  Annualized Return:   {self.metrics['annualized_return_pct']:>10.2f}%")
        
        print("\nRisk-Adjusted Returns:")
        print(f"  Sharpe Ratio:        {self.metrics['sharpe_ratio']:>10.2f}")
        print(f"  Sortino Ratio:       {self.metrics['sortino_ratio']:>10.2f}")
        print(f"  Calmar Ratio:        {self.metrics['calmar_ratio']:>10.2f}")
        
        print("\nDrawdown:")
        print(f"  Max Drawdown:        {self.metrics['max_drawdown_pct']:>10.2f}%")
        print(f"  Avg Drawdown:        {self.metrics['avg_drawdown_pct']:>10.2f}%")
        print(f"  Max DD Duration:     {self.metrics['max_drawdown_duration']:>10} days")
        print(f"  Recovery Factor:     {self.metrics['recovery_factor']:>10.2f}")
        
        print("\nVolatility:")
        print(f"  Volatility:          {self.metrics['volatility']*100:>10.2f}%")
        print(f"  Annual Volatility:   {self.metrics['annualized_volatility']*100:>10.2f}%")
        print(f"  Downside Vol:        {self.metrics['downside_volatility']*100:>10.2f}%")
        
        if 'avg_trade_pnl' in self.metrics:
            print("\nTrade Statistics:")
            print(f"  Avg Trade P&L:       ${self.metrics['avg_trade_pnl']:>10.2f}")
            print(f"  Best Trade:          ${self.metrics['best_trade']:>10.2f}")
            print(f"  Worst Trade:         ${self.metrics['worst_trade']:>10.2f}")
            print(f"  Expectancy:          ${self.metrics['expectancy']:>10.2f}")
        
        print("\n" + "="*60 + "\n")
