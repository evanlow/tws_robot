"""
Strategy Lifecycle Management

Manages the lifecycle states and transitions of trading strategies from
backtesting through paper trading to live deployment.

State Flow:
    BACKTEST → PAPER → VALIDATED → LIVE_APPROVED → LIVE_ACTIVE
    
Any state can transition to PAUSED or RETIRED.
"""

import sqlite3
import logging
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """Strategy lifecycle states"""
    
    BACKTEST = "backtest"           # Testing on historical data
    PAPER = "paper"                 # Running on paper trading account
    VALIDATED = "validated"         # Paper trading validation passed
    LIVE_APPROVED = "live_approved" # Manual approval granted
    LIVE_ACTIVE = "live_active"     # Running on live account
    PAUSED = "paused"               # Temporarily stopped
    RETIRED = "retired"             # Permanently stopped
    
    def __str__(self):
        return self.value


@dataclass
class StrategyMetrics:
    """Metrics for strategy validation"""
    
    days_running: int = 0
    total_trades: int = 0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    consecutive_losses: int = 0
    total_pnl: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategyMetrics':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class ValidationCriteria:
    """Criteria for validating paper trading performance"""
    
    min_days: int = 30
    min_trades: int = 20
    min_sharpe_ratio: float = 1.0
    max_drawdown: float = 0.10      # 10%
    min_win_rate: float = 0.50      # 50%
    min_profit_factor: float = 1.5
    max_consecutive_losses: int = 5
    
    def validate(self, metrics: StrategyMetrics) -> tuple[bool, list[str]]:
        """
        Validate metrics against criteria.
        
        Returns:
            (is_valid, list_of_failures)
        """
        failures = []
        
        if metrics.days_running < self.min_days:
            failures.append(f"Insufficient days: {metrics.days_running} < {self.min_days}")
        
        if metrics.total_trades < self.min_trades:
            failures.append(f"Insufficient trades: {metrics.total_trades} < {self.min_trades}")
        
        if metrics.sharpe_ratio < self.min_sharpe_ratio:
            failures.append(f"Low Sharpe ratio: {metrics.sharpe_ratio:.2f} < {self.min_sharpe_ratio}")
        
        if metrics.max_drawdown > self.max_drawdown:
            failures.append(f"Excessive drawdown: {metrics.max_drawdown:.2%} > {self.max_drawdown:.2%}")
        
        if metrics.win_rate < self.min_win_rate:
            failures.append(f"Low win rate: {metrics.win_rate:.2%} < {self.min_win_rate:.2%}")
        
        if metrics.profit_factor < self.min_profit_factor:
            failures.append(f"Low profit factor: {metrics.profit_factor:.2f} < {self.min_profit_factor}")
        
        if metrics.consecutive_losses > self.max_consecutive_losses:
            failures.append(f"Too many consecutive losses: {metrics.consecutive_losses} > {self.max_consecutive_losses}")
        
        return len(failures) == 0, failures


