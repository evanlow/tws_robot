"""
SQLAlchemy database models for trading system.

Models:
- Trade: Completed trade records with P&L
- Position: Current and historical positions
- Order: Order lifecycle tracking
- Strategy: Strategy configuration and state
- MarketData: Historical price and volume data
- PerformanceMetric: Daily/cumulative performance metrics
"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, 
    Boolean, ForeignKey, Text, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from enum import Enum

Base = declarative_base()


class OrderStatus(str, Enum):
    """Order status values."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionSide(str, Enum):
    """Position side values."""
    LONG = "LONG"
    SHORT = "SHORT"


class Trade(Base):
    """
    Completed trade records with P&L calculation.
    
    Represents a full round-trip trade (entry + exit).
    """
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    
    # Entry details
    entry_time = Column(DateTime, nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    entry_order_id = Column(Integer, nullable=True)
    
    # Exit details
    exit_time = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_order_id = Column(Integer, nullable=True)
    
    # Position details
    quantity = Column(Integer, nullable=False)
    side = Column(SQLEnum(PositionSide), nullable=False)
    
    # P&L calculation
    gross_pnl = Column(Float, nullable=True)
    commission = Column(Float, default=0.0)
    net_pnl = Column(Float, nullable=True)
    pnl_percentage = Column(Float, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    notes = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="trades")
    
    def __repr__(self):
        pnl_value = self.net_pnl if self.net_pnl is not None else 0.0
        return (f"<Trade(id={self.id}, symbol={self.symbol}, "
                f"side={self.side}, qty={self.quantity}, "
                f"pnl=${pnl_value:.2f})>")


class Position(Base):
    """
    Current and historical position records.
    
    Tracks position lifecycle from open to close.
    """
    __tablename__ = 'positions'
    
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    
    # Position details
    quantity = Column(Integer, nullable=False)
    side = Column(SQLEnum(PositionSide), nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    
    # Status
    is_open = Column(Boolean, default=True, index=True)
    opened_at = Column(DateTime, default=datetime.now, index=True)
    closed_at = Column(DateTime, nullable=True)
    
    # P&L tracking
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    extra_data = Column(JSON, nullable=True)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="positions")
    
    def __repr__(self):
        status = "OPEN" if self.is_open else "CLOSED"
        return (f"<Position(id={self.id}, symbol={self.symbol}, "
                f"side={self.side}, qty={self.quantity}, status={status})>")


class Order(Base):
    """
    Order lifecycle tracking.
    
    Records all orders from submission to completion.
    """
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=True)
    
    # Order identification
    ib_order_id = Column(Integer, nullable=False, unique=True, index=True)
    perm_id = Column(Integer, nullable=True)
    
    # Order details
    symbol = Column(String(20), nullable=False, index=True)
    action = Column(String(10), nullable=False)  # BUY, SELL
    order_type = Column(String(20), nullable=False)  # MKT, LMT, STP, etc.
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    
    # Status tracking
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, index=True)
    filled_quantity = Column(Integer, default=0)
    remaining_quantity = Column(Integer, nullable=True)
    avg_fill_price = Column(Float, nullable=True)
    
    # Timestamps
    submitted_at = Column(DateTime, default=datetime.now, index=True)
    filled_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    extra_data = Column(JSON, nullable=True)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="orders")
    
    def __repr__(self):
        return (f"<Order(id={self.ib_order_id}, symbol={self.symbol}, "
                f"action={self.action}, qty={self.quantity}, status={self.status})>")


class Strategy(Base):
    """
    Strategy configuration and state tracking.
    
    Stores strategy parameters, state, and performance.
    """
    __tablename__ = 'strategies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=False, index=True)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    
    # Configuration
    config = Column(JSON, nullable=True)  # Strategy parameters
    
    # Performance tracking
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    trades = relationship("Trade", back_populates="strategy")
    positions = relationship("Position", back_populates="strategy")
    orders = relationship("Order", back_populates="strategy")
    
    def __repr__(self):
        status = "ACTIVE" if self.is_active else "INACTIVE"
        return f"<Strategy(id={self.id}, name={self.name}, status={status})>"


class MarketData(Base):
    """
    Historical market data storage.
    
    Stores OHLCV bars for backtesting and analysis.
    """
    __tablename__ = 'market_data'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    
    # OHLCV data
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    
    # Bar properties
    bar_size = Column(String(20), nullable=False)  # 1min, 5min, 1hour, 1day
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return (f"<MarketData(symbol={self.symbol}, "
                f"time={self.timestamp}, close={self.close})>")


class PerformanceMetric(Base):
    """
    Daily and cumulative performance metrics.
    
    Tracks system-wide and strategy-specific performance.
    """
    __tablename__ = 'performance_metrics'
    
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=True)
    
    # Time period
    date = Column(DateTime, nullable=False, index=True)
    
    # Daily metrics
    daily_pnl = Column(Float, default=0.0)
    daily_return = Column(Float, default=0.0)
    trades_count = Column(Integer, default=0)
    
    # Cumulative metrics
    cumulative_pnl = Column(Float, default=0.0)
    cumulative_return = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    
    # Risk metrics
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return (f"<PerformanceMetric(date={self.date.date()}, "
                f"pnl=${self.daily_pnl:.2f})>")
