"""
Unit tests for strategy lifecycle management.

Tests state transitions, validation criteria, and persistence.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime

from strategy.lifecycle import (
    StrategyState,
    StrategyLifecycle,
    StrategyMetrics,
    ValidationCriteria
)


class TestStrategyState:
    """Test StrategyState enum"""
    
    def test_state_values(self):
        """Test all state values are defined"""
        assert StrategyState.BACKTEST.value == "backtest"
        assert StrategyState.PAPER.value == "paper"
        assert StrategyState.VALIDATED.value == "validated"
        assert StrategyState.LIVE_APPROVED.value == "live_approved"
        assert StrategyState.LIVE_ACTIVE.value == "live_active"
        assert StrategyState.PAUSED.value == "paused"
        assert StrategyState.RETIRED.value == "retired"
    
    def test_state_string_representation(self):
        """Test string conversion"""
        assert str(StrategyState.BACKTEST) == "backtest"
        assert str(StrategyState.PAPER) == "paper"


class TestStrategyMetrics:
    """Test StrategyMetrics dataclass"""
    
    def test_metrics_initialization(self):
        """Test metrics can be created with defaults"""
        metrics = StrategyMetrics()
        assert metrics.days_running == 0
        assert metrics.total_trades == 0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown == 0.0
    
    def test_metrics_with_values(self):
        """Test metrics with custom values"""
        metrics = StrategyMetrics(
            days_running=45,
            total_trades=50,
            sharpe_ratio=1.8,
            max_drawdown=0.08,
            win_rate=0.60,
            profit_factor=2.1
        )
        assert metrics.days_running == 45
        assert metrics.sharpe_ratio == 1.8
        assert metrics.win_rate == 0.60
    
    def test_metrics_to_dict(self):
        """Test conversion to dictionary"""
        metrics = StrategyMetrics(days_running=30, total_trades=25)
        data = metrics.to_dict()
        assert isinstance(data, dict)
        assert data['days_running'] == 30
        assert data['total_trades'] == 25
    
    def test_metrics_from_dict(self):
        """Test creation from dictionary"""
        data = {'days_running': 40, 'total_trades': 30, 'sharpe_ratio': 1.5}
        metrics = StrategyMetrics.from_dict(data)
        assert metrics.days_running == 40
        assert metrics.total_trades == 30
        assert metrics.sharpe_ratio == 1.5


class TestValidationCriteria:
    """Test ValidationCriteria"""
    
    def test_default_criteria(self):
        """Test default validation criteria"""
        criteria = ValidationCriteria()
        assert criteria.min_days == 30
        assert criteria.min_trades == 20
        assert criteria.min_sharpe_ratio == 1.0
        assert criteria.max_drawdown == 0.10
    
    def test_validation_pass(self):
        """Test validation with passing metrics"""
        criteria = ValidationCriteria()
        metrics = StrategyMetrics(
            days_running=35,
            total_trades=25,
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            win_rate=0.55,
            profit_factor=2.0,
            consecutive_losses=3
        )
        
        is_valid, failures = criteria.validate(metrics)
        assert is_valid is True
        assert len(failures) == 0
    
    def test_validation_fail_days(self):
        """Test validation fails on insufficient days"""
        criteria = ValidationCriteria()
        metrics = StrategyMetrics(days_running=10)
        
        is_valid, failures = criteria.validate(metrics)
        assert is_valid is False
        assert any("days" in f.lower() for f in failures)
    
    def test_validation_fail_sharpe(self):
        """Test validation fails on low Sharpe ratio"""
        criteria = ValidationCriteria()
        metrics = StrategyMetrics(
            days_running=35,
            total_trades=25,
            sharpe_ratio=0.5,  # Below minimum
            max_drawdown=0.08,
            win_rate=0.55,
            profit_factor=2.0
        )
        
        is_valid, failures = criteria.validate(metrics)
        assert is_valid is False
        assert any("sharpe" in f.lower() for f in failures)
    
    def test_validation_fail_drawdown(self):
        """Test validation fails on excessive drawdown"""
        criteria = ValidationCriteria()
        metrics = StrategyMetrics(
            days_running=35,
            total_trades=25,
            sharpe_ratio=1.5,
            max_drawdown=0.15,  # Above maximum
            win_rate=0.55,
            profit_factor=2.0
        )
        
        is_valid, failures = criteria.validate(metrics)
        assert is_valid is False
        assert any("drawdown" in f.lower() for f in failures)
    
    def test_validation_multiple_failures(self):
        """Test validation with multiple failures"""
        criteria = ValidationCriteria()
        metrics = StrategyMetrics(
            days_running=10,      # Too few
            total_trades=5,       # Too few
            sharpe_ratio=0.5,     # Too low
            max_drawdown=0.15,    # Too high
            win_rate=0.40,        # Too low
            profit_factor=1.0     # Too low
        )
        
        is_valid, failures = criteria.validate(metrics)
        assert is_valid is False
        assert len(failures) >= 3  # Multiple failures


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


class TestStrategyLifecycle:
    """Test StrategyLifecycle manager"""
    
    def test_initialization(self, temp_db):
        """Test lifecycle manager initializes correctly"""
        lifecycle = StrategyLifecycle(temp_db)
        assert os.path.exists(temp_db)
        
        # Check tables created
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert 'strategy_state' in tables
        assert 'state_transitions' in tables
        conn.close()
    
    def test_register_strategy(self, temp_db):
        """Test strategy registration"""
        lifecycle = StrategyLifecycle(temp_db)
        
        success = lifecycle.register_strategy("test_strategy", "Test notes")
        assert success is True
        
        state = lifecycle.get_state("test_strategy")
        assert state == StrategyState.BACKTEST
    
    def test_register_duplicate_strategy(self, temp_db):
        """Test duplicate registration is rejected"""
        lifecycle = StrategyLifecycle(temp_db)
        
        lifecycle.register_strategy("test_strategy")
        success = lifecycle.register_strategy("test_strategy")
        
        assert success is False
    
    def test_get_state_nonexistent(self, temp_db):
        """Test getting state of nonexistent strategy"""
        lifecycle = StrategyLifecycle(temp_db)
        state = lifecycle.get_state("nonexistent")
        assert state is None
    
    def test_valid_transition(self, temp_db):
        """Test valid state transition"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        # BACKTEST → PAPER is valid
        success = lifecycle.transition("test_strategy", StrategyState.PAPER)
        assert success is True
        
        state = lifecycle.get_state("test_strategy")
        assert state == StrategyState.PAPER
    
    def test_invalid_transition(self, temp_db):
        """Test invalid state transition is rejected"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        # BACKTEST → LIVE_ACTIVE is invalid (must go through PAPER first)
        success = lifecycle.transition("test_strategy", StrategyState.LIVE_ACTIVE)
        assert success is False
        
        # Should still be in BACKTEST
        state = lifecycle.get_state("test_strategy")
        assert state == StrategyState.BACKTEST
    
    def test_transition_same_state(self, temp_db):
        """Test transition to same state is rejected"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        success = lifecycle.transition("test_strategy", StrategyState.BACKTEST)
        assert success is False
    
    def test_transition_with_validation(self, temp_db):
        """Test PAPER → VALIDATED requires metrics validation"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        # Move to PAPER
        lifecycle.transition("test_strategy", StrategyState.PAPER)
        
        # Try to validate without sufficient metrics - should fail
        success = lifecycle.transition("test_strategy", StrategyState.VALIDATED)
        assert success is False
        
        # Add valid metrics
        metrics = StrategyMetrics(
            days_running=35,
            total_trades=25,
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            win_rate=0.55,
            profit_factor=2.0,
            consecutive_losses=3
        )
        lifecycle.update_metrics("test_strategy", metrics)
        
        # Now validation should pass
        success = lifecycle.transition("test_strategy", StrategyState.VALIDATED)
        assert success is True
    
    def test_pause_from_any_state(self, temp_db):
        """Test strategies can be paused from any state"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        # BACKTEST → PAUSED
        success = lifecycle.transition("test_strategy", StrategyState.PAUSED)
        assert success is True
        
        # Move to PAPER and pause again
        lifecycle.register_strategy("test_strategy2")
        lifecycle.transition("test_strategy2", StrategyState.PAPER)
        success = lifecycle.transition("test_strategy2", StrategyState.PAUSED)
        assert success is True
    
    def test_retired_is_terminal(self, temp_db):
        """Test RETIRED state is terminal"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        # Move to RETIRED
        lifecycle.transition("test_strategy", StrategyState.RETIRED)
        
        # Try to transition out - should fail
        success = lifecycle.transition("test_strategy", StrategyState.PAPER)
        assert success is False
        
        state = lifecycle.get_state("test_strategy")
        assert state == StrategyState.RETIRED
    
    def test_update_metrics(self, temp_db):
        """Test updating strategy metrics"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        metrics = StrategyMetrics(days_running=10, total_trades=15)
        success = lifecycle.update_metrics("test_strategy", metrics)
        assert success is True
        
        retrieved = lifecycle.get_metrics("test_strategy")
        assert retrieved.days_running == 10
        assert retrieved.total_trades == 15
    
    def test_get_metrics_no_data(self, temp_db):
        """Test getting metrics when none stored returns empty metrics"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        metrics = lifecycle.get_metrics("test_strategy")
        assert isinstance(metrics, StrategyMetrics)
        assert metrics.days_running == 0
    
    def test_transition_history(self, temp_db):
        """Test transition history is recorded"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        lifecycle.transition("test_strategy", StrategyState.PAPER, reason="Starting paper trading")
        lifecycle.transition("test_strategy", StrategyState.PAUSED, reason="Market closure")
        
        history = lifecycle.get_history("test_strategy")
        assert len(history) == 2
        assert history[0]['from_state'] == "backtest"
        assert history[0]['to_state'] == "paper"
        assert history[0]['reason'] == "Starting paper trading"
        assert history[1]['from_state'] == "paper"
        assert history[1]['to_state'] == "paused"
    
    def test_list_all_strategies(self, temp_db):
        """Test listing all strategies"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("strategy1", "First strategy")
        lifecycle.register_strategy("strategy2", "Second strategy")
        
        strategies = lifecycle.list_strategies()
        assert len(strategies) == 2
        assert any(s['name'] == 'strategy1' for s in strategies)
        assert any(s['name'] == 'strategy2' for s in strategies)
    
    def test_list_strategies_by_state(self, temp_db):
        """Test filtering strategies by state"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("strategy1")
        lifecycle.register_strategy("strategy2")
        lifecycle.register_strategy("strategy3")
        
        # Move strategy2 to PAPER
        lifecycle.transition("strategy2", StrategyState.PAPER)
        
        # List only BACKTEST strategies
        backtest_strategies = lifecycle.list_strategies(StrategyState.BACKTEST)
        assert len(backtest_strategies) == 2
        
        # List only PAPER strategies
        paper_strategies = lifecycle.list_strategies(StrategyState.PAPER)
        assert len(paper_strategies) == 1
        assert paper_strategies[0]['name'] == 'strategy2'
    
    def test_can_transition(self, temp_db):
        """Test can_transition check"""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("test_strategy")
        
        # Valid transition
        can_do, reason = lifecycle.can_transition("test_strategy", StrategyState.PAPER)
        assert can_do is True
        
        # Invalid transition
        can_do, reason = lifecycle.can_transition("test_strategy", StrategyState.LIVE_ACTIVE)
        assert can_do is False
        assert "invalid" in reason.lower()
        
        # Nonexistent strategy
        can_do, reason = lifecycle.can_transition("nonexistent", StrategyState.PAPER)
        assert can_do is False
        assert "not found" in reason.lower()


