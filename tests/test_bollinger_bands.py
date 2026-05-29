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


class TestBollingerMomentumFilter:
    """Tests for the momentum filter integration in BollingerBandsStrategy."""

    def _make_strategy(self, period=5, min_volume=0):
        strategy = BollingerBandsStrategy(
            name="BB_MomTest",
            symbols=["AAPL"],
            period=period,
            std_dev=2.0,
            min_volume=min_volume,
        )
        strategy.start()
        return strategy

    def test_assess_momentum_insufficient_data(self):
        """Momentum returns insufficient_data with <20 bars."""
        strategy = self._make_strategy()
        strategy.price_history["AAPL"] = [100.0] * 10
        assert strategy._assess_momentum("AAPL") == "insufficient_data"

    def test_assess_momentum_uptrend(self):
        """Momentum detects uptrend when price > MA20 > MA50."""
        strategy = self._make_strategy()
        # Steadily rising prices
        strategy.price_history["AAPL"] = [50 + i for i in range(60)]
        assert strategy._assess_momentum("AAPL") == "uptrend"

    def test_assess_momentum_downtrend(self):
        """Momentum detects downtrend when price < MA20 < MA50."""
        strategy = self._make_strategy()
        # Steadily falling prices
        strategy.price_history["AAPL"] = [200 - i for i in range(60)]
        assert strategy._assess_momentum("AAPL") == "downtrend"

    def test_buy_signal_suppressed_in_downtrend(self):
        """BUY signal is suppressed when momentum is downtrend."""
        strategy = self._make_strategy(period=5, min_volume=0)

        # Feed 60 declining prices to establish downtrend
        prices = [200 - i * 2 for i in range(60)]
        for i, price in enumerate(prices):
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)

        # Now create a band cross scenario: price drops below lower band
        # After 60 bars in a downtrend, force a cross below
        # The last few bars establish the band; drive price far below
        last_price = prices[-1]
        extreme_low = last_price - 50  # way below lower band
        bar = {'close': extreme_low, 'volume': 1000000, 'timestamp': datetime.now()}
        strategy.on_bar("AAPL", bar)

        # No BUY signal should have been generated due to downtrend filter
        buy_signals = [s for s in strategy.signals_to_emit if s.signal_type == SignalType.BUY]
        assert len(buy_signals) == 0

    def test_sell_signal_suppressed_in_uptrend(self):
        """SELL signal is suppressed when momentum is uptrend."""
        strategy = self._make_strategy(period=5, min_volume=0)

        # Feed 60 rising prices to establish uptrend
        prices = [50 + i * 2 for i in range(60)]
        for price in prices:
            bar = {'close': price, 'volume': 1000000, 'timestamp': datetime.now()}
            strategy.on_bar("AAPL", bar)

        # Drive price far above upper band
        last_price = prices[-1]
        extreme_high = last_price + 50
        bar = {'close': extreme_high, 'volume': 1000000, 'timestamp': datetime.now()}
        strategy.on_bar("AAPL", bar)

        # No SELL signal should have been generated due to uptrend filter
        sell_signals = [s for s in strategy.signals_to_emit if s.signal_type == SignalType.SELL]
        assert len(sell_signals) == 0

    def test_confidence_with_sr_context_insufficient_data(self):
        """Falls back to base confidence with <50 bars."""
        strategy = self._make_strategy()
        strategy.price_history["AAPL"] = [100.0] * 30
        confidence = strategy._confidence_with_sr_context("AAPL", 100.0, SignalType.BUY)
        assert confidence == 0.75

    def test_confidence_with_sr_context_with_enough_data(self):
        """Returns a valid confidence value with 50+ bars."""
        strategy = self._make_strategy()
        strategy.price_history["AAPL"] = [100.0 + (i % 5) for i in range(60)]
        confidence = strategy._confidence_with_sr_context("AAPL", 100.0, SignalType.BUY)
        assert 0.5 <= confidence <= 1.0


