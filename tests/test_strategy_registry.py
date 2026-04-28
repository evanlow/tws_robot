"""
Unit tests for StrategyRegistry.

Tests strategy registration, lifecycle management, and coordination.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from core.event_bus import EventBus
from strategies.strategy_registry import StrategyRegistry
from strategies.base_strategy import BaseStrategy, StrategyState, StrategyConfig
from strategies.signal import Signal, SignalType, SignalStrength


class MockStrategy(BaseStrategy):
    """Mock strategy for testing"""
    
    def __init__(self, config: StrategyConfig, event_bus=None):
        super().__init__(config, event_bus)
        self.on_bar_called = False
        self.validate_signal_called = False
    
    def on_bar(self, symbol: str, bar_data: dict):
        """Mock on_bar implementation"""
        self.on_bar_called = True
    
    def validate_signal(self, signal: Signal) -> bool:
        """Mock validate_signal implementation"""
        self.validate_signal_called = True
        return True


class TestStrategyRegistry:
    """Test StrategyRegistry functionality"""
    
    def test_registry_initialization(self):
        """Test registry initialization"""
        event_bus = EventBus()
        registry = StrategyRegistry(event_bus)
        
        assert registry.event_bus == event_bus
        assert len(registry._strategy_classes) == 0
        assert len(registry._strategies) == 0
    
    def test_register_strategy_class(self):
        """Test registering a strategy class"""
        registry = StrategyRegistry()
        
        # Register valid strategy class
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Verify registration
        assert "MockStrategy" in registry._strategy_classes
        assert registry._strategy_classes["MockStrategy"] == MockStrategy
        
        # Check get_registered_classes
        classes = registry.get_registered_classes()
        assert "MockStrategy" in classes
    
    def test_register_invalid_strategy_class(self):
        """Test registering non-strategy class raises error"""
        registry = StrategyRegistry()
        
        # Try to register non-BaseStrategy class
        class NotAStrategy:
            pass
        
        with pytest.raises(ValueError):
            registry.register_strategy_class("Invalid", NotAStrategy)
    
    def test_unregister_strategy_class(self):
        """Test unregistering a strategy class"""
        registry = StrategyRegistry()
        
        # Register and then unregister
        registry.register_strategy_class("MockStrategy", MockStrategy)
        assert "MockStrategy" in registry._strategy_classes
        
        registry.unregister_strategy_class("MockStrategy")
        assert "MockStrategy" not in registry._strategy_classes
    
    def test_create_strategy(self):
        """Test creating a strategy instance"""
        event_bus = EventBus()
        registry = StrategyRegistry(event_bus)
        
        # Register strategy class
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create strategy instance
        config = StrategyConfig(
            name="Test_Strategy",
            symbols=["AAPL"],
            enabled=True
        )
        
        strategy = registry.create_strategy("MockStrategy", config)
        
        # Verify strategy created
        assert isinstance(strategy, MockStrategy)
        assert strategy.config.name == "Test_Strategy"
        assert strategy.event_bus == event_bus
        
        # Verify strategy registered in active strategies
        assert "Test_Strategy" in registry._strategies
    
    def test_create_strategy_unregistered_type(self):
        """Test creating strategy with unregistered type raises error"""
        registry = StrategyRegistry()
        
        config = StrategyConfig(
            name="Test",
            symbols=["AAPL"]
        )
        
        with pytest.raises(ValueError):
            registry.create_strategy("UnknownType", config)
    
    def test_create_strategy_duplicate_name(self):
        """Test creating strategy with duplicate name raises error"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="Duplicate",
            symbols=["AAPL"]
        )
        
        # Create first strategy
        registry.create_strategy("MockStrategy", config)
        
        # Try to create second with same name
        with pytest.raises(ValueError):
            registry.create_strategy("MockStrategy", config)
    
    def test_get_strategy(self):
        """Test retrieving strategy by name"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="TestStrategy",
            symbols=["AAPL"]
        )
        
        # Create strategy
        strategy = registry.create_strategy("MockStrategy", config)
        
        # Retrieve strategy
        retrieved = registry.get_strategy("TestStrategy")
        assert retrieved is strategy
        
        # Try to get non-existent strategy
        none_result = registry.get_strategy("NonExistent")
        assert none_result is None
    
    def test_remove_strategy(self):
        """Test removing a strategy"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="RemoveMe",
            symbols=["AAPL"]
        )
        
        # Create strategy
        registry.create_strategy("MockStrategy", config)
        assert "RemoveMe" in registry._strategies
        
        # Remove strategy
        registry.remove_strategy("RemoveMe")
        assert "RemoveMe" not in registry._strategies
    
    def test_get_all_strategies(self):
        """Test getting all active strategies"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create multiple strategies
        for i in range(3):
            config = StrategyConfig(
                name=f"Strategy_{i}",
                symbols=["AAPL"]
            )
            registry.create_strategy("MockStrategy", config)
        
        # Get all strategies
        strategies = registry.get_all_strategies()
        assert len(strategies) == 3
        assert all(isinstance(s, MockStrategy) for s in strategies)
    
    def test_start_strategy(self):
        """Test starting a specific strategy"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="StartMe",
            symbols=["AAPL"]
        )
        
        strategy = registry.create_strategy("MockStrategy", config)
        assert strategy.state == StrategyState.READY
        
        # Start strategy
        registry.start_strategy("StartMe")
        assert strategy.state == StrategyState.RUNNING
    
    def test_stop_strategy(self):
        """Test stopping a specific strategy"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="StopMe",
            symbols=["AAPL"]
        )
        
        strategy = registry.create_strategy("MockStrategy", config)
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        
        # Stop strategy
        registry.stop_strategy("StopMe")
        assert strategy.state == StrategyState.STOPPED
    
    def test_pause_strategy(self):
        """Test pausing a specific strategy"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="PauseMe",
            symbols=["AAPL"]
        )
        
        strategy = registry.create_strategy("MockStrategy", config)
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        
        # Pause strategy
        registry.pause_strategy("PauseMe")
        assert strategy.state == StrategyState.PAUSED
    
    def test_resume_strategy(self):
        """Test resuming a paused strategy"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        config = StrategyConfig(
            name="ResumeMe",
            symbols=["AAPL"]
        )
        
        strategy = registry.create_strategy("MockStrategy", config)
        strategy.start()
        strategy.pause()
        assert strategy.state == StrategyState.PAUSED
        
        # Resume strategy
        registry.resume_strategy("ResumeMe")
        assert strategy.state == StrategyState.RUNNING
    
    def test_start_all_strategies(self):
        """Test starting all strategies"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create multiple strategies
        strategies = []
        for i in range(3):
            config = StrategyConfig(
                name=f"Strategy_{i}",
                symbols=["AAPL"]
            )
            strategy = registry.create_strategy("MockStrategy", config)
            strategies.append(strategy)
        
        # Start all
        registry.start_all()
        
        # Verify all started
        for strategy in strategies:
            assert strategy.state == StrategyState.RUNNING
    
    def test_stop_all_strategies(self):
        """Test stopping all strategies"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create and start multiple strategies
        strategies = []
        for i in range(3):
            config = StrategyConfig(
                name=f"Strategy_{i}",
                symbols=["AAPL"]
            )
            strategy = registry.create_strategy("MockStrategy", config)
            strategy.start()
            strategies.append(strategy)
        
        # Stop all
        registry.stop_all()
        
        # Verify all stopped
        for strategy in strategies:
            assert strategy.state == StrategyState.STOPPED
    
    def test_pause_all_strategies(self):
        """Test pausing all strategies"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create and start multiple strategies
        strategies = []
        for i in range(3):
            config = StrategyConfig(
                name=f"Strategy_{i}",
                symbols=["AAPL"]
            )
            strategy = registry.create_strategy("MockStrategy", config)
            strategy.start()
            strategies.append(strategy)
        
        # Pause all
        registry.pause_all()
        
        # Verify all paused
        for strategy in strategies:
            assert strategy.state == StrategyState.PAUSED
    
    def test_get_strategies_by_state(self):
        """Test getting strategies filtered by state"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create strategies in different states
        config1 = StrategyConfig(name="Running1", symbols=["AAPL"])
        strategy1 = registry.create_strategy("MockStrategy", config1)
        strategy1.start()
        
        config2 = StrategyConfig(name="Running2", symbols=["MSFT"])
        strategy2 = registry.create_strategy("MockStrategy", config2)
        strategy2.start()
        
        config3 = StrategyConfig(name="Paused1", symbols=["GOOGL"])
        strategy3 = registry.create_strategy("MockStrategy", config3)
        strategy3.start()
        strategy3.pause()
        
        config4 = StrategyConfig(name="Ready1", symbols=["TSLA"])
        strategy4 = registry.create_strategy("MockStrategy", config4)
        
        # Get running strategies
        running = registry.get_strategies_by_state(StrategyState.RUNNING)
        assert len(running) == 2
        assert strategy1 in running
        assert strategy2 in running
        
        # Get paused strategies
        paused = registry.get_strategies_by_state(StrategyState.PAUSED)
        assert len(paused) == 1
        assert strategy3 in paused
        
        # Get ready strategies
        ready = registry.get_strategies_by_state(StrategyState.READY)
        assert len(ready) == 1
        assert strategy4 in ready
    
    def test_get_strategies_by_symbol(self):
        """Test getting strategies filtered by symbol"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create strategies with different symbols
        config1 = StrategyConfig(name="AAPL_1", symbols=["AAPL"])
        strategy1 = registry.create_strategy("MockStrategy", config1)
        
        config2 = StrategyConfig(name="AAPL_2", symbols=["AAPL", "MSFT"])
        strategy2 = registry.create_strategy("MockStrategy", config2)
        
        config3 = StrategyConfig(name="MSFT_1", symbols=["MSFT"])
        strategy3 = registry.create_strategy("MockStrategy", config3)
        
        # Get strategies for AAPL
        aapl_strategies = registry.get_strategies_by_symbol("AAPL")
        assert len(aapl_strategies) == 2
        assert strategy1 in aapl_strategies
        assert strategy2 in aapl_strategies
        
        # Get strategies for MSFT
        msft_strategies = registry.get_strategies_by_symbol("MSFT")
        assert len(msft_strategies) == 2
        assert strategy2 in msft_strategies
        assert strategy3 in msft_strategies
    
    def test_registry_performance_summary(self):
        """Test getting performance summary from registry"""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        
        # Create strategies with different performance
        for i in range(3):
            config = StrategyConfig(
                name=f"Strategy_{i}",
                symbols=["AAPL"]
            )
            strategy = registry.create_strategy("MockStrategy", config)
            strategy.signals_generated = (i + 1) * 10
            strategy.signals_accepted = (i + 1) * 8
            strategy.signals_rejected = (i + 1) * 2
        
        # Get summary using actual method name
        summary = registry.get_overall_summary()
        
        assert summary['total_strategies'] == 3
        assert summary['total_signals'] == 60  # 10 + 20 + 30
        assert summary['total_accepted'] == 48   # 8 + 16 + 24
        assert summary['total_rejected'] == 12   # 2 + 4 + 6
        assert 'acceptance_rate' in summary

    def test_inferred_strategy_types_registered(self):
        """Regression: every type emitted by PositionAnalyzer must be registered.

        This ensures that clicking 'Adopt' in the UI never fails with
        '"<type>" is not registered' for auto-detected strategies.
        """
        from strategies.inferred_strategies import INFERRED_STRATEGY_CLASSES
        from web.position_analyzer import PositionAnalyzer

        # Collect all strategy_type values PositionAnalyzer can produce by
        # analysing a synthetic portfolio that covers every detected pattern.
        #
        # positions schema: symbol -> {side, avg_cost, market_value, quantity}
        synthetic_positions = {
            # Covered call: long stock + short call
            "GOOG": {
                "side": "LONG", "avg_cost": 190.0,
                "market_value": 34200.0, "quantity": 100,
            },
            "GOOG 260515C00380000": {
                "side": "SHORT", "avg_cost": 1.0,
                "market_value": -40.0, "quantity": -1,
            },
            # Protective put: long stock + long put
            "AAPL": {
                "side": "LONG", "avg_cost": 150.0,
                "market_value": 15000.0, "quantity": 100,
            },
            "AAPL 260515P00140000": {
                "side": "LONG", "avg_cost": 2.0,
                "market_value": 200.0, "quantity": 1,
            },
            # Naked long equity
            "MSFT": {
                "side": "LONG", "avg_cost": 300.0,
                "market_value": 30000.0, "quantity": 100,
            },
            # Naked short equity
            "TSLA": {
                "side": "SHORT", "avg_cost": 200.0,
                "market_value": -20000.0, "quantity": -100,
            },
            # Naked short call
            "SPY 260515C00600000": {
                "side": "SHORT", "avg_cost": 1.0,
                "market_value": -100.0, "quantity": -1,
            },
            # Naked long put
            "QQQ 260515P00400000": {
                "side": "LONG", "avg_cost": 3.0,
                "market_value": 300.0, "quantity": 1,
            },
        }

        analyzer = PositionAnalyzer()
        inferred = analyzer.analyze(synthetic_positions)
        detected_types = {s.strategy_type for s in inferred}

        registry = StrategyRegistry()
        registry.register_strategy_class("BollingerBands", MockStrategy)
        for strategy_type, strategy_class in INFERRED_STRATEGY_CLASSES.items():
            registry.register_strategy_class(strategy_type, strategy_class)

        registered = set(registry.get_registered_classes())

        for stype in detected_types:
            assert stype in registered, (
                f"Strategy type '{stype}' is detected by PositionAnalyzer "
                f"but not registered in StrategyRegistry. "
                f"The Adopt button will fail for this type."
            )


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