class StrategyLifecycle:
    """
    Manages strategy lifecycle state transitions and persistence.
    
    Enforces gating logic to ensure strategies progress through proper
    validation before reaching live trading.
    """
    
    # Valid state transitions
    TRANSITIONS = {
        StrategyState.BACKTEST: [StrategyState.PAPER, StrategyState.PAUSED, StrategyState.RETIRED],
        StrategyState.PAPER: [StrategyState.VALIDATED, StrategyState.PAUSED, StrategyState.RETIRED],
        StrategyState.VALIDATED: [StrategyState.LIVE_APPROVED, StrategyState.PAUSED, StrategyState.RETIRED],
        StrategyState.LIVE_APPROVED: [StrategyState.LIVE_ACTIVE, StrategyState.PAUSED, StrategyState.RETIRED],
        StrategyState.LIVE_ACTIVE: [StrategyState.PAUSED, StrategyState.RETIRED],
        StrategyState.PAUSED: [StrategyState.PAPER, StrategyState.LIVE_ACTIVE, StrategyState.RETIRED],
        StrategyState.RETIRED: [],  # Terminal state
    }
    
    def __init__(self, db_path: str = "strategy_lifecycle.db"):
        """
        Initialize lifecycle manager.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._init_database()
        logger.info(f"Initialized StrategyLifecycle with database: {db_path}")
    
    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Strategy state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_state (
                strategy_name TEXT PRIMARY KEY,
                current_state TEXT NOT NULL,
                previous_state TEXT,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metrics_json TEXT,
                notes TEXT
            )
        """)
        
        # State transition history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                reason TEXT,
                approved_by TEXT
            )
        """)

        # Persistent strategy instances (for StrategyRegistry persistence)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_instances (
                name TEXT PRIMARY KEY,
                strategy_type TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database schema initialized")
    
    def register_strategy(self, strategy_name: str, notes: str = "") -> bool:
        """
        Register a new strategy in BACKTEST state.
        
        Args:
            strategy_name: Unique name for the strategy
            notes: Optional notes about the strategy
        
        Returns:
            True if registered, False if already exists
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO strategy_state (
                    strategy_name, current_state, previous_state, 
                    updated_at, created_at, notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (strategy_name, StrategyState.BACKTEST.value, None, now, now, notes))
            
            conn.commit()
            logger.info(f"Registered strategy '{strategy_name}' in BACKTEST state")
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"Strategy '{strategy_name}' already registered")
            return False
        finally:
            conn.close()
    
    def get_state(self, strategy_name: str) -> Optional[StrategyState]:
        """
        Get current state of a strategy.
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            Current StrategyState or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT current_state FROM strategy_state WHERE strategy_name = ?",
            (strategy_name,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return StrategyState(row[0])
        return None
    
    def get_metrics(self, strategy_name: str) -> Optional[StrategyMetrics]:
        """
        Get strategy metrics.
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            StrategyMetrics or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT metrics_json FROM strategy_state WHERE strategy_name = ?",
            (strategy_name,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            import json
            return StrategyMetrics.from_dict(json.loads(row[0]))
        return StrategyMetrics()  # Return empty metrics if none stored
    
    def update_metrics(self, strategy_name: str, metrics: StrategyMetrics) -> bool:
        """
        Update strategy metrics.
        
        Args:
            strategy_name: Name of the strategy
            metrics: Updated metrics
        
        Returns:
            True if updated successfully
        """
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE strategy_state 
                SET metrics_json = ?, updated_at = ?
                WHERE strategy_name = ?
            """, (json.dumps(metrics.to_dict()), datetime.now().isoformat(), strategy_name))
            
            conn.commit()
            success = cursor.rowcount > 0
            
            if success:
                logger.info(f"Updated metrics for strategy '{strategy_name}'")
            else:
                logger.warning(f"Strategy '{strategy_name}' not found for metrics update")
            
            return success
            
        finally:
            conn.close()
    
    def can_transition(self, strategy_name: str, to_state: StrategyState) -> tuple[bool, str]:
        """
        Check if transition is allowed.
        
        Args:
            strategy_name: Name of the strategy
            to_state: Target state
        
        Returns:
            (is_allowed, reason)
        """
        current_state = self.get_state(strategy_name)
        
        if current_state is None:
            return False, f"Strategy '{strategy_name}' not found"
        
        if current_state == to_state:
            return False, f"Already in {to_state} state"
        
        if to_state not in self.TRANSITIONS[current_state]:
            return False, f"Invalid transition: {current_state} → {to_state}"
        
        # Special validation for PAPER → VALIDATED transition
        if current_state == StrategyState.PAPER and to_state == StrategyState.VALIDATED:
            metrics = self.get_metrics(strategy_name)
            criteria = ValidationCriteria()
            is_valid, failures = criteria.validate(metrics)
            
            if not is_valid:
                reason = "Validation criteria not met:\n" + "\n".join(f"  - {f}" for f in failures)
                return False, reason
        
        return True, "Transition allowed"
    
    def transition(
        self, 
        strategy_name: str, 
        to_state: StrategyState,
        reason: str = "",
        approved_by: str = ""
    ) -> bool:
        """
        Transition strategy to new state.
        
        Args:
            strategy_name: Name of the strategy
            to_state: Target state
            reason: Reason for transition
            approved_by: Who approved (for LIVE transitions)
        
        Returns:
            True if transition successful
        """
        can_transition, transition_reason = self.can_transition(strategy_name, to_state)
        
        if not can_transition:
            logger.error(f"Transition denied for '{strategy_name}': {transition_reason}")
            return False
        
        current_state = self.get_state(strategy_name)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            now = datetime.now().isoformat()
            
            # Update strategy state
            cursor.execute("""
                UPDATE strategy_state
                SET current_state = ?, previous_state = ?, updated_at = ?
                WHERE strategy_name = ?
            """, (to_state.value, current_state.value, now, strategy_name))
            
            # Record transition history
            cursor.execute("""
                INSERT INTO state_transitions (
                    strategy_name, from_state, to_state, timestamp, reason, approved_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (strategy_name, current_state.value, to_state.value, now, reason, approved_by))
            
            conn.commit()
            logger.info(f"Strategy '{strategy_name}' transitioned: {current_state} → {to_state}")
            return True
            
        except Exception as e:
            logger.error(f"Transition failed: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_history(self, strategy_name: str) -> list[Dict[str, Any]]:
        """
        Get state transition history for a strategy.
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            List of transition records
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT from_state, to_state, timestamp, reason, approved_by
            FROM state_transitions
            WHERE strategy_name = ?
            ORDER BY timestamp ASC
        """, (strategy_name,))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                'from_state': row[0],
                'to_state': row[1],
                'timestamp': row[2],
                'reason': row[3],
                'approved_by': row[4]
            })
        
        conn.close()
        return history
    
    def save_strategy_instance(
        self,
        name: str,
        strategy_type: str,
        symbols: list,
        parameters: Dict[str, Any],
    ) -> bool:
        """
        Persist a strategy instance so it can be restored after a restart.

        If a record with the same name already exists it is updated in place
        (UPSERT), keeping the in-memory registry and the database in sync even
        when a strategy is recreated with different symbols or parameters.

        Args:
            name: Strategy instance name (unique key)
            strategy_type: Registered strategy type string (e.g. "BollingerBands")
            symbols: List of trading symbols
            parameters: Strategy-specific parameters dict

        Returns:
            True on success
        """
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO strategy_instances
                    (name, strategy_type, symbols_json, parameters_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    strategy_type  = excluded.strategy_type,
                    symbols_json   = excluded.symbols_json,
                    parameters_json = excluded.parameters_json
                """,
                (
                    name,
                    strategy_type,
                    json.dumps(symbols),
                    json.dumps(parameters),
                    now,
                ),
            )
            conn.commit()
            logger.info(f"Persisted strategy instance '{name}' (type: {strategy_type})")
            return True
        finally:
            conn.close()

    def delete_strategy_instance(self, name: str) -> bool:
        """
        Remove a persisted strategy instance record.

        Args:
            name: Strategy instance name

        Returns:
            True if a record was deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM strategy_instances WHERE name = ?",
                (name,),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted persisted strategy instance '{name}'")
            else:
                logger.warning(f"No persisted record found for strategy '{name}'")
            return deleted
        finally:
            conn.close()

    def load_strategy_instances(self) -> list[Dict[str, Any]]:
        """
        Load all persisted strategy instances from the database.

        Returns:
            List of dicts with keys: name, strategy_type, symbols, parameters, created_at
        """
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, strategy_type, symbols_json, parameters_json, created_at
            FROM strategy_instances
            ORDER BY created_at ASC
            """
        )
        rows = cursor.fetchall()
        conn.close()

        instances = []
        for row in rows:
            try:
                instances.append(
                    {
                        "name": row[0],
                        "strategy_type": row[1],
                        "symbols": json.loads(row[2]),
                        "parameters": json.loads(row[3]),
                        "created_at": row[4],
                    }
                )
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping persisted strategy instance '%s' due to invalid JSON: %s",
                    row[0],
                    exc,
                )
        return instances

    def list_strategies(self, state: Optional[StrategyState] = None) -> list[Dict[str, Any]]:
        """
        List all strategies, optionally filtered by state.
        
        Args:
            state: Filter by this state (None for all)
        
        Returns:
            List of strategy info dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if state:
            cursor.execute("""
                SELECT strategy_name, current_state, updated_at, created_at, notes
                FROM strategy_state
                WHERE current_state = ?
                ORDER BY strategy_name
            """, (state.value,))
        else:
            cursor.execute("""
                SELECT strategy_name, current_state, updated_at, created_at, notes
                FROM strategy_state
                ORDER BY strategy_name
            """)
        
        strategies = []
        for row in cursor.fetchall():
            strategies.append({
                'name': row[0],
                'state': row[1],
                'updated_at': row[2],
                'created_at': row[3],
                'notes': row[4]
            })
        
        conn.close()
        return strategies
