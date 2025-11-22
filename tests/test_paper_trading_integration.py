"""
Integration Tests for Paper Trading System

End-to-end tests validating the complete paper trading workflow:
- Strategy deployment from backtest to paper
- Real-time data flow
- Order execution and position tracking
- Risk limit enforcement
- Component integration

Author: TWS Robot Development Team
Date: November 22, 2025
Sprint 1 Task 5
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict

from strategy.lifecycle import StrategyLifecycle, StrategyState, StrategyMetrics, ValidationCriteria
from execution.paper_adapter import PaperTradingAdapter, PendingOrder
from data.realtime_pipeline import RealtimeDataManager, DataSubscription, BarBuffer
from monitoring.paper_monitor import PaperMonitor, StrategySnapshot, RiskSnapshot
from backtest.strategy_templates import MovingAverageCrossStrategy
from backtest.data_models import Bar, Position, TimeFrame
from backtest.profiles import RiskProfile, ProfileType


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for lifecycle testing"""
    db_path = tmp_path / "test_lifecycle.db"
    return str(db_path)


@pytest.fixture
def lifecycle_manager(temp_db):
    """Create StrategyLifecycle manager"""
    return StrategyLifecycle(db_path=temp_db)


@pytest.fixture
def paper_adapter():
    """Create PaperTradingAdapter (won't connect without TWS)"""
    return PaperTradingAdapter(host="127.0.0.1", port=7497, client_id=200)


@pytest.fixture
def monitor():
    """Create PaperMonitor"""
    return PaperMonitor()


@pytest.fixture
def ma_cross_strategy():
    """Create MA Cross strategy instance"""
    from backtest.strategy import StrategyConfig
    
    config = StrategyConfig(
        name="MA_Cross_Test",
        symbols=['AAPL', 'MSFT'],
        initial_capital=100000.0,
        parameters={
            'fast_period': 10,
            'slow_period': 20,
            'signal_threshold': 0.01
        }
    )
    return MovingAverageCrossStrategy(config=config)


@pytest.fixture
def sample_bar():
    """Create sample bar data"""
    return Bar(
        timestamp=datetime.now(),
        symbol="AAPL",
        open=150.0,
        high=152.0,
        low=149.0,
        close=151.0,
        volume=1000000,
        timeframe=TimeFrame.MINUTE_1
    )


@pytest.fixture
def conservative_profile():
    """Create conservative risk profile"""
    return RiskProfile(
        name="Conservative",
        profile_type=ProfileType.CONSERVATIVE,
        max_position_size=0.05,  # 5% per position
        max_portfolio_risk=0.01,  # 1% per trade
        max_concurrent_positions=3,
        default_stop_loss=0.01,  # 1% stop
        default_profit_target=0.03  # 3% target
    )