import os
import tempfile


@pytest.fixture
def temp_db_path():
    """Return a path to a fresh temporary SQLite database, deleted after the test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # let StrategyLifecycle create it fresh
    yield path
    if os.path.exists(path):
        os.unlink(path)


class TestStrategyRegistryPersistence:
    """Tests for the database-backed persistence of strategy instances."""

    def _make_registry(self, db_path: str) -> StrategyRegistry:
        """Create a registry with MockStrategy registered and persistence enabled."""
        registry = StrategyRegistry(db_path=db_path)
        registry.register_strategy_class("MockStrategy", MockStrategy)
        return registry

    def test_create_strategy_persists_to_db(self, temp_db_path):
        """Creating a strategy should write a record to the database."""
        registry = self._make_registry(temp_db_path)
        config = StrategyConfig(name="Persist_1", symbols=["AAPL"])
        registry.create_strategy("MockStrategy", config)

        # Load records directly from the lifecycle store
        records = registry._lifecycle.load_strategy_instances()
        assert len(records) == 1
        assert records[0]["name"] == "Persist_1"
        assert records[0]["strategy_type"] == "MockStrategy"
        assert records[0]["symbols"] == ["AAPL"]

    def test_load_persisted_strategies_restores_instances(self, temp_db_path):
        """Strategies created in one registry session are reloaded in the next."""
        # Session 1: create two strategies
        registry1 = self._make_registry(temp_db_path)
        registry1.create_strategy(
            "MockStrategy", StrategyConfig(name="BB_AAPL", symbols=["AAPL"])
        )
        registry1.create_strategy(
            "MockStrategy",
            StrategyConfig(name="BB_MSFT", symbols=["MSFT"], parameters={"period": 25}),
        )

        # Session 2: new registry, same DB — simulate an app restart
        registry2 = self._make_registry(temp_db_path)
        restored = registry2.load_persisted_strategies()

        assert restored == 2
        assert "BB_AAPL" in registry2
        assert "BB_MSFT" in registry2

        msft = registry2.get_strategy("BB_MSFT")
        assert msft is not None
        assert msft.config.symbols == ["MSFT"]
        assert msft.config.parameters == {"period": 25}

    def test_remove_strategy_deletes_from_db(self, temp_db_path):
        """Removing a strategy must delete its persistence record."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="ToDelete", symbols=["GOOG"])
        )

        # Confirm it was persisted
        assert len(registry._lifecycle.load_strategy_instances()) == 1

        registry.remove_strategy("ToDelete")

        # Confirm it was removed from the database
        assert len(registry._lifecycle.load_strategy_instances()) == 0

    def test_load_skips_unknown_strategy_types(self, temp_db_path):
        """Strategies whose type is no longer registered are skipped, not raised."""
        # Write a record for an unknown type directly via the lifecycle store
        from strategy.lifecycle import StrategyLifecycle
        lifecycle = StrategyLifecycle(temp_db_path)
        lifecycle.save_strategy_instance(
            name="Ghost", strategy_type="ObsoleteType", symbols=["X"], parameters={}
        )

        registry = self._make_registry(temp_db_path)
        restored = registry.load_persisted_strategies()

        assert restored == 0
        assert "Ghost" not in registry

    def test_no_db_path_no_persistence(self):
        """Without a db_path the registry works purely in-memory with no errors."""
        registry = StrategyRegistry()
        registry.register_strategy_class("MockStrategy", MockStrategy)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="InMemory", symbols=["AAPL"])
        )

        assert registry._lifecycle is None
        restored = registry.load_persisted_strategies()
        assert restored == 0
        assert "InMemory" in registry

    def test_load_does_not_duplicate_existing_strategies(self, temp_db_path):
        """load_persisted_strategies must not create duplicates for in-memory entries."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="Once", symbols=["AAPL"])
        )

        # Calling load again should not duplicate the already-present strategy
        restored = registry.load_persisted_strategies()
        assert restored == 0
        assert len(registry.get_all_strategies()) == 1

    def test_upsert_updates_existing_record(self, temp_db_path):
        """save_strategy_instance with same name must overwrite, not duplicate."""
        from strategy.lifecycle import StrategyLifecycle
        lifecycle = StrategyLifecycle(temp_db_path)

        lifecycle.save_strategy_instance(
            name="BB_AAPL", strategy_type="MockStrategy",
            symbols=["AAPL"], parameters={"period": 20},
        )
        # Overwrite with new symbols/parameters
        lifecycle.save_strategy_instance(
            name="BB_AAPL", strategy_type="MockStrategy",
            symbols=["AAPL", "MSFT"], parameters={"period": 30},
        )

        records = lifecycle.load_strategy_instances()
        assert len(records) == 1
        assert records[0]["symbols"] == ["AAPL", "MSFT"]
        assert records[0]["parameters"] == {"period": 30}

    def test_invalid_json_rows_are_skipped(self, temp_db_path):
        """load_strategy_instances must skip rows with corrupted JSON, not raise."""
        import sqlite3
        from strategy.lifecycle import StrategyLifecycle

        lifecycle = StrategyLifecycle(temp_db_path)

        # Insert a row with invalid JSON directly
        conn = sqlite3.connect(temp_db_path)
        conn.execute(
            """
            INSERT INTO strategy_instances
                (name, strategy_type, symbols_json, parameters_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Corrupt", "MockStrategy", "NOT_JSON", "{}", "2024-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # A valid row
        lifecycle.save_strategy_instance(
            name="Good", strategy_type="MockStrategy",
            symbols=["AAPL"], parameters={},
        )

        records = lifecycle.load_strategy_instances()
        # Only the valid row should be returned
        assert len(records) == 1
        assert records[0]["name"] == "Good"

    def test_invalid_config_rows_are_skipped_on_load(self, temp_db_path):
        """load_persisted_strategies skips records that fail StrategyConfig.validate()."""
        import sqlite3
        from strategy.lifecycle import StrategyLifecycle

        lifecycle = StrategyLifecycle(temp_db_path)
        # Empty symbols list — will fail StrategyConfig.validate()
        lifecycle.save_strategy_instance(
            name="BadConfig", strategy_type="MockStrategy",
            symbols=[], parameters={},
        )

        registry = self._make_registry(temp_db_path)
        restored = registry.load_persisted_strategies()

        assert restored == 0
        assert "BadConfig" not in registry


# ---------------------------------------------------------------------------
# Account-scoped registry tests
# ---------------------------------------------------------------------------


class TestStrategyRegistryAccountIsolation:
    """Verify the registry only loads/persists strategies for its own account."""

    def _make_registry(self, db_path: str, account_id: str = "") -> StrategyRegistry:
        registry = StrategyRegistry(db_path=db_path, account_id=account_id)
        registry.register_strategy_class("MockStrategy", MockStrategy)
        return registry

    def test_registry_account_id_stored(self, temp_db_path):
        """account_id passed to StrategyRegistry is stored."""
        registry = self._make_registry(temp_db_path, "DU111111")
        assert registry.account_id == "DU111111"

    def test_strategies_persisted_with_registry_account(self, temp_db_path):
        """Creating a strategy in an account-scoped registry stores account_id."""
        registry = self._make_registry(temp_db_path, "DU111111")
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="BB_AAPL", symbols=["AAPL"])
        )

        # Verify the persisted record carries the correct account_id
        records = registry._lifecycle.load_strategy_instances(account_id="DU111111")
        assert len(records) == 1
        assert records[0]["account_id"] == "DU111111"

    def test_load_only_restores_own_account_strategies(self, temp_db_path):
        """A registry for account A must not restore account B's strategies."""
        # Session 1: create strategies in two different accounts
        reg_a = self._make_registry(temp_db_path, "DU111111")
        reg_a.create_strategy(
            "MockStrategy", StrategyConfig(name="Strat_A", symbols=["AAPL"])
        )

        reg_b = self._make_registry(temp_db_path, "DU222222")
        reg_b.create_strategy(
            "MockStrategy", StrategyConfig(name="Strat_B", symbols=["MSFT"])
        )

        # Session 2: new registry for account A only
        new_reg_a = self._make_registry(temp_db_path, "DU111111")
        restored = new_reg_a.load_persisted_strategies()

        assert restored == 1
        assert "Strat_A" in new_reg_a
        assert "Strat_B" not in new_reg_a

    def test_remove_strategy_only_deletes_own_account_record(self, temp_db_path):
        """remove_strategy for account A must not delete account B's record."""
        reg_a = self._make_registry(temp_db_path, "DU111111")
        reg_b = self._make_registry(temp_db_path, "DU222222")

        # Both accounts create a strategy with the same name
        reg_a.create_strategy(
            "MockStrategy", StrategyConfig(name="SharedName", symbols=["GOOG"])
        )
        reg_b.create_strategy(
            "MockStrategy", StrategyConfig(name="SharedName", symbols=["GOOG"])
        )

        reg_a.remove_strategy("SharedName")

        # Account B's record must survive
        instances_b = reg_b._lifecycle.load_strategy_instances(account_id="DU222222")
        assert len(instances_b) == 1

    def test_config_account_id_takes_precedence(self, temp_db_path):
        """If config.account_id is set explicitly it is used over registry.account_id."""
        registry = self._make_registry(temp_db_path, "DU111111")
        config = StrategyConfig(name="Explicit", symbols=["AAPL"],
                                account_id="DU999999")
        registry.create_strategy("MockStrategy", config)

        # Record should carry the explicit account_id from the config
        records_explicit = registry._lifecycle.load_strategy_instances(
            account_id="DU999999"
        )
        records_registry = registry._lifecycle.load_strategy_instances(
            account_id="DU111111"
        )
        assert len(records_explicit) == 1
        assert len(records_registry) == 0


