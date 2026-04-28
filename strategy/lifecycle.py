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
                strategy_name TEXT NOT NULL,
                account_id TEXT NOT NULL DEFAULT '',
                current_state TEXT NOT NULL,
                previous_state TEXT,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metrics_json TEXT,
                notes TEXT,
                PRIMARY KEY (strategy_name, account_id)
            )
        """)
        
        # State transition history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                account_id TEXT NOT NULL DEFAULT '',
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
                name TEXT NOT NULL,
                account_id TEXT NOT NULL DEFAULT '',
                strategy_type TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                running_state TEXT NOT NULL DEFAULT 'READY',
                PRIMARY KEY (name, account_id)
            )
        """)

        conn.commit()

        # --- Zero-downtime migration for legacy databases -------------------
        # Phase 1: add missing columns to any table that doesn't yet have them.
        # SQLite does not support "IF NOT EXISTS" on ALTER TABLE; use try/except.
        # SECURITY: table names come from a hardcoded whitelist only.
        _allowed_tables = {"strategy_state", "state_transitions", "strategy_instances"}
        for table, column in [
            ("strategy_state", "account_id TEXT NOT NULL DEFAULT ''"),
            ("state_transitions", "account_id TEXT NOT NULL DEFAULT ''"),
            ("strategy_instances", "account_id TEXT NOT NULL DEFAULT ''"),
            ("strategy_instances", "running_state TEXT NOT NULL DEFAULT 'READY'"),
        ]:
            if table not in _allowed_tables:
                raise ValueError(f"Unexpected table name: {table!r}")
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column}")  # noqa: S608
                conn.commit()
                logger.info(f"Migrated: added account_id column to {table}")
            except sqlite3.OperationalError:
                # Column already exists — expected on fresh or already-migrated DBs
                pass

        # Phase 2: rebuild strategy_state and strategy_instances if they still
        # carry the legacy single-column primary key.  On a fresh DB the CREATE
        # TABLE IF NOT EXISTS above already produced the correct composite PK, so
        # PRAGMA table_info will report len(pk_cols) == 2 and no rebuild happens.
        # On a legacy DB that was just column-migrated the PK is still single-
        # column, so the ON CONFLICT(name, account_id) in the UPSERT would fail
        # without this step.
        _rebuild_specs = [
            (
                "strategy_state",
                """CREATE TABLE strategy_state (
                    strategy_name TEXT NOT NULL,
                    account_id TEXT NOT NULL DEFAULT '',
                    current_state TEXT NOT NULL,
                    previous_state TEXT,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metrics_json TEXT,
                    notes TEXT,
                    PRIMARY KEY (strategy_name, account_id)
                )""",
                ("strategy_name, account_id, current_state, previous_state,"
                 " updated_at, created_at, metrics_json, notes"),
            ),
            (
                "strategy_instances",
                """CREATE TABLE strategy_instances (
                    name TEXT NOT NULL,
                    account_id TEXT NOT NULL DEFAULT '',
                    strategy_type TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    running_state TEXT NOT NULL DEFAULT 'READY',
                    PRIMARY KEY (name, account_id)
                )""",
                "name, account_id, strategy_type, symbols_json, parameters_json, created_at",
            ),
        ]
        for table, new_ddl, cols in _rebuild_specs:
            cursor.execute(f"PRAGMA table_info({table})")  # noqa: S608
            pk_cols = [row[1] for row in cursor.fetchall() if row[5] > 0]
            if len(pk_cols) >= 2:
                continue  # Already has composite PK — no rebuild needed
            # Legacy single-column PK: rename, recreate, copy, drop old.
            tmp = f"_{table}_legacy_tmp"
            cursor.execute(f"ALTER TABLE {table} RENAME TO {tmp}")  # noqa: S608
            cursor.execute(new_ddl)
            cursor.execute(
                f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {tmp}"  # noqa: S608
            )
            cursor.execute(f"DROP TABLE {tmp}")  # noqa: S608
            conn.commit()
            logger.info(f"Migration: rebuilt {table} with composite primary key")

        conn.close()
        logger.info("Database schema initialized")
    
    def register_strategy(self, strategy_name: str, notes: str = "",
                          account_id: str = "") -> bool:
        """
        Register a new strategy in BACKTEST state.
        
        Args:
            strategy_name: Unique name for the strategy
            notes: Optional notes about the strategy
            account_id: IBKR account identifier this strategy belongs to
        
        Returns:
            True if registered, False if already exists
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO strategy_state (
                    strategy_name, account_id, current_state, previous_state, 
                    updated_at, created_at, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (strategy_name, account_id, StrategyState.BACKTEST.value, None,
                  now, now, notes))
            
            conn.commit()
            logger.info(f"Registered strategy '{strategy_name}' (account: '{account_id}') in BACKTEST state")
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"Strategy '{strategy_name}' already registered for account '{account_id}'")
            return False
        finally:
            conn.close()
    
    def get_state(self, strategy_name: str,
                  account_id: str = "") -> Optional[StrategyState]:
        """
        Get current state of a strategy.
        
        Args:
            strategy_name: Name of the strategy
            account_id: IBKR account identifier (empty string matches legacy rows)
        
        Returns:
            Current StrategyState or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT current_state FROM strategy_state "
            "WHERE strategy_name = ? AND account_id = ?",
            (strategy_name, account_id)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return StrategyState(row[0])
        return None
    
    def get_metrics(self, strategy_name: str,
                    account_id: str = "") -> Optional[StrategyMetrics]:
        """
        Get strategy metrics.
        
        Args:
            strategy_name: Name of the strategy
            account_id: IBKR account identifier
        
        Returns:
            StrategyMetrics or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT metrics_json FROM strategy_state "
            "WHERE strategy_name = ? AND account_id = ?",
            (strategy_name, account_id)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            import json
            return StrategyMetrics.from_dict(json.loads(row[0]))
        return StrategyMetrics()  # Return empty metrics if none stored
    
    def update_metrics(self, strategy_name: str, metrics: StrategyMetrics,
                       account_id: str = "") -> bool:
        """
        Update strategy metrics.
        
        Args:
            strategy_name: Name of the strategy
            metrics: Updated metrics
            account_id: IBKR account identifier
        
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
                WHERE strategy_name = ? AND account_id = ?
            """, (json.dumps(metrics.to_dict()), datetime.now().isoformat(),
                  strategy_name, account_id))
            
            conn.commit()
            success = cursor.rowcount > 0
            
            if success:
                logger.info(f"Updated metrics for strategy '{strategy_name}'")
            else:
                logger.warning(f"Strategy '{strategy_name}' not found for metrics update")
            
            return success
            
        finally:
            conn.close()
    
    def can_transition(self, strategy_name: str, to_state: StrategyState,
                       account_id: str = "") -> tuple[bool, str]:
        """
        Check if transition is allowed.
        
        Args:
            strategy_name: Name of the strategy
            to_state: Target state
            account_id: IBKR account identifier
        
        Returns:
            (is_allowed, reason)
        """
        current_state = self.get_state(strategy_name, account_id)
        
        if current_state is None:
            return False, f"Strategy '{strategy_name}' not found"
        
        if current_state == to_state:
            return False, f"Already in {to_state} state"
        
        if to_state not in self.TRANSITIONS[current_state]:
            return False, f"Invalid transition: {current_state} → {to_state}"
        
        # Special validation for PAPER → VALIDATED transition
        if current_state == StrategyState.PAPER and to_state == StrategyState.VALIDATED:
            metrics = self.get_metrics(strategy_name, account_id)
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
        approved_by: str = "",
        account_id: str = ""
    ) -> bool:
        """
        Transition strategy to new state.
        
        Args:
            strategy_name: Name of the strategy
            to_state: Target state
            reason: Reason for transition
            approved_by: Who approved (for LIVE transitions)
            account_id: IBKR account identifier
        
        Returns:
            True if transition successful
        """
        can_transition, transition_reason = self.can_transition(strategy_name, to_state, account_id)
        
        if not can_transition:
            logger.error(f"Transition denied for '{strategy_name}': {transition_reason}")
            return False
        
        current_state = self.get_state(strategy_name, account_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            now = datetime.now().isoformat()
            
            # Update strategy state
            cursor.execute("""
                UPDATE strategy_state
                SET current_state = ?, previous_state = ?, updated_at = ?
                WHERE strategy_name = ? AND account_id = ?
            """, (to_state.value, current_state.value, now, strategy_name, account_id))
            
            # Record transition history
            cursor.execute("""
                INSERT INTO state_transitions (
                    strategy_name, account_id, from_state, to_state,
                    timestamp, reason, approved_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (strategy_name, account_id, current_state.value, to_state.value,
                  now, reason, approved_by))
            
            conn.commit()
            logger.info(f"Strategy '{strategy_name}' transitioned: {current_state} → {to_state}")
            return True
            
        except Exception as e:
            logger.error(f"Transition failed: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_history(self, strategy_name: str,
                    account_id: str = "") -> list[Dict[str, Any]]:
        """
        Get state transition history for a strategy.
        
        Args:
            strategy_name: Name of the strategy
            account_id: IBKR account identifier
        
        Returns:
            List of transition records
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT from_state, to_state, timestamp, reason, approved_by
            FROM state_transitions
            WHERE strategy_name = ? AND account_id = ?
            ORDER BY timestamp ASC
        """, (strategy_name, account_id))
        
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
        account_id: str = "",
    ) -> bool:
        """
        Persist a strategy instance so it can be restored after a restart.

        If a record with the same (name, account_id) already exists it is
        updated in place (UPSERT), keeping the in-memory registry and the
        database in sync even when a strategy is recreated with different
        symbols or parameters.

        Args:
            name: Strategy instance name
            strategy_type: Registered strategy type string (e.g. "BollingerBands")
            symbols: List of trading symbols
            parameters: Strategy-specific parameters dict
            account_id: IBKR account identifier this instance belongs to

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
                    (name, account_id, strategy_type, symbols_json,
                     parameters_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, account_id) DO UPDATE SET
                    strategy_type   = excluded.strategy_type,
                    symbols_json    = excluded.symbols_json,
                    parameters_json = excluded.parameters_json
                """,
                (
                    name,
                    account_id,
                    strategy_type,
                    json.dumps(symbols),
                    json.dumps(parameters),
                    now,
                ),
            )
            conn.commit()
            logger.info(
                f"Persisted strategy instance '{name}' "
                f"(type: {strategy_type}, account: '{account_id}')"
            )
            return True
        finally:
            conn.close()

    def update_instance_running_state(
        self,
        name: str,
        running_state: str,
        account_id: str = "",
    ) -> bool:
        """
        Update the persisted running state for a strategy instance.

        Called whenever a strategy is started, stopped, or paused so that
        the state survives application restarts.

        Args:
            name: Strategy instance name
            running_state: New running state value (e.g. ``'RUNNING'``,
                ``'STOPPED'``, ``'PAUSED'``, ``'READY'``)
            account_id: IBKR account identifier

        Returns:
            True if the record was updated, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE strategy_instances SET running_state = ? "
                "WHERE name = ? AND account_id = ?",
                (running_state, name, account_id),
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.debug(
                    f"Updated running_state for strategy '{name}' "
                    f"(account: '{account_id}') to '{running_state}'"
                )
            else:
                logger.warning(
                    f"No persisted record found for strategy '{name}' "
                    f"(account: '{account_id}') when updating running_state"
                )
            return updated
        finally:
            conn.close()

    def delete_strategy_instance(self, name: str,
                                 account_id: str = "") -> bool:
        """
        Remove a persisted strategy instance record.

        Args:
            name: Strategy instance name
            account_id: IBKR account identifier

        Returns:
            True if a record was deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM strategy_instances WHERE name = ? AND account_id = ?",
                (name, account_id),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted persisted strategy instance '{name}' (account: '{account_id}')")
            else:
                logger.warning(
                    f"No persisted record found for strategy '{name}' (account: '{account_id}')"
                )
            return deleted
        finally:
            conn.close()

    def load_strategy_instances(self,
                                account_id: Optional[str] = None) -> list[Dict[str, Any]]:
        """
        Load persisted strategy instances from the database.

        Args:
            account_id: When provided, only instances belonging to this account
                are returned.  When ``None``, all instances are returned
                (intended for admin/migration use only).

        Returns:
            List of dicts with keys: name, account_id, strategy_type, symbols,
            parameters, created_at, running_state
        """
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if account_id is not None:
            cursor.execute(
                """
                SELECT name, account_id, strategy_type, symbols_json,
                       parameters_json, created_at, running_state
                FROM strategy_instances
                WHERE account_id = ?
                ORDER BY created_at ASC
                """,
                (account_id,),
            )
        else:
            cursor.execute(
                """
                SELECT name, account_id, strategy_type, symbols_json,
                       parameters_json, created_at, running_state
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
                        "account_id": row[1],
                        "strategy_type": row[2],
                        "symbols": json.loads(row[3]),
                        "parameters": json.loads(row[4]),
                        "created_at": row[5],
                        "running_state": row[6],
                    }
                )
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping persisted strategy instance '%s' due to invalid JSON: %s",
                    row[0],
                    exc,
                )
        return instances

    def list_strategies(self, state: Optional[StrategyState] = None,
                        account_id: Optional[str] = None) -> list[Dict[str, Any]]:
        """
        List all strategies, optionally filtered by state and/or account.
        
        Args:
            state: Filter by this state (None for all states)
            account_id: Filter by this account (None for all accounts)
        
        Returns:
            List of strategy info dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        conditions = []
        params: list = []
        if state is not None:
            conditions.append("current_state = ?")
            params.append(state.value)
        if account_id is not None:
            conditions.append("account_id = ?")
            params.append(account_id)

        if conditions:
            query = (
                "SELECT strategy_name, account_id, current_state, updated_at,"
                " created_at, notes"
                " FROM strategy_state"
                " WHERE " + " AND ".join(conditions) +
                " ORDER BY strategy_name"
            )
        else:
            query = (
                "SELECT strategy_name, account_id, current_state, updated_at,"
                " created_at, notes"
                " FROM strategy_state"
                " ORDER BY strategy_name"
            )

        cursor.execute(query, params)
        
        strategies = []
        for row in cursor.fetchall():
            strategies.append({
                'name': row[0],
                'account_id': row[1],
                'state': row[2],
                'updated_at': row[3],
                'created_at': row[4],
                'notes': row[5],
            })
        
        conn.close()
        return strategies