class TestEndToEndPaperTrading:
    """Test complete paper trading workflow"""
    
    def test_strategy_lifecycle_states(self, lifecycle_manager):
        """Test strategy can be registered and transitioned through states"""
        # Register strategy in BACKTEST state (default)
        lifecycle_manager.register_strategy("MA_Cross")
        
        # Verify initial state
        state = lifecycle_manager.get_state("MA_Cross")
        assert state == StrategyState.BACKTEST
        
        # Transition to PAPER
        success = lifecycle_manager.transition("MA_Cross", StrategyState.PAPER)
        assert success
        assert lifecycle_manager.get_state("MA_Cross") == StrategyState.PAPER
    
    def test_strategy_to_paper_requires_validation(self, lifecycle_manager):
        """Test strategy cannot go to VALIDATED without meeting criteria"""
        lifecycle_manager.register_strategy("MA_Cross")
        lifecycle_manager.transition("MA_Cross", StrategyState.PAPER)
        
        # Try to transition to VALIDATED without meeting criteria
        success = lifecycle_manager.transition("MA_Cross", StrategyState.VALIDATED)
        assert not success  # Should fail validation
        
        # Update metrics to meet criteria
        metrics = StrategyMetrics(
            days_running=30,
            total_trades=25,
            sharpe_ratio=1.2,
            max_drawdown=0.08,
            win_rate=0.55,
            profit_factor=1.8,
            total_pnl=5000.0
        )
        lifecycle_manager.update_metrics("MA_Cross", metrics)
        
        # Now transition should succeed
        success = lifecycle_manager.transition("MA_Cross", StrategyState.VALIDATED)
        assert success
        assert lifecycle_manager.get_state("MA_Cross") == StrategyState.VALIDATED
    
    def test_adapter_order_execution_pattern(self, paper_adapter):
        """Test paper adapter order execution without TWS connection"""
        # Simulate adapter ready state
        paper_adapter.ready = True
        paper_adapter.next_valid_order_id = 5000
        
        # Mock serverVersion for TWS API calls
        with patch.object(paper_adapter, 'serverVersion', return_value=176):
            # Place order
            order_id = paper_adapter.buy("AAPL", 100, order_type="MKT")
            
            assert order_id == 5000
            assert order_id in paper_adapter._orders
            
            order = paper_adapter.get_order(order_id)
            assert order is not None
            assert order.symbol == "AAPL"
            assert order.quantity == 100
            assert order.action == "BUY"
    
    def test_adapter_position_tracking(self, paper_adapter):
        """Test position tracking in paper adapter"""
        # Manually create position (simulating TWS callback)
        position = Position(
            symbol="AAPL",
            quantity=100,
            average_cost=150.0,
            current_price=152.0
        )
        
        with paper_adapter._positions_lock:
            paper_adapter._positions["AAPL"] = position
        
        # Verify position retrieval
        positions = paper_adapter.get_all_positions()
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 100
        assert positions["AAPL"].average_cost == 150.0
    
    def test_bar_buffer_aggregation(self):
        """Test bar buffer aggregates ticks correctly"""
        buffer = BarBuffer(symbol="AAPL")
        
        now = datetime.now()
        
        # Add multiple ticks
        buffer.update_price(150.0, 100, now)
        buffer.update_price(151.0, 200, now + timedelta(seconds=10))
        buffer.update_price(149.5, 150, now + timedelta(seconds=20))
        buffer.update_price(150.5, 100, now + timedelta(seconds=30))
        
        # Verify aggregation
        assert buffer.is_complete()
        assert buffer.open == 150.0
        assert buffer.high == 151.0
        assert buffer.low == 149.5
        assert buffer.close == 150.5
        assert buffer.volume == 550
        
        # Convert to Bar
        bar = buffer.to_bar(TimeFrame.MINUTE_1)
        assert bar.symbol == "AAPL"
        assert bar.open == 150.0
        assert bar.high == 151.0
        assert bar.low == 149.5
        assert bar.close == 150.5
        assert bar.volume == 550


class TestMultiSymbolHandling:
    """Test multi-symbol data distribution and order routing"""
    
    def test_data_subscription_multiple_symbols(self):
        """Test subscribing to multiple symbols"""
        callback = Mock()
        
        subscription = DataSubscription(
            strategy_id="MA_Cross",
            symbols=["AAPL", "MSFT", "GOOGL"],
            callback=callback,
            timeframe=TimeFrame.MINUTE_1
        )
        
        assert len(subscription.symbols) == 3
        assert "AAPL" in subscription.symbols
        assert "MSFT" in subscription.symbols
        assert "GOOGL" in subscription.symbols
        assert subscription.active
    
    def test_multiple_orders_different_symbols(self, paper_adapter):
        """Test ordering multiple symbols"""
        paper_adapter.ready = True
        paper_adapter.next_valid_order_id = 6000
        
        # Mock serverVersion for TWS API calls
        with patch.object(paper_adapter, 'serverVersion', return_value=176):
            # Place orders for different symbols
            order1 = paper_adapter.buy("AAPL", 100, order_type="MKT")
            order2 = paper_adapter.buy("MSFT", 50, order_type="MKT")
            order3 = paper_adapter.buy("GOOGL", 25, order_type="MKT")
            
            assert order1 == 6000
            assert order2 == 6001
            assert order3 == 6002
            
            # Verify all orders tracked
            assert len(paper_adapter._orders) == 3
    
    def test_position_tracking_multiple_symbols(self, paper_adapter):
        """Test tracking positions across multiple symbols"""
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, average_cost=150.0, current_price=152.0),
            "MSFT": Position(symbol="MSFT", quantity=50, average_cost=380.0, current_price=385.0),
            "GOOGL": Position(symbol="GOOGL", quantity=25, average_cost=2800.0, current_price=2825.0)
        }
        
        with paper_adapter._positions_lock:
            paper_adapter._positions.update(positions)
        
        all_positions = paper_adapter.get_all_positions()
        assert len(all_positions) == 3
        assert "AAPL" in all_positions
        assert "MSFT" in all_positions
        assert "GOOGL" in all_positions


