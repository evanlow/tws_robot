"""
Database connection and session management using SQLAlchemy.

Provides thread-safe database access with connection pooling
and session management for the trading system.

Usage:
    db = get_database()
    
    # Create tables
    db.create_tables()
    
    # Use session context
    with db.session_scope() as session:
        trade = Trade(symbol="AAPL", quantity=100, ...)
        session.add(trade)
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import logging
from typing import Optional
import os

try:
    from .models import Base
except ImportError:
    from models import Base

logger = logging.getLogger(__name__)


class Database:
    """
    Database connection manager with SQLAlchemy.
    
    Features:
    - Connection pooling for performance
    - Thread-safe session management
    - Automatic table creation
    - Context manager for transactions
    """
    
    def __init__(self, database_url: Optional[str] = None, echo: bool = False):
        """
        Initialize database connection.
        
        Args:
            database_url: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
                If None, reads from DATABASE_URL environment variable
            echo: If True, log all SQL statements (useful for debugging)
        """
        if database_url is None:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                # Default to SQLite for development if no PostgreSQL URL
                database_url = 'sqlite:///tws_robot.db'
                logger.warning("No DATABASE_URL found, using SQLite: tws_robot.db")
        
        self.database_url = database_url
        self.echo = echo
        
        # Create engine with connection pooling
        if database_url.startswith('postgresql') or database_url.startswith('mysql'):
            self.engine = create_engine(
                database_url,
                echo=echo,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # Verify connections before using
                pool_recycle=3600,   # Recycle connections after 1 hour
            )
        else:
            # SQLite configuration
            self.engine = create_engine(
                database_url,
                echo=echo,
                connect_args={'check_same_thread': False}  # For SQLite
            )
        
        # Create session factory
        session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(session_factory)
        
        logger.info(f"Database initialized: {self._mask_password(database_url)}")
    
    def _mask_password(self, url: str) -> str:
        """Mask password in database URL for logging."""
        if '://' in url and '@' in url:
            protocol, rest = url.split('://', 1)
            if '@' in rest:
                credentials, host = rest.split('@', 1)
                if ':' in credentials:
                    user, _ = credentials.split(':', 1)
                    return f"{protocol}://{user}:****@{host}"
        return url
    
    def create_tables(self):
        """Create all tables defined in models."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")
    
    def drop_tables(self):
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(self.engine)
        logger.warning("Database tables dropped")
    
    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope for database operations.
        
        Usage:
            with db.session_scope() as session:
                trade = Trade(...)
                session.add(trade)
                # Automatic commit on success
                # Automatic rollback on exception
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            session.close()
    
    def get_session(self) -> Session:
        """
        Get a new session (remember to close it manually).
        
        Prefer using session_scope() context manager instead.
        """
        return self.Session()
    
    def close(self):
        """Close database connections."""
        self.Session.remove()
        self.engine.dispose()
        logger.info("Database connections closed")
    
    def execute_raw_sql(self, sql: str):
        """
        Execute raw SQL statement (use with caution).
        
        Args:
            sql: SQL statement to execute
        """
        with self.engine.connect() as conn:
            result = conn.execute(sql)
            conn.commit()
            return result


# Global database instance
_global_database: Optional[Database] = None


def get_database(database_url: Optional[str] = None, echo: bool = False) -> Database:
    """
    Get or create the global database instance (singleton pattern).
    
    Args:
        database_url: PostgreSQL connection string (only used on first call)
        echo: Log SQL statements (only used on first call)
    
    Returns:
        The global Database instance
    """
    global _global_database
    if _global_database is None:
        _global_database = Database(database_url=database_url, echo=echo)
    return _global_database


def reset_database():
    """Reset the global database instance (useful for testing)."""
    global _global_database
    if _global_database:
        _global_database.close()
    _global_database = None


if __name__ == "__main__":
    # Example usage
    from datetime import datetime
    logging.basicConfig(level=logging.INFO)
    
    # Use SQLite for testing
    db = Database('sqlite:///test.db', echo=True)
    
    # Create tables
    db.create_tables()
    
    # Import models
    try:
        from .models import Trade, Strategy, PositionSide
    except ImportError:
        from models import Trade, Strategy, PositionSide
    
    # Create a strategy
    with db.session_scope() as session:
        strategy = Strategy(
            name="Test Strategy",
            description="A test strategy",
            config={"param1": 100, "param2": 0.5}
        )
        session.add(strategy)
    
    # Create a trade
    with db.session_scope() as session:
        # Query the strategy
        strategy = session.query(Strategy).filter_by(name="Test Strategy").first()
        
        trade = Trade(
            strategy_id=strategy.id,
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=150.0,
            quantity=100,
            side=PositionSide.LONG,
            exit_price=155.0,
            gross_pnl=500.0,
            commission=2.0,
            net_pnl=498.0
        )
        session.add(trade)
    
    # Query trades
    with db.session_scope() as session:
        trades = session.query(Trade).all()
        print(f"\nTrades: {len(trades)}")
        for trade in trades:
            print(f"  {trade}")
    
    # Cleanup
    db.close()
    print("\nDatabase connection closed")
