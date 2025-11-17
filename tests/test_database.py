"""
Unit tests for Database module.

Tests SQLAlchemy models, database operations, and session management.
Uses SQLite in-memory database for testing.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.database import Database
from data.models import (
    Base, Trade, Position, Order, Strategy,
    MarketData, PerformanceMetric,
    OrderStatus, PositionSide
)


@pytest.fixture
def db():
    """Create in-memory SQLite database for testing."""
    database = Database('sqlite:///:memory:', echo=False)
    database.create_tables()
    yield database
    database.close()


@pytest.fixture
def test_strategy(db):
    """Create a test strategy."""
    with db.session_scope() as session:
        strategy = Strategy(
            name="Test Strategy",
            description="A test strategy for unit tests",
            config={"param1": 100, "param2": 0.5}
        )
        session.add(strategy)
        session.flush()
        strategy_id = strategy.id
    
    return strategy_id


class TestDatabaseModels:
    """Test database models."""
    
    @pytest.mark.unit
    def test_create_strategy(self, db):
        """Test creating a strategy."""
        with db.session_scope() as session:
            strategy = Strategy(
                name="Test Strategy 1",
                description="Test description",
                is_active=True,
                config={"stop_loss": 0.02, "take_profit": 0.05}
            )
            session.add(strategy)
            session.flush()
            
            assert strategy.id is not None
            assert strategy.name == "Test Strategy 1"
            assert strategy.is_active is True
            assert strategy.total_trades == 0
            assert strategy.config["stop_loss"] == 0.02
    
    @pytest.mark.unit
    def test_create_trade(self, db, test_strategy):
        """Test creating a trade."""
        with db.session_scope() as session:
            trade = Trade(
                strategy_id=test_strategy,
                symbol="AAPL",
                entry_time=datetime.now(),
                entry_price=150.0,
                quantity=100,
                side=PositionSide.LONG,
                exit_price=155.0,
                gross_pnl=500.0,
                commission=2.0,
                net_pnl=498.0,
                pnl_percentage=3.32
            )
            session.add(trade)
            session.flush()
            
            assert trade.id is not None
            assert trade.symbol == "AAPL"
            assert trade.quantity == 100
            assert trade.net_pnl == 498.0
    
    @pytest.mark.unit
    def test_create_position(self, db, test_strategy):
        """Test creating a position."""
        with db.session_scope() as session:
            position = Position(
                strategy_id=test_strategy,
                symbol="GOOGL",
                quantity=50,
                side=PositionSide.LONG,
                avg_entry_price=295.0,
                current_price=300.0,
                is_open=True,
                unrealized_pnl=250.0
            )
            session.add(position)
            session.flush()
            
            assert position.id is not None
            assert position.symbol == "GOOGL"
            assert position.is_open is True
            assert position.unrealized_pnl == 250.0
    
    @pytest.mark.unit
    def test_create_order(self, db, test_strategy):
        """Test creating an order."""
        with db.session_scope() as session:
            order = Order(
                strategy_id=test_strategy,
                ib_order_id=12345,
                symbol="MSFT",
                action="BUY",
                order_type="LMT",
                quantity=100,
                limit_price=380.0,
                status=OrderStatus.SUBMITTED,
                remaining_quantity=100
            )
            session.add(order)
            session.flush()
            
            assert order.id is not None
            assert order.ib_order_id == 12345
            assert order.status == OrderStatus.SUBMITTED
    
    @pytest.mark.unit
    def test_strategy_relationships(self, db, test_strategy):
        """Test strategy relationships with trades and orders."""
        with db.session_scope() as session:
            # Create trade
            trade = Trade(
                strategy_id=test_strategy,
                symbol="AAPL",
                entry_time=datetime.now(),
                entry_price=150.0,
                quantity=100,
                side=PositionSide.LONG
            )
            session.add(trade)
            
            # Create order
            order = Order(
                strategy_id=test_strategy,
                ib_order_id=123,
                symbol="AAPL",
                action="BUY",
                order_type="MKT",
                quantity=100,
                status=OrderStatus.FILLED
            )
            session.add(order)
            session.flush()
        
        # Query strategy and check relationships
        with db.session_scope() as session:
            strategy = session.query(Strategy).filter_by(id=test_strategy).first()
            
            assert len(strategy.trades) == 1
            assert strategy.trades[0].symbol == "AAPL"
            assert len(strategy.orders) == 1
            assert strategy.orders[0].ib_order_id == 123
    
    @pytest.mark.unit
    def test_market_data(self, db):
        """Test creating market data."""
        with db.session_scope() as session:
            bar = MarketData(
                symbol="SPY",
                timestamp=datetime.now(),
                open=450.0,
                high=452.0,
                low=449.0,
                close=451.5,
                volume=1000000,
                bar_size="1min"
            )
            session.add(bar)
            session.flush()
            
            assert bar.id is not None
            assert bar.symbol == "SPY"
            assert bar.close == 451.5
    
    @pytest.mark.unit
    def test_performance_metric(self, db, test_strategy):
        """Test creating performance metrics."""
        with db.session_scope() as session:
            metric = PerformanceMetric(
                strategy_id=test_strategy,
                date=datetime.now(),
                daily_pnl=1250.0,
                daily_return=2.5,
                trades_count=5,
                cumulative_pnl=5000.0,
                win_rate=0.6,
                sharpe_ratio=1.8
            )
            session.add(metric)
            session.flush()
            
            assert metric.id is not None
            assert metric.daily_pnl == 1250.0
            assert metric.win_rate == 0.6


class TestDatabaseOperations:
    """Test database operations."""
    
    @pytest.mark.unit
    def test_session_scope_commit(self, db):
        """Test that session_scope commits on success."""
        with db.session_scope() as session:
            strategy = Strategy(name="Commit Test")
            session.add(strategy)
        
        # Verify it was committed
        with db.session_scope() as session:
            result = session.query(Strategy).filter_by(name="Commit Test").first()
            assert result is not None
    
    @pytest.mark.unit
    def test_session_scope_rollback(self, db):
        """Test that session_scope rolls back on error."""
        try:
            with db.session_scope() as session:
                strategy = Strategy(name="Rollback Test")
                session.add(strategy)
                raise ValueError("Intentional error")
        except ValueError:
            pass
        
        # Verify it was rolled back
        with db.session_scope() as session:
            result = session.query(Strategy).filter_by(name="Rollback Test").first()
            assert result is None
    
    @pytest.mark.unit
    def test_query_filter(self, db, test_strategy):
        """Test querying with filters."""
        # Create multiple trades
        with db.session_scope() as session:
            for i in range(5):
                trade = Trade(
                    strategy_id=test_strategy,
                    symbol="AAPL" if i % 2 == 0 else "GOOGL",
                    entry_time=datetime.now(),
                    entry_price=150.0 + i,
                    quantity=100,
                    side=PositionSide.LONG
                )
                session.add(trade)
        
        # Query AAPL trades only
        with db.session_scope() as session:
            aapl_trades = session.query(Trade).filter_by(symbol="AAPL").all()
            assert len(aapl_trades) == 3
            assert all(t.symbol == "AAPL" for t in aapl_trades)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