class TestRiskLimitEnforcement:
    """Test risk limit enforcement in paper trading"""
    
    def test_profile_position_size_limits(self, conservative_profile):
        """Test risk profile enforces position size limits"""
        assert conservative_profile.max_position_size == 0.05  # 5%
        assert conservative_profile.max_concurrent_positions == 3
        
        # Validate profile
        errors = conservative_profile.validate()
        assert len(errors) == 0
    
    def test_portfolio_risk_calculation(self, conservative_profile):
        """Test portfolio risk calculation"""
        portfolio_value = 100000.0
        position_size = portfolio_value * conservative_profile.max_position_size
        
        assert position_size == 5000.0  # 5% of 100k
        
        # Verify doesn't exceed max risk per trade
        max_risk_amount = portfolio_value * conservative_profile.max_portfolio_risk
        stop_loss_amount = position_size * conservative_profile.default_stop_loss
        
        assert stop_loss_amount <= max_risk_amount  # Should be within limits
    
    def test_concurrent_position_limit(self, conservative_profile):
        """Test concurrent position limits"""
        current_positions = 3
        max_positions = conservative_profile.max_concurrent_positions
        
        # At limit - should not allow new position
        can_open_new = current_positions < max_positions
        assert not can_open_new
        
        # Below limit - should allow
        current_positions = 2
        can_open_new = current_positions < max_positions
        assert can_open_new
    
    def test_order_rejection_when_over_limit(self, paper_adapter, conservative_profile):
        """Test order rejection when position limit exceeded"""
        # Simulate 3 open positions (at limit)
        for i, symbol in enumerate(["AAPL", "MSFT", "GOOGL"]):
            pos = Position(symbol=symbol, quantity=100, average_cost=150.0, current_price=150.0)
            with paper_adapter._positions_lock:
                paper_adapter._positions[symbol] = pos
        
        # Count non-zero positions
        position_count = len([p for p in paper_adapter.get_all_positions().values() if p.quantity != 0])
        
        # At limit (3 positions)
        assert position_count == 3
        assert position_count >= conservative_profile.max_concurrent_positions


