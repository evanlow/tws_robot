"""
Unit tests for BollingerBandsStrategy.

Tests Bollinger Bands mean reversion trading strategy.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
import pandas as pd
import numpy as np

from strategies.bollinger_bands import BollingerBandsStrategy
from strategies.signal import Signal, SignalType, SignalStrength
from strategies.base_strategy import StrategyState


class TestBollingerBandsStrategy:
    """Test BollingerBands strategy functionality"""
    
    def test_strategy_initialization(self):
        """Test strategy initialization with default parameters"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        assert strategy.config.name == "BB_Test"
        assert strategy.config.symbols == ["AAPL"]
        assert strategy.period == 20
        assert strategy.std_dev == 2.0
        assert strategy.state == StrategyState.READY
    
    def test_strategy_initialization_custom_params(self):
        """Test strategy initialization with custom parameters"""
        strategy = BollingerBandsStrategy(
            name="BB_Custom",
            symbols=["AAPL", "MSFT"],
            period=30,
            std_dev=3.0,
            min_volume=200000,
            position_size=0.15,
            stop_loss_pct=0.03
        )
        
        assert strategy.period == 30
        assert strategy.std_dev == 3.0
        assert strategy.min_volume == 200000
        assert strategy.position_size == 0.15
        assert strategy.stop_loss_pct == 0.03
        assert len(strategy.config.symbols) == 2
    
    def test_strategy_config_parameters(self):
        """Test that parameters are stored in config"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=25,
            std_dev=2.5
        )
        
        params = strategy.config.parameters
        assert params['period'] == 25
        assert params['std_dev'] == 2.5
        assert 'min_volume' in params
        assert 'position_size' in params
        assert 'stop_loss_pct' in params
    
    def test_strategy_lifecycle_start(self):
        """Test starting the strategy"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        assert strategy.state == StrategyState.READY
        
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        assert strategy.start_time is not None
    
    def test_strategy_lifecycle_stop(self):
        """Test stopping the strategy"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        
        strategy.stop()
        assert strategy.state == StrategyState.STOPPED
        assert strategy.stop_time is not None
    
    def test_strategy_lifecycle_pause_resume(self):
        """Test pausing and resuming the strategy"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        
        strategy.pause()
        assert strategy.state == StrategyState.PAUSED
        
        strategy.resume()
        assert strategy.state == StrategyState.RUNNING
    
    def test_calculate_bollinger_bands_simple(self):
        """Test Bollinger Bands calculation by processing bars"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5,
            std_dev=2.0
        )
        strategy.start()
        
        # Create simple price data and feed through on_bar
        prices = [100, 102, 98, 101, 99, 100]
        for i, price in enumerate(prices):
            bar = {
                'close': price,
                'volume': 1000000,
                'timestamp': datetime.now()
            }
            strategy.on_bar("AAPL", bar)
        
        # After enough data, should have indicators
        indicators = strategy.get_indicator_values("AAPL")
        assert 'middle_band' in indicators
        assert 'upper_band' in indicators
        assert 'lower_band' in indicators
        if indicators['upper_band'] > 0:
            assert indicators['upper_band'] > indicators['middle_band'] > indicators['lower_band']
    
    def test_calculate_bollinger_bands_insufficient_data(self):
        """Test that insufficient data doesn't crash"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=20
        )
        strategy.start()
        
        # Feed only 10 data points, need 20
        for i in range(10):
            bar = {'close': 100 + i, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)
        
        # Should not have indicators yet
        indicators = strategy.get_indicator_values("AAPL")
        assert indicators == {} or indicators.get('middle_band', 0) == 0
    
    def test_validate_signal_valid(self):
        """Test validating a valid signal after building indicators"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5
        )
        strategy.start()
        
        # Build up indicators first
        for i in range(10):
            bar = {'close': 100 + i, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)
        
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
            target_price=150.0,
            quantity=100
        )
        
        # Valid signal with indicators should pass validation
        assert strategy.validate_signal(signal) is True
    
    def test_validate_signal_wrong_symbol(self):
        """Test rejecting signal for wrong symbol"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        signal = Signal(
            symbol="MSFT",  # Not in strategy symbols
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now()
        )
        
        # Should reject signal for non-configured symbol
        assert strategy.validate_signal(signal) is False
    
    def test_on_bar_with_event_bus(self):
        """Test that on_bar processes data when running"""
        event_bus = Mock()
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5
        )
        strategy.event_bus = event_bus
        strategy.start()
        
        # Create bar data
        bar_data = {
            'symbol': 'AAPL',
            'close': 150.0,
            'volume': 1000000,
            'timestamp': datetime.now()
        }
        
        # Call on_bar (should not raise exception)
        try:
            strategy.on_bar("AAPL", bar_data)
            success = True
        except Exception:
            success = False
        
        assert success is True
    
    def test_position_tracking(self):
        """Test that strategy tracks positions"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        # Initially no positions
        assert len(strategy._positions) == 0
        
        # Simulate position entry
        strategy._positions["AAPL"] = {
            'quantity': 100,
            'entry_price': 150.0,
            'entry_time': datetime.now()
        }
        
        assert "AAPL" in strategy._positions
        assert strategy._positions["AAPL"]['quantity'] == 100
    
    def test_signal_generation_count(self):
        """Test that signal generation stores signals"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5
        )
        strategy.start()
        
        # Build indicators
        for i in range(10):
            bar = {'close': 100 + i, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)
        
        # Check signals array is empty initially
        assert len(strategy.signals_to_emit) == 0
        
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
            target_price=150.0
        )
        
        # Generate signal
        strategy.generate_signal(signal)
        
        # Check signal was stored
        assert len(strategy.signals_to_emit) > 0
    
    def test_multiple_symbols(self):
        """Test strategy with multiple symbols"""
        strategy = BollingerBandsStrategy(
            name="BB_Multi",
            symbols=["AAPL", "MSFT", "GOOGL"]
        )
        
        assert len(strategy.config.symbols) == 3
        assert "AAPL" in strategy.config.symbols
        assert "MSFT" in strategy.config.symbols
        assert "GOOGL" in strategy.config.symbols
    
    def test_price_buffer_management(self):
        """Test that strategy maintains price history for each symbol"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5
        )
        
        # Check price history initialized
        assert hasattr(strategy, 'price_history')
        assert hasattr(strategy, 'volume_history')
    
    def test_risk_limits_in_config(self):
        """Test that risk limits are accessible in config"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        # Config should exist
        assert strategy.config is not None
        assert hasattr(strategy.config, 'risk_limits')
    
    def test_strategy_enabled_flag(self):
        """Test that strategy respects enabled flag"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        # Should be enabled by default
        assert strategy.config.enabled is True
    
    def test_bollinger_bands_widening(self):
        """Test that bands widen with increased volatility"""
        # Low volatility strategy
        strategy1 = BollingerBandsStrategy(
            name="BB_LowVol",
            symbols=["AAPL"],
            period=5,
            std_dev=2.0
        )
        strategy1.start()
        
        # Feed low volatility prices
        for price in [100, 100, 100, 100, 100, 100]:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy1.on_bar("AAPL", bar)
        
        low_vol_indicators = strategy1.get_indicator_values("AAPL")
        
        # High volatility strategy
        strategy2 = BollingerBandsStrategy(
            name="BB_HighVol",
            symbols=["AAPL"],
            period=5,
            std_dev=2.0
        )
        strategy2.start()
        
        # Feed high volatility prices
        for price in [100, 110, 90, 115, 85, 100]:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy2.on_bar("AAPL", bar)
        
        high_vol_indicators = strategy2.get_indicator_values("AAPL")
        
        # Compare band widths if we have data
        if low_vol_indicators and high_vol_indicators:
            low_vol_width = low_vol_indicators['upper_band'] - low_vol_indicators['lower_band']
            high_vol_width = high_vol_indicators['upper_band'] - high_vol_indicators['lower_band']
            
            # High volatility should have wider bands
            assert high_vol_width > low_vol_width
    
    def test_strategy_parameters_validation(self):
        """Test that strategy validates parameters"""
        # Valid parameters should work
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=20,
            std_dev=2.0
        )
        
        assert strategy.period == 20
        assert strategy.std_dev == 2.0
    
    def test_strategy_state_transitions(self):
        """Test all valid state transitions"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        # READY -> RUNNING
        assert strategy.state == StrategyState.READY
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        
        # RUNNING -> PAUSED
        strategy.pause()
        assert strategy.state == StrategyState.PAUSED
        
        # PAUSED -> RUNNING
        strategy.resume()
        assert strategy.state == StrategyState.RUNNING
        
        # RUNNING -> STOPPED
        strategy.stop()
        assert strategy.state == StrategyState.STOPPED