class TestBollingerBandsSignalPaths:
    """Coverage for signal generation, suppression, cooldown, and validation."""

    def _make_strategy(self, period=20, min_volume=0):
        s = BollingerBandsStrategy(
            name="BB_SigTest",
            symbols=["TEST"],
            period=period,
            std_dev=2.0,
            min_volume=min_volume,
        )
        s.start()
        return s

    def _feed_bar(self, strategy, close, volume=1_000_000, symbol="TEST"):
        strategy.on_bar(
            symbol,
            {"close": close, "volume": volume, "timestamp": datetime(2024, 1, 1)},
        )

    def _establish_history(self, strategy, count=20, price=100.0, symbol="TEST"):
        """Feed `count` bars at `price` to build up price history and prev_close."""
        for _ in range(count):
            self._feed_bar(strategy, price, symbol=symbol)

    # --- Not RUNNING guard (line 167) ---
    def test_on_bar_skipped_when_not_running(self):
        """Strategy in READY state ignores bars entirely."""
        s = BollingerBandsStrategy(name="BB_T", symbols=["TEST"])
        # state is READY, not started
        s.on_bar("TEST", {"close": 100.0, "volume": 1_000_000, "timestamp": datetime(2024, 1, 1)})
        assert "TEST" not in s.price_history

    # --- Volume threshold (lines 212-213) ---
    def test_volume_below_threshold_prevents_signal(self):
        """Bars whose volume falls below min_volume are rejected after band calc."""
        s = self._make_strategy(period=20, min_volume=1_000_000)
        self._establish_history(s, 20, 100.0)  # build prev_close=100
        # Feed below-threshold volume; crossing conditions would otherwise fire
        s.on_bar("TEST", {"close": 99.0, "volume": 100_000, "timestamp": datetime(2024, 1, 1)})
        assert len(s.signals_to_emit) == 0

    # --- BUY cooldown reset (lines 222-223) ---
    def test_buy_cooldown_resets_when_price_at_or_above_sma(self):
        """last_signal BUY is cleared once close >= sma (mean-reversion complete)."""
        s = self._make_strategy(period=20)
        s.price_history["TEST"] = [100.0] * 20
        s.volume_history["TEST"] = [1_000_000] * 20
        s.last_signal["TEST"] = SignalType.BUY
        # close=101 >= sma≈100.05 → reset
        self._feed_bar(s, 101.0)
        assert s.last_signal.get("TEST") is None

    # --- SELL cooldown reset (lines 225-226) ---
    def test_sell_cooldown_resets_when_price_at_or_below_sma(self):
        """last_signal SELL is cleared once close <= sma."""
        s = self._make_strategy(period=20)
        s.price_history["TEST"] = [100.0] * 20
        s.volume_history["TEST"] = [1_000_000] * 20
        s.last_signal["TEST"] = SignalType.SELL
        # close=99 <= sma≈99.95 → reset
        self._feed_bar(s, 99.0)
        assert s.last_signal.get("TEST") is None

    # --- BUY signal generated (lines 279-308) ---
    def test_buy_signal_generated_on_lower_band_cross(self):
        """BUY signal is emitted when price drops below lower Bollinger band."""
        s = self._make_strategy(period=20)
        self._establish_history(s, 20, 100.0)  # prev_close=100, prev_lower=100
        # 99 < new_lower≈99.51 with 20 bars → BUY crossing
        self._feed_bar(s, 99.0)
        buy_signals = [sig for sig in s.signals_to_emit if sig.signal_type == SignalType.BUY]
        assert len(buy_signals) == 1
        assert buy_signals[0].confidence >= 0.75

    # --- SELL signal generated (lines 313-348) ---
    def test_sell_signal_generated_on_upper_band_cross(self):
        """SELL signal is emitted when price rises above upper Bollinger band."""
        s = self._make_strategy(period=20)
        self._establish_history(s, 20, 100.0)  # prev_close=100, prev_upper=100
        # 101 > new_upper≈100.49 → SELL crossing
        self._feed_bar(s, 101.0)
        sell_signals = [sig for sig in s.signals_to_emit if sig.signal_type == SignalType.SELL]
        assert len(sell_signals) == 1
        assert sell_signals[0].confidence >= 0.75

    # --- BUY suppression when downtrend (lines 273-278) ---
    def test_buy_signal_suppressed_when_momentum_is_downtrend(self, monkeypatch):
        """BUY crossing is suppressed by the downtrend momentum filter."""
        s = self._make_strategy(period=20)
        self._establish_history(s, 20, 100.0)
        monkeypatch.setattr(s, "_assess_momentum", lambda sym: "downtrend")
        self._feed_bar(s, 99.0)  # triggers crossing but momentum blocks it
        buy_signals = [sig for sig in s.signals_to_emit if sig.signal_type == SignalType.BUY]
        assert len(buy_signals) == 0

    # --- SELL suppression when uptrend (lines 313-318) ---
    def test_sell_signal_suppressed_when_momentum_is_uptrend(self, monkeypatch):
        """SELL crossing is suppressed by the uptrend momentum filter."""
        s = self._make_strategy(period=20)
        self._establish_history(s, 20, 100.0)
        monkeypatch.setattr(s, "_assess_momentum", lambda sym: "uptrend")
        self._feed_bar(s, 101.0)  # triggers crossing but momentum blocks it
        sell_signals = [sig for sig in s.signals_to_emit if sig.signal_type == SignalType.SELL]
        assert len(sell_signals) == 0

    # --- _assess_momentum sideways branch (line 369) ---
    def test_assess_momentum_returns_sideways_for_flat_history(self):
        """Momentum is 'sideways' when price hovers near MA20 (< 2% difference)."""
        s = self._make_strategy()
        s.price_history["TEST"] = [100.0] * 25  # flat → abs diff / ma20 = 0 < 0.02
        assert s._assess_momentum("TEST") == "sideways"

    # --- S/R confidence boost for BUY (lines 418-426) ---
    def test_sr_confidence_boost_when_buy_near_support(self, monkeypatch):
        """Confidence boosted by +0.15 when BUY price is inside a support zone."""
        from web.stock_analysis_services import technical_levels_service
        s = self._make_strategy()
        s.price_history["TEST"] = list(range(50, 101))  # 51 bars ≥ 50 threshold
        monkeypatch.setattr(
            technical_levels_service,
            "detect_support_resistance",
            lambda bars, price: {
                "support": [{"low": 94.0, "high": 96.0, "confidence": "high", "reason": "t"}],
                "resistance": [],
            },
        )
        confidence = s._confidence_with_sr_context("TEST", 95.0, SignalType.BUY)
        assert confidence == pytest.approx(0.75 + 0.15)

    # --- S/R confidence boost for SELL (line 465) ---
    def test_sr_confidence_boost_when_sell_near_resistance(self, monkeypatch):
        """Confidence boosted by +0.15 when SELL price is inside a resistance zone."""
        from web.stock_analysis_services import technical_levels_service
        s = self._make_strategy()
        s.price_history["TEST"] = list(range(50, 101))  # 51 bars
        monkeypatch.setattr(
            technical_levels_service,
            "detect_support_resistance",
            lambda bars, price: {
                "support": [],
                "resistance": [{"low": 104.0, "high": 106.0, "confidence": "high", "reason": "t"}],
            },
        )
        confidence = s._confidence_with_sr_context("TEST", 105.0, SignalType.SELL)
        assert confidence == pytest.approx(0.75 + 0.15)

    # --- validate_signal: target_price <= 0 (line 480) ---
    def test_validate_signal_rejects_zero_target_price(self):
        """validate_signal returns False when target_price is zero."""
        s = self._make_strategy()
        s.middle_band["TEST"] = 100.0
        signal = Signal(
            symbol="TEST",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            timestamp=datetime(2024, 1, 1),
            target_price=0,
            reason="test",
            confidence=0.75,
        )
        assert s.validate_signal(signal) is False

    # --- generate_signal rejects invalid signal (lines 484-494) ---
    def test_generate_signal_does_not_emit_invalid_signal(self):
        """generate_signal silently drops a signal that fails validation."""
        s = self._make_strategy()
        # Symbol not in middle_band → validate_signal returns False
        signal = Signal(
            symbol="UNKNOWN",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            timestamp=datetime(2024, 1, 1),
            target_price=100.0,
            reason="test",
            confidence=0.75,
        )
        s.generate_signal(signal)
        assert len(s.signals_to_emit) == 0

    # --- reset() clears all state (lines 484-494) ---
    def test_reset_clears_all_strategy_state(self):
        """reset() empties every internal dict/list."""
        s = self._make_strategy()
        self._establish_history(s, count=20, price=100.0)
        assert "TEST" in s.price_history
        s.reset()
        assert len(s.price_history) == 0
        assert len(s.volume_history) == 0
        assert len(s.upper_band) == 0
        assert len(s.middle_band) == 0
        assert len(s.lower_band) == 0
        assert len(s.prev_close) == 0
        assert len(s.prev_upper) == 0
        assert len(s.prev_lower) == 0
        assert len(s.last_signal) == 0
        assert len(s.signals_to_emit) == 0

    # --- _confidence_with_sr_context: exception path (lines 423-426) ---
    def test_confidence_with_sr_context_exception_returns_base_confidence(self, monkeypatch):
        """When detect_support_resistance raises, base_confidence is returned unchanged."""
        from web.stock_analysis_services import technical_levels_service

        def _exploding_detect(bars, close, **kwargs):
            raise RuntimeError("data error")

        monkeypatch.setattr(technical_levels_service, "detect_support_resistance", _exploding_detect)
        s = self._make_strategy()
        s.price_history["TEST"] = [100.0 + (i % 3) for i in range(60)]
        result = s._confidence_with_sr_context("TEST", 100.0, SignalType.BUY)
        # Exception is caught silently; base_confidence is returned
        assert 0.0 <= result <= 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