class TestLifecycleIntegration:
    """Integration tests for full lifecycle workflow"""
    
    def test_full_lifecycle_workflow(self, temp_db):
        """Test complete workflow from backtest to live"""
        lifecycle = StrategyLifecycle(temp_db)
        
        # 1. Register strategy
        lifecycle.register_strategy("ma_cross", "Moving average crossover")
        assert lifecycle.get_state("ma_cross") == StrategyState.BACKTEST
        
        # 2. Move to paper trading
        lifecycle.transition("ma_cross", StrategyState.PAPER, reason="Backtest passed")
        assert lifecycle.get_state("ma_cross") == StrategyState.PAPER
        
        # 3. Accumulate metrics (simulated)
        metrics = StrategyMetrics(
            days_running=35,
            total_trades=40,
            sharpe_ratio=1.8,
            max_drawdown=0.07,
            win_rate=0.58,
            profit_factor=2.2,
            consecutive_losses=3,
            total_pnl=5000.0
        )
        lifecycle.update_metrics("ma_cross", metrics)
        
        # 4. Validate
        lifecycle.transition("ma_cross", StrategyState.VALIDATED, reason="Metrics criteria met")
        assert lifecycle.get_state("ma_cross") == StrategyState.VALIDATED
        
        # 5. Approve for live
        lifecycle.transition(
            "ma_cross", 
            StrategyState.LIVE_APPROVED,
            reason="Manual review completed",
            approved_by="admin"
        )
        assert lifecycle.get_state("ma_cross") == StrategyState.LIVE_APPROVED
        
        # 6. Activate live
        lifecycle.transition("ma_cross", StrategyState.LIVE_ACTIVE, reason="Go live")
        assert lifecycle.get_state("ma_cross") == StrategyState.LIVE_ACTIVE
        
        # Check history
        history = lifecycle.get_history("ma_cross")
        assert len(history) == 4  # Four transitions
        assert history[-1]['to_state'] == "live_active"
        assert history[-2]['approved_by'] == "admin"