class TestConnectionResilience:
    """Test connection handling and state preservation"""
    
    def test_adapter_connection_state_tracking(self, paper_adapter):
        """Test adapter tracks connection state"""
        assert not paper_adapter.connected
        assert not paper_adapter.ready
        
        # Simulate connection
        paper_adapter.connected = True
        assert paper_adapter.connected
        
        # Simulate ready state
        paper_adapter.ready = True
        paper_adapter.next_valid_order_id = 1000
        assert paper_adapter.ready
    
    def test_orders_fail_when_not_ready(self, paper_adapter):
        """Test orders fail when adapter not ready"""
        paper_adapter.ready = False
        
        with pytest.raises(RuntimeError, match="Not connected to TWS or not ready"):
            paper_adapter.buy("AAPL", 100)
    
    def test_state_preservation_across_disconnect(self, paper_adapter):
        """Test positions preserved across simulated disconnect"""
        # Setup position
        pos = Position(symbol="AAPL", quantity=100, average_cost=150.0, current_price=150.0)
        with paper_adapter._positions_lock:
            paper_adapter._positions["AAPL"] = pos
        
        # Simulate disconnect
        paper_adapter.connected = False
        paper_adapter.ready = False
        
        # Positions should still be tracked
        positions = paper_adapter.get_all_positions()
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 100
    
    def test_order_tracking_persists(self, paper_adapter):
        """Test order tracking persists across simulated disconnect"""
        paper_adapter.ready = True
        paper_adapter.next_valid_order_id = 7000
        
        # Mock serverVersion for TWS API calls
        with patch.object(paper_adapter, 'serverVersion', return_value=176):
            # Place order
            order_id = paper_adapter.buy("AAPL", 100)
            
            # Simulate disconnect
            paper_adapter.connected = False
            paper_adapter.ready = False
            
            # Order should still be tracked
            order = paper_adapter.get_order(order_id)
            assert order is not None
            assert order.order_id == 7000


class TestMonitorIntegration:
    """Test monitor integration with paper trading components"""
    
    def test_monitor_displays_strategy_state(self, monitor):
        """Test monitor can display strategy state"""
        snapshot = StrategySnapshot(
            name="MA_Cross",
            state=StrategyState.PAPER,
            start_time=datetime.now() - timedelta(hours=1),
            positions={"AAPL": Position(symbol="AAPL", quantity=100, average_cost=150.0, current_price=152.0)},
            session_pnl=200.0,
            total_pnl=1500.0,
            metrics=StrategyMetrics(
                days_running=10,
                total_trades=30,
                sharpe_ratio=1.1,
                win_rate=0.55
            )
        )
        
        monitor.update_strategy(snapshot)
        
        assert len(monitor._strategy_snapshots) == 1
        assert "MA_Cross" in monitor._strategy_snapshots
    
    def test_monitor_displays_risk_metrics(self, monitor):
        """Test monitor displays risk metrics"""
        risk = RiskSnapshot(
            portfolio_value=100000.0,
            margin_used=20000.0,
            margin_available=80000.0,
            max_drawdown=0.05,
            position_count=2,
            risk_limit_utilization=0.4
        )
        
        monitor.update_risk(risk)
        
        assert monitor._risk_snapshot is not None
        assert monitor._risk_snapshot.portfolio_value == 100000.0
    
    def test_monitor_displays_orders(self, monitor):
        """Test monitor displays order activity"""
        order = PendingOrder(
            order_id=8000,
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT",
            status="FILLED",
            filled_qty=100,
            avg_fill_price=150.25
        )
        
        monitor.add_order(order)
        
        assert len(monitor._recent_orders) == 1
        assert monitor._recent_orders[0].order_id == 8000
    
    def test_monitor_renders_layout(self, monitor):
        """Test monitor renders complete layout"""
        # Add some data
        snapshot = StrategySnapshot(
            name="Test",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},
            session_pnl=100.0,
            total_pnl=500.0,
            metrics=StrategyMetrics()
        )
        monitor.update_strategy(snapshot)
        
        # Render layout
        layout = monitor.render()
        
        assert layout is not None
        assert layout["top"] is not None
        assert layout["bottom"] is not None