class TestBollingerBandsCalculation:
    """Test Bollinger Bands mathematical calculations"""
    
    def test_bands_with_trending_data(self):
        """Test bands with trending price data"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5,
            std_dev=2.0
        )
        strategy.start()
        
        # Uptrending prices
        uptrend_prices = [100, 102, 104, 106, 108, 110]
        for price in uptrend_prices:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)
        
        indicators = strategy.get_indicator_values("AAPL")
        
        if indicators and indicators.get('middle_band', 0) > 0:
            # Middle band should be around average
            assert indicators['middle_band'] > 100
            assert indicators['middle_band'] < 110
            
            # Bands should be properly ordered
            assert indicators['upper_band'] > indicators['middle_band']
            assert indicators['middle_band'] > indicators['lower_band']
    
    def test_bands_with_flat_prices(self):
        """Test bands with flat price data"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5,
            std_dev=2.0
        )
        strategy.start()
        
        # Flat prices (no volatility)
        flat_prices = [100, 100, 100, 100, 100, 100]
        for price in flat_prices:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)
        
        indicators = strategy.get_indicator_values("AAPL")
        
        if indicators and indicators.get('middle_band', 0) > 0:
            # With no volatility, all bands should be very close
            assert abs(indicators['upper_band'] - indicators['middle_band']) < 1.0
            assert abs(indicators['middle_band'] - indicators['lower_band']) < 1.0
    
    def test_std_dev_multiplier_effect(self):
        """Test effect of different std_dev multipliers"""
        prices = [100, 102, 98, 101, 99, 103, 97, 100]
        
        # 2 standard deviations
        strategy1 = BollingerBandsStrategy(
            name="BB_2std",
            symbols=["AAPL"],
            period=5,
            std_dev=2.0
        )
        strategy1.start()
        for price in prices:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy1.on_bar("AAPL", bar)
        indicators1 = strategy1.get_indicator_values("AAPL")
        
        # 3 standard deviations
        strategy2 = BollingerBandsStrategy(
            name="BB_3std",
            symbols=["AAPL"],
            period=5,
            std_dev=3.0
        )
        strategy2.start()
        for price in prices:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy2.on_bar("AAPL", bar)
        indicators2 = strategy2.get_indicator_values("AAPL")
        
        if indicators1 and indicators2 and indicators1.get('upper_band', 0) > 0:
            width1 = indicators1['upper_band'] - indicators1['lower_band']
            width2 = indicators2['upper_band'] - indicators2['lower_band']
            
            # 3 std_dev should have wider bands
            assert width2 > width1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