# ---------------------------------------------------------------------------
# Account isolation tests
# ---------------------------------------------------------------------------


class TestStrategyLifecycleAccountIsolation:
    """Tests that verify strategies are scoped by account_id."""

    def test_same_name_different_accounts_are_independent(self, temp_db):
        """Two accounts may own a strategy with the same name without collision."""
        lifecycle = StrategyLifecycle(temp_db)

        lifecycle.register_strategy("covered_call", account_id="DU111111")
        lifecycle.register_strategy("covered_call", account_id="DU222222")

        # Each account starts in BACKTEST
        assert lifecycle.get_state("covered_call", "DU111111") == StrategyState.BACKTEST
        assert lifecycle.get_state("covered_call", "DU222222") == StrategyState.BACKTEST

        # Transitioning account A does NOT affect account B
        lifecycle.transition("covered_call", StrategyState.PAPER, account_id="DU111111")
        assert lifecycle.get_state("covered_call", "DU111111") == StrategyState.PAPER
        assert lifecycle.get_state("covered_call", "DU222222") == StrategyState.BACKTEST

    def test_register_duplicate_same_account_rejected(self, temp_db):
        """Registering the same name + account twice is rejected."""
        lifecycle = StrategyLifecycle(temp_db)
        assert lifecycle.register_strategy("s1", account_id="DU111111") is True
        assert lifecycle.register_strategy("s1", account_id="DU111111") is False

    def test_register_same_name_different_account_allowed(self, temp_db):
        """Same strategy name under a different account is allowed."""
        lifecycle = StrategyLifecycle(temp_db)
        assert lifecycle.register_strategy("s1", account_id="DU111111") is True
        assert lifecycle.register_strategy("s1", account_id="DU222222") is True

    def test_get_state_unknown_account_returns_none(self, temp_db):
        """Looking up a name in the wrong account returns None."""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("s1", account_id="DU111111")
        assert lifecycle.get_state("s1", "DU999999") is None

    def test_metrics_are_account_scoped(self, temp_db):
        """Metrics written to account A are not visible in account B."""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("s1", account_id="DU111111")
        lifecycle.register_strategy("s1", account_id="DU222222")

        metrics_a = StrategyMetrics(days_running=20, total_trades=10)
        lifecycle.update_metrics("s1", metrics_a, account_id="DU111111")

        # Account B should see empty (default) metrics
        metrics_b = lifecycle.get_metrics("s1", account_id="DU222222")
        assert metrics_b.days_running == 0

    def test_history_is_account_scoped(self, temp_db):
        """Transition history for account A is not mixed with account B."""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("s1", account_id="DU111111")
        lifecycle.register_strategy("s1", account_id="DU222222")

        lifecycle.transition("s1", StrategyState.PAPER,
                             reason="A paper", account_id="DU111111")

        history_a = lifecycle.get_history("s1", "DU111111")
        history_b = lifecycle.get_history("s1", "DU222222")
        assert len(history_a) == 1
        assert len(history_b) == 0

    def test_list_strategies_filtered_by_account(self, temp_db):
        """list_strategies(account_id=...) only returns that account's strategies."""
        lifecycle = StrategyLifecycle(temp_db)
        lifecycle.register_strategy("s1", account_id="DU111111")
        lifecycle.register_strategy("s2", account_id="DU111111")
        lifecycle.register_strategy("s3", account_id="DU222222")

        result_a = lifecycle.list_strategies(account_id="DU111111")
        result_b = lifecycle.list_strategies(account_id="DU222222")
        all_strats = lifecycle.list_strategies()

        assert len(result_a) == 2
        assert len(result_b) == 1
        assert len(all_strats) == 3

    def test_save_and_load_instances_account_scoped(self, temp_db):
        """save_strategy_instance / load_strategy_instances respect account_id."""
        lifecycle = StrategyLifecycle(temp_db)

        lifecycle.save_strategy_instance(
            "bb_goog", "BollingerBands", ["GOOG"], {}, account_id="DU111111"
        )
        lifecycle.save_strategy_instance(
            "bb_aapl", "BollingerBands", ["AAPL"], {}, account_id="DU222222"
        )

        instances_a = lifecycle.load_strategy_instances(account_id="DU111111")
        instances_b = lifecycle.load_strategy_instances(account_id="DU222222")
        all_instances = lifecycle.load_strategy_instances()

        assert len(instances_a) == 1
        assert instances_a[0]["name"] == "bb_goog"
        assert instances_a[0]["account_id"] == "DU111111"

        assert len(instances_b) == 1
        assert instances_b[0]["name"] == "bb_aapl"

        assert len(all_instances) == 2

    def test_delete_instance_account_scoped(self, temp_db):
        """delete_strategy_instance only removes the matching account's record."""
        lifecycle = StrategyLifecycle(temp_db)

        lifecycle.save_strategy_instance(
            "bb_goog", "BollingerBands", ["GOOG"], {}, account_id="DU111111"
        )
        lifecycle.save_strategy_instance(
            "bb_goog", "BollingerBands", ["GOOG"], {}, account_id="DU222222"
        )

        # Delete only account A's copy
        deleted = lifecycle.delete_strategy_instance("bb_goog", account_id="DU111111")
        assert deleted is True

        # Account B's copy must survive
        remaining = lifecycle.load_strategy_instances(account_id="DU222222")
        assert len(remaining) == 1
        assert remaining[0]["account_id"] == "DU222222"

    def test_migration_adds_account_id_to_legacy_schema(self, temp_db):
        """A legacy database (without account_id) is migrated automatically."""
        import sqlite3

        # Create a database that mimics the old schema (no account_id column)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE strategy_instances (
                name TEXT PRIMARY KEY,
                strategy_type TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Insert a legacy record
        cursor.execute(
            "INSERT INTO strategy_instances VALUES (?, ?, ?, ?, ?)",
            ("old_strat", "BollingerBands", '["AAPL"]', '{}', "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Open via StrategyLifecycle — migration must succeed
        lifecycle = StrategyLifecycle(temp_db)

        # Legacy row should have account_id = '' after migration
        all_instances = lifecycle.load_strategy_instances()
        assert len(all_instances) == 1
        assert all_instances[0]["account_id"] == ""