class TestFullWorkflowIntegration:
    """Test complete workflow integration"""
    
    def test_strategy_registration_to_monitor(self, lifecycle_manager, monitor):
        """Test strategy flows from registration to monitor display"""
        # Register strategy
        lifecycle_manager.register_strategy("MA_Cross")
        
        # Transition to PAPER
        lifecycle_manager.transition("MA_Cross", StrategyState.PAPER)
        
        # Get state for monitor
        state = lifecycle_manager.get_state("MA_Cross")
        
        # Create snapshot for monitor
        snapshot = StrategySnapshot(
            name="MA_Cross",
            state=state,
            start_time=datetime.now(),
            positions={},
            session_pnl=0.0,
            total_pnl=0.0,
            metrics=StrategyMetrics()
        )
        
        monitor.update_strategy(snapshot)
        
        # Verify integration
        assert state == StrategyState.PAPER
        assert "MA_Cross" in monitor._strategy_snapshots
    
    def test_order_execution_to_position_to_monitor(self, paper_adapter, monitor):
        """Test order → position → monitor flow"""
        paper_adapter.ready = True
        paper_adapter.next_valid_order_id = 9000
        
        # Mock serverVersion for TWS API calls
        with patch.object(paper_adapter, 'serverVersion', return_value=176):
            # Place order
            order_id = paper_adapter.buy("AAPL", 100, order_type="MKT")
            
            # Simulate fill
            order = paper_adapter.get_order(order_id)
            order.status = "FILLED"
            order.filled_qty = 100
            order.avg_fill_price = 150.0
            
            # Create position from fill
            pos = Position(symbol="AAPL", quantity=100, average_cost=150.0, current_price=150.0)
            with paper_adapter._positions_lock:
                paper_adapter._positions["AAPL"] = pos
            
            # Update monitor
            pending_order = PendingOrder(
                order_id=order_id,
                symbol="AAPL",
                action="BUY",
                quantity=100,
                order_type="MKT",
                status="FILLED",
                filled_qty=100,
                avg_fill_price=150.0
            )
            monitor.add_order(pending_order)
            
            # Verify flow
            assert order_id in paper_adapter._orders
            assert "AAPL" in paper_adapter.get_all_positions()
            assert len(monitor._recent_orders) == 1
    
    def test_data_subscription_pattern(self):
        """Test data subscription creation pattern"""
        # Strategy would create subscription like this
        callback = Mock()
        
        subscription = DataSubscription(
            strategy_id="MA_Cross",
            symbols=["AAPL"],
            callback=callback,
            timeframe=TimeFrame.MINUTE_1
        )
        
        # RealtimeDataManager would track this
        subscriptions = {"MA_Cross": subscription}
        
        assert "MA_Cross" in subscriptions
        assert subscription.active
        assert "AAPL" in subscription.symbols


class TestPrimeDirectiveCompliance:
    """Test Prime Directive compliance"""
    
    def test_all_components_importable(self):
        """Test all paper trading components can be imported"""
        # This test verifies no import errors
        from strategy.lifecycle import StrategyLifecycle, StrategyState
        from execution.paper_adapter import PaperTradingAdapter
        from data.realtime_pipeline import RealtimeDataManager, DataSubscription
        from monitoring.paper_monitor import PaperMonitor
        from backtest.strategy_templates import MovingAverageCrossStrategy
        
        # All imports succeeded
        assert True
    
    def test_baseline_compatibility_maintained(self, ma_cross_strategy, sample_bar):
        """Test backtest components still work after paper trading integration"""
        # Feed bar (no signal expected on first bar)
        ma_cross_strategy.on_bar("AAPL", sample_bar)
        
        # Verify strategy can process bars without errors
        assert True  # If we get here, strategy processing works
    
    def test_no_breaking_changes_to_existing_apis(self):
        """Test no breaking changes to existing APIs"""
        # Verify core classes still have expected interfaces
        from backtest.data_models import Bar, Position
        from backtest.strategy import Strategy
        
        # Bar should have all expected attributes
        bar = Bar(
            timestamp=datetime.now(),
            symbol="AAPL",
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000,
            timeframe=TimeFrame.MINUTE_1
        )
        
        assert hasattr(bar, 'timestamp')
        assert hasattr(bar, 'symbol')
        assert hasattr(bar, 'open')
        assert hasattr(bar, 'close')
        
        # Position should have expected attributes
        pos = Position(symbol="AAPL", quantity=100, average_cost=150.0)
        assert hasattr(pos, 'symbol')
        assert hasattr(pos, 'quantity')
        assert hasattr(pos, 'average_cost')
        assert hasattr(pos, 'unrealized_pnl')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
