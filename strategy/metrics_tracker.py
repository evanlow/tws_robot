"""
Paper Trading Metrics Tracker

Tracks strategy performance metrics during paper trading phase for validation.
Calculates key metrics like Sharpe ratio, win rate, drawdown, and profit factor.

Author: TWS Robot Development Team
Date: November 23, 2025
Sprint 2 Task 2
"""

import sqlite3
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
import math
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Individual trade record"""
    trade_id: int
    strategy_name: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    commission: float = 0.0
    
    @property
    def net_pnl(self) -> float:
        """P&L after commissions"""
        return self.pnl - self.commission
    
    @property
    def is_winner(self) -> bool:
        """Whether trade was profitable"""
        return self.net_pnl > 0
    
    @property
    def holding_period_hours(self) -> float:
        """Trade holding period in hours"""
        return (self.exit_time - self.entry_time).total_seconds() / 3600.0


@dataclass
class DailySnapshot:
    """Daily portfolio snapshot for time-series analysis"""
    snapshot_date: date
    strategy_name: str
    portfolio_value: float
    cash: float
    positions_value: float
    daily_pnl: float
    cumulative_pnl: float
    trade_count: int
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class MetricsSnapshot:
    """Current metrics snapshot"""
    strategy_name: str
    as_of_date: datetime
    days_running: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    consecutive_losses: int
    total_pnl: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float


class PaperMetricsTracker:
    """
    Track and calculate strategy performance metrics during paper trading.
    
    Manages:
    - Trade history and P&L
    - Daily portfolio snapshots
    - Performance metrics (Sharpe, drawdown, win rate)
    - Validation criteria progress
    
    Storage:
    - SQLite database with strategy_metrics and strategy_snapshots tables
    """
    
    def __init__(self, db_path: str, strategy_name: str, initial_capital: float = 100000.0):
        """
        Initialize metrics tracker.
        
        Args:
            db_path: Path to SQLite database
            strategy_name: Name of strategy being tracked
            initial_capital: Starting capital for paper trading
        """
        self.db_path = db_path
        self.strategy_name = strategy_name
        self.initial_capital = initial_capital
        self.start_date: Optional[date] = None
        
        # In-memory cache
        self._trades: List[Trade] = []
        self._daily_snapshots: List[DailySnapshot] = []
        self._peak_value = initial_capital
        self._max_drawdown = 0.0
        self._consecutive_losses = 0
        
        # Initialize database
        self._init_database()
        self._load_from_database()
        
        logger.info(f"PaperMetricsTracker initialized for '{strategy_name}' (capital: ${initial_capital:,.2f})")
    
    def _init_database(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT NOT NULL,
                pnl REAL NOT NULL,
                commission REAL DEFAULT 0.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Daily snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                portfolio_value REAL NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                daily_pnl REAL NOT NULL,
                cumulative_pnl REAL NOT NULL,
                trade_count INTEGER DEFAULT 0,
                realized_pnl REAL DEFAULT 0.0,
                unrealized_pnl REAL DEFAULT 0.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_date, strategy_name)
            )
        """)
        
        # Metrics metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_metadata (
                strategy_name TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                peak_value REAL NOT NULL,
                max_drawdown REAL DEFAULT 0.0,
                consecutive_losses INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Database tables initialized: {self.db_path}")
    
    def _load_from_database(self):
        """Load existing data from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Load metadata
        cursor.execute("""
            SELECT start_date, initial_capital, peak_value, max_drawdown, consecutive_losses
            FROM strategy_metadata
            WHERE strategy_name = ?
        """, (self.strategy_name,))
        
        row = cursor.fetchone()
        if row:
            self.start_date = datetime.fromisoformat(row[0]).date()
            self.initial_capital = row[1]
            self._peak_value = row[2]
            self._max_drawdown = row[3]
            self._consecutive_losses = row[4]
            logger.info(f"Loaded existing metrics for '{self.strategy_name}' (started: {self.start_date})")
        else:
            # First time - insert metadata
            self.start_date = date.today()
            cursor.execute("""
                INSERT INTO strategy_metadata (strategy_name, start_date, initial_capital, peak_value)
                VALUES (?, ?, ?, ?)
            """, (self.strategy_name, self.start_date.isoformat(), self.initial_capital, self._peak_value))
            conn.commit()
            logger.info(f"Created new metrics tracking for '{self.strategy_name}' (start: {self.start_date})")
        
        # Load trades
        cursor.execute("""
            SELECT trade_id, strategy_name, symbol, side, quantity, entry_price, exit_price,
                   entry_time, exit_time, pnl, commission
            FROM strategy_trades
            WHERE strategy_name = ?
            ORDER BY exit_time
        """, (self.strategy_name,))
        
        for row in cursor.fetchall():
            trade = Trade(
                trade_id=row[0],
                strategy_name=row[1],
                symbol=row[2],
                side=row[3],
                quantity=row[4],
                entry_price=row[5],
                exit_price=row[6],
                entry_time=datetime.fromisoformat(row[7]),
                exit_time=datetime.fromisoformat(row[8]),
                pnl=row[9],
                commission=row[10]
            )
            self._trades.append(trade)
        
        # Load daily snapshots
        cursor.execute("""
            SELECT snapshot_date, strategy_name, portfolio_value, cash, positions_value,
                   daily_pnl, cumulative_pnl, trade_count, realized_pnl, unrealized_pnl
            FROM strategy_snapshots
            WHERE strategy_name = ?
            ORDER BY snapshot_date
        """, (self.strategy_name,))
        
        for row in cursor.fetchall():
            snapshot = DailySnapshot(
                snapshot_date=datetime.fromisoformat(row[0]).date(),
                strategy_name=row[1],
                portfolio_value=row[2],
                cash=row[3],
                positions_value=row[4],
                daily_pnl=row[5],
                cumulative_pnl=row[6],
                trade_count=row[7],
                realized_pnl=row[8],
                unrealized_pnl=row[9]
            )
            self._daily_snapshots.append(snapshot)
        
        conn.close()
        logger.debug(f"Loaded {len(self._trades)} trades, {len(self._daily_snapshots)} snapshots")
    
    def record_trade(self, symbol: str, side: str, quantity: int, entry_price: float,
                    exit_price: float, entry_time: datetime, exit_time: datetime,
                    commission: float = 0.0) -> Trade:
        """
        Record a completed trade.
        
        Args:
            symbol: Ticker symbol
            side: 'BUY' or 'SELL' (entry side)
            quantity: Number of shares
            entry_price: Entry price per share
            exit_price: Exit price per share
            entry_time: Entry timestamp
            exit_time: Exit timestamp
            commission: Total commission paid
            
        Returns:
            Trade object
        """
        # Calculate P&L
        if side.upper() == 'BUY':
            pnl = (exit_price - entry_price) * quantity
        else:  # SELL (short)
            pnl = (entry_price - exit_price) * quantity
        
        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO strategy_trades 
            (strategy_name, symbol, side, quantity, entry_price, exit_price, 
             entry_time, exit_time, pnl, commission)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (self.strategy_name, symbol, side, quantity, entry_price, exit_price,
              entry_time.isoformat(), exit_time.isoformat(), pnl, commission))
        
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create trade object
        trade = Trade(
            trade_id=trade_id,
            strategy_name=self.strategy_name,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=entry_time,
            exit_time=exit_time,
            pnl=pnl,
            commission=commission
        )
        
        # Update cache
        self._trades.append(trade)
        
        # Update consecutive losses
        if trade.is_winner:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
        
        # Update metadata
        self._update_metadata()
        
        logger.info(f"Recorded trade: {symbol} {side} {quantity}@{exit_price:.2f} - P&L: ${trade.net_pnl:.2f}")
        
        return trade
    
    def record_daily_snapshot(self, snapshot_date: date, portfolio_value: float,
                             cash: float, positions_value: float, daily_pnl: float,
                             trade_count: int = 0, realized_pnl: float = 0.0,
                             unrealized_pnl: float = 0.0):
        """
        Record end-of-day portfolio snapshot.
        
        Args:
            snapshot_date: Date of snapshot
            portfolio_value: Total portfolio value (cash + positions)
            cash: Cash balance
            positions_value: Market value of positions
            daily_pnl: P&L for the day
            trade_count: Number of trades executed today
            realized_pnl: Realized P&L from closed trades
            unrealized_pnl: Unrealized P&L from open positions
        """
        # Calculate cumulative P&L
        cumulative_pnl = portfolio_value - self.initial_capital
        
        # Update peak and drawdown
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value
        
        current_drawdown = (self._peak_value - portfolio_value) / self._peak_value
        if current_drawdown > self._max_drawdown:
            self._max_drawdown = current_drawdown
        
        # Store in database (replace if exists)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO strategy_snapshots
            (snapshot_date, strategy_name, portfolio_value, cash, positions_value,
             daily_pnl, cumulative_pnl, trade_count, realized_pnl, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (snapshot_date.isoformat(), self.strategy_name, portfolio_value, cash,
              positions_value, daily_pnl, cumulative_pnl, trade_count, realized_pnl, unrealized_pnl))
        
        conn.commit()
        conn.close()
        
        # Update cache
        snapshot = DailySnapshot(
            snapshot_date=snapshot_date,
            strategy_name=self.strategy_name,
            portfolio_value=portfolio_value,
            cash=cash,
            positions_value=positions_value,
            daily_pnl=daily_pnl,
            cumulative_pnl=cumulative_pnl,
            trade_count=trade_count,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl
        )
        
        # Remove existing snapshot for this date if present
        self._daily_snapshots = [s for s in self._daily_snapshots if s.snapshot_date != snapshot_date]
        self._daily_snapshots.append(snapshot)
        self._daily_snapshots.sort(key=lambda s: s.snapshot_date)
        
        # Update metadata
        self._update_metadata()
        
        logger.info(f"Recorded snapshot: {snapshot_date} - Value: ${portfolio_value:,.2f}, Daily P&L: ${daily_pnl:+,.2f}")
    
    def _update_metadata(self):
        """Update metadata in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE strategy_metadata
            SET peak_value = ?, max_drawdown = ?, consecutive_losses = ?, last_updated = ?
            WHERE strategy_name = ?
        """, (self._peak_value, self._max_drawdown, self._consecutive_losses,
              datetime.now().isoformat(), self.strategy_name))
        
        conn.commit()
        conn.close()
    
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.0) -> float:
        """
        Calculate annualized Sharpe ratio from daily returns.
        
        Args:
            risk_free_rate: Annual risk-free rate (default 0%)
            
        Returns:
            Sharpe ratio (0.0 if insufficient data)
        """
        if len(self._daily_snapshots) < 2:
            return 0.0
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(self._daily_snapshots)):
            prev_value = self._daily_snapshots[i-1].portfolio_value
            curr_value = self._daily_snapshots[i].portfolio_value
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(daily_return)
        
        if not returns:
            return 0.0
        
        # Calculate mean and std dev
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return 0.0
        
        # Annualize (assuming 252 trading days)
        annual_return = mean_return * 252
        annual_std = std_dev * math.sqrt(252)
        
        sharpe = (annual_return - risk_free_rate) / annual_std
        
        return sharpe
    
    def calculate_max_drawdown(self) -> float:
        """
        Calculate maximum drawdown from daily snapshots.
        
        Returns:
            Maximum drawdown as percentage (0.0 to 1.0)
        """
        return self._max_drawdown
    
    def calculate_win_rate(self) -> float:
        """
        Calculate win rate (percentage of winning trades).
        
        Returns:
            Win rate (0.0 to 1.0)
        """
        if not self._trades:
            return 0.0
        
        winning_trades = sum(1 for t in self._trades if t.is_winner)
        return winning_trades / len(self._trades)
    
    def calculate_profit_factor(self) -> float:
        """
        Calculate profit factor (gross profit / gross loss).
        
        Returns:
            Profit factor (0.0 if no losing trades)
        """
        if not self._trades:
            return 0.0
        
        gross_profit = sum(t.net_pnl for t in self._trades if t.is_winner)
        gross_loss = abs(sum(t.net_pnl for t in self._trades if not t.is_winner))
        
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def get_days_running(self) -> int:
        """
        Get number of calendar days since start.
        
        Returns:
            Days running
        """
        if not self.start_date:
            return 0
        
        return (date.today() - self.start_date).days
    
    def get_metrics_snapshot(self) -> MetricsSnapshot:
        """
        Get current metrics snapshot.
        
        Returns:
            MetricsSnapshot with all current metrics
        """
        total_trades = len(self._trades)
        winning_trades = sum(1 for t in self._trades if t.is_winner)
        losing_trades = total_trades - winning_trades
        
        # Calculate averages
        if winning_trades > 0:
            wins = [t.net_pnl for t in self._trades if t.is_winner]
            average_win = sum(wins) / len(wins)
            largest_win = max(wins)
        else:
            average_win = 0.0
            largest_win = 0.0
        
        if losing_trades > 0:
            losses = [t.net_pnl for t in self._trades if not t.is_winner]
            average_loss = sum(losses) / len(losses)
            largest_loss = min(losses)
        else:
            average_loss = 0.0
            largest_loss = 0.0
        
        # Total P&L
        total_pnl = sum(t.net_pnl for t in self._trades)
        
        return MetricsSnapshot(
            strategy_name=self.strategy_name,
            as_of_date=datetime.now(),
            days_running=self.get_days_running(),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=self.calculate_win_rate(),
            sharpe_ratio=self.calculate_sharpe_ratio(),
            max_drawdown=self.calculate_max_drawdown(),
            profit_factor=self.calculate_profit_factor(),
            consecutive_losses=self._consecutive_losses,
            total_pnl=total_pnl,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss
        )
    
    def get_all_trades(self) -> List[Trade]:
        """Get all recorded trades"""
        return self._trades.copy()
    
    def get_daily_snapshots(self) -> List[DailySnapshot]:
        """Get all daily snapshots"""
        return self._daily_snapshots.copy()
    
    def get_recent_trades(self, count: int = 10) -> List[Trade]:
        """
        Get most recent trades.
        
        Args:
            count: Number of trades to return
            
        Returns:
            List of recent trades
        """
        return self._trades[-count:] if self._trades else []
    
    def clear_all_data(self):
        """Clear all trades and snapshots (for testing)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM strategy_trades WHERE strategy_name = ?", (self.strategy_name,))
        cursor.execute("DELETE FROM strategy_snapshots WHERE strategy_name = ?", (self.strategy_name,))
        cursor.execute("DELETE FROM strategy_metadata WHERE strategy_name = ?", (self.strategy_name,))
        
        conn.commit()
        conn.close()
        
        self._trades.clear()
        self._daily_snapshots.clear()
        self._peak_value = self.initial_capital
        self._max_drawdown = 0.0
        self._consecutive_losses = 0
        self.start_date = date.today()
        
        # Reinitialize metadata
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO strategy_metadata (strategy_name, start_date, initial_capital, peak_value)
            VALUES (?, ?, ?, ?)
        """, (self.strategy_name, self.start_date.isoformat(), self.initial_capital, self._peak_value))
        conn.commit()
        conn.close()
        
        logger.warning(f"Cleared all data for strategy '{self.strategy_name}'")