# ---------------------------------------------------------------------------
# Running-state persistence tests
# ---------------------------------------------------------------------------


class TestStrategyRunningStatePersistence:
    """Tests that a strategy's running state is saved and restored across sessions."""

    def _make_registry(self, db_path: str) -> StrategyRegistry:
        registry = StrategyRegistry(db_path=db_path)
        registry.register_strategy_class("MockStrategy", MockStrategy)
        return registry

    def test_start_persists_running_state(self, temp_db_path):
        """Starting a strategy must update the persisted running_state to RUNNING."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="S1", symbols=["AAPL"])
        )
        registry.start_strategy("S1")

        records = registry._lifecycle.load_strategy_instances()
        assert records[0]["running_state"] == StrategyState.RUNNING.value

    def test_stop_persists_stopped_state(self, temp_db_path):
        """Stopping a strategy must update the persisted running_state to STOPPED."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="S1", symbols=["AAPL"])
        )
        registry.start_strategy("S1")
        registry.stop_strategy("S1")

        records = registry._lifecycle.load_strategy_instances()
        assert records[0]["running_state"] == StrategyState.STOPPED.value

    def test_pause_persists_paused_state(self, temp_db_path):
        """Pausing a strategy must update the persisted running_state to PAUSED."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="S1", symbols=["AAPL"])
        )
        registry.start_strategy("S1")
        registry.pause_strategy("S1")

        records = registry._lifecycle.load_strategy_instances()
        assert records[0]["running_state"] == StrategyState.PAUSED.value

    def test_resume_persists_running_state(self, temp_db_path):
        """Resuming a paused strategy must update the persisted running_state to RUNNING."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="S1", symbols=["AAPL"])
        )
        registry.start_strategy("S1")
        registry.pause_strategy("S1")
        registry.resume_strategy("S1")

        records = registry._lifecycle.load_strategy_instances()
        assert records[0]["running_state"] == StrategyState.RUNNING.value

    def test_running_state_restored_on_load(self, temp_db_path):
        """A strategy that was RUNNING before restart is RUNNING after load."""
        # Session 1: create and start a strategy
        registry1 = self._make_registry(temp_db_path)
        registry1.create_strategy(
            "MockStrategy", StrategyConfig(name="Runner", symbols=["AAPL"])
        )
        registry1.start_strategy("Runner")

        # Session 2: new registry, same DB
        registry2 = self._make_registry(temp_db_path)
        registry2.load_persisted_strategies()

        strategy = registry2.get_strategy("Runner")
        assert strategy is not None
        assert strategy.state == StrategyState.RUNNING

    def test_paused_state_restored_on_load(self, temp_db_path):
        """A strategy that was PAUSED before restart is PAUSED after load."""
        registry1 = self._make_registry(temp_db_path)
        registry1.create_strategy(
            "MockStrategy", StrategyConfig(name="Pauser", symbols=["AAPL"])
        )
        registry1.start_strategy("Pauser")
        registry1.pause_strategy("Pauser")

        registry2 = self._make_registry(temp_db_path)
        registry2.load_persisted_strategies()

        strategy = registry2.get_strategy("Pauser")
        assert strategy is not None
        assert strategy.state == StrategyState.PAUSED

    def test_stopped_state_not_restarted_on_load(self, temp_db_path):
        """A strategy that was STOPPED before restart stays READY (not restarted)."""
        registry1 = self._make_registry(temp_db_path)
        registry1.create_strategy(
            "MockStrategy", StrategyConfig(name="Stopper", symbols=["AAPL"])
        )
        registry1.start_strategy("Stopper")
        registry1.stop_strategy("Stopper")

        registry2 = self._make_registry(temp_db_path)
        registry2.load_persisted_strategies()

        strategy = registry2.get_strategy("Stopper")
        assert strategy is not None
        # STOPPED strategies are restored as READY — they are not auto-restarted
        assert strategy.state == StrategyState.READY

    def test_new_strategy_defaults_to_ready_state(self, temp_db_path):
        """A newly created strategy (never started) has running_state READY in DB."""
        registry = self._make_registry(temp_db_path)
        registry.create_strategy(
            "MockStrategy", StrategyConfig(name="Fresh", symbols=["AAPL"])
        )

        records = registry._lifecycle.load_strategy_instances()
        assert records[0]["running_state"] == "READY"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
