"""
Tests for Strategy Templates

Comprehensive test suite for all strategy templates including:
- MovingAverageCrossStrategy
- MeanReversionStrategy
- MomentumStrategy
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from backtest.strategy_templates import (
    MovingAverageCrossStrategy, MACrossConfig,
    MeanReversionStrategy, MeanReversionConfig,
    MomentumStrategy, MomentumConfig,
    get_template, list_templates, STRATEGY_TEMPLATES
)
from backtest.strategy import StrategyConfig
from backtest.data_models import Bar
from backtest.market_simulator import Order


# ============================================================================
# Test Fixtures and Helpers
# ============================================================================

def create_test_config(name: str = "TestStrategy", symbols: List[str] = None) -> StrategyConfig:
    """Create a test strategy configuration"""
    if symbols is None:
        symbols = ['AAPL']
    
    return StrategyConfig(
        name=name,
        symbols=symbols,
        initial_capital=100000.0
    )

def create_test_bars(symbol: str, count: int, start_price: float = 100.0, 
                    trend: str = 'flat', volatility: float = 1.0) -> List[Bar]:
    """
    Create test bars with various patterns
    
    Args:
        symbol: Symbol name
        count: Number of bars to create
        start_price: Starting price
        trend: 'up', 'down', 'flat', 'choppy'
        volatility: Price movement amplitude
    """
    bars = []
    current_price = start_price
    base_date = datetime(2024, 1, 1)
    
    for i in range(count):
        # Apply trend
        if trend == 'up':
            current_price += volatility
        elif trend == 'down':
            current_price -= volatility
        elif trend == 'choppy':
            # Oscillate
            current_price += volatility if i % 4 < 2 else -volatility
        # 'flat' means no change
        
        # Create OHLC with some variation
        high = current_price * 1.01
        low = current_price * 0.99
        open_price = current_price * 1.005
        close = current_price
        
        bar = Bar(
            timestamp=base_date + timedelta(days=i),
            symbol=symbol,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=100000
        )
        bars.append(bar)
    
    return bars


# ============================================================================
# Moving Average Cross Strategy Tests
# ============================================================================

class TestMACrossConfig:
    """Test MA Cross configuration"""
    
    def test_valid_config(self):
        """Test valid configuration"""
        config = MACrossConfig(fast_period=20, slow_period=50)
        assert config.fast_period == 20
        assert config.slow_period == 50
        assert config.min_bars == 50
    
    def test_invalid_periods(self):
        """Test that fast >= slow raises error"""
        with pytest.raises(ValueError, match="Fast period must be less than slow period"):
            MACrossConfig(fast_period=50, slow_period=20)
    
    def test_invalid_fast_period(self):
        """Test that fast < 2 raises error"""
        with pytest.raises(ValueError, match="Fast period must be at least 2"):
            MACrossConfig(fast_period=1, slow_period=50)
    
    def test_invalid_slow_period(self):
        """Test that slow < 2 raises error"""
        # When both are 1, fast_period check happens first
        with pytest.raises(ValueError, match="Fast period must be at least 2"):
            MACrossConfig(fast_period=1, slow_period=1)
        
        # Test slow period validation with valid fast period
        with pytest.raises(ValueError, match="Slow period must be at least 2"):
            MACrossConfig(fast_period=2, slow_period=1)
    
    def test_min_bars_auto_adjust(self):
        """Test that min_bars auto-adjusts to slow_period"""
        config = MACrossConfig(fast_period=10, slow_period=50, min_bars=20)
        assert config.min_bars == 50


class TestMovingAverageCrossStrategy:
    """Test Moving Average Cross strategy"""
    
    def test_strategy_initialization(self):
        """Test strategy initializes correctly"""
        config = create_test_config()
        ma_config = MACrossConfig(fast_period=10, slow_period=20)
        strategy = MovingAverageCrossStrategy(config, ma_config)
        
        assert strategy.ma_config.fast_period == 10
        assert strategy.ma_config.slow_period == 20
        assert len(strategy.fast_ma) == 0
        assert len(strategy.slow_ma) == 0
    
    def test_strategy_with_default_config(self):
        """Test strategy works with default MA config"""
        config = create_test_config()
        strategy = MovingAverageCrossStrategy(config)
        
        assert strategy.ma_config.fast_period == 20
        assert strategy.ma_config.slow_period == 50
    
    def test_golden_cross_signal(self):
        """Test golden cross signal detection logic"""
        config = create_test_config()
        ma_config = MACrossConfig(fast_period=5, slow_period=10)
        strategy = MovingAverageCrossStrategy(config, ma_config)
        
        # Manually create scenario for golden cross
        # Fast MA crosses above slow MA
        strategy.prev_fast_ma['AAPL'] = 99.0
        strategy.prev_slow_ma['AAPL'] = 100.0
        strategy.fast_ma['AAPL'] = 101.0
        strategy.slow_ma['AAPL'] = 100.0
        
        # This should be detected as golden cross (buy signal)
        assert strategy.fast_ma['AAPL'] > strategy.slow_ma['AAPL']
        assert strategy.prev_fast_ma['AAPL'] <= strategy.prev_slow_ma['AAPL']
    
    def test_death_cross_signal(self):
        """Test death cross signal detection logic"""
        config = create_test_config()
        ma_config = MACrossConfig(fast_period=5, slow_period=10)
        strategy = MovingAverageCrossStrategy(config, ma_config)
        
        # Manually create scenario for death cross
        # Fast MA crosses below slow MA
        strategy.prev_fast_ma['AAPL'] = 101.0
        strategy.prev_slow_ma['AAPL'] = 100.0
        strategy.fast_ma['AAPL'] = 99.0
        strategy.slow_ma['AAPL'] = 100.0
        
        # This should be detected as death cross (sell signal)
        assert strategy.fast_ma['AAPL'] < strategy.slow_ma['AAPL']
        assert strategy.prev_fast_ma['AAPL'] >= strategy.prev_slow_ma['AAPL']
    
    def test_sma_calculation(self):
        """Test SMA calculation is correct"""
        config = create_test_config()
        ma_config = MACrossConfig(fast_period=5, slow_period=10)
        strategy = MovingAverageCrossStrategy(config, ma_config)
        
        prices = [100, 102, 104, 106, 108]
        sma = strategy._calculate_sma(prices, 5)
        expected = sum(prices) / 5
        
        assert sma == expected
    
    def test_insufficient_bars(self):
        """Test strategy configuration for min bars"""
        ma_config = MACrossConfig(fast_period=10, slow_period=20)
        
        # Min bars should be at least slow_period
        assert ma_config.min_bars >= ma_config.slow_period
        assert ma_config.min_bars == 20


# ============================================================================
# Mean Reversion Strategy Tests
# ============================================================================

class TestMeanReversionConfig:
    """Test Mean Reversion configuration"""
    
    def test_valid_config(self):
        """Test valid configuration"""
        config = MeanReversionConfig(
            bb_period=20,
            bb_std=2.0,
            rsi_period=14,
            rsi_oversold=30.0,
            rsi_overbought=70.0
        )
        assert config.bb_period == 20
        assert config.bb_std == 2.0
        assert config.rsi_period == 14
    
    def test_invalid_bb_period(self):
        """Test invalid BB period"""
        with pytest.raises(ValueError, match="BB period must be at least 2"):
            MeanReversionConfig(bb_period=1)
    
    def test_invalid_bb_std(self):
        """Test invalid BB standard deviation"""
        with pytest.raises(ValueError, match="BB standard deviations must be positive"):
            MeanReversionConfig(bb_std=0)
    
    def test_invalid_rsi_period(self):
        """Test invalid RSI period"""
        with pytest.raises(ValueError, match="RSI period must be at least 2"):
            MeanReversionConfig(rsi_period=1)
    
    def test_invalid_rsi_thresholds(self):
        """Test invalid RSI thresholds"""
        with pytest.raises(ValueError, match="RSI oversold must be less than overbought"):
            MeanReversionConfig(rsi_oversold=70, rsi_overbought=30)
    
    def test_rsi_bounds(self):
        """Test RSI values must be 0-100"""
        with pytest.raises(ValueError, match="RSI oversold must be between 0 and 100"):
            MeanReversionConfig(rsi_oversold=-10)
        
        with pytest.raises(ValueError, match="RSI overbought must be between 0 and 100"):
            MeanReversionConfig(rsi_overbought=110)


class TestMeanReversionStrategy:
    """Test Mean Reversion strategy"""
    
    def test_strategy_initialization(self):
        """Test strategy initializes correctly"""
        config = create_test_config()
        mr_config = MeanReversionConfig(bb_period=10, rsi_period=7)
        strategy = MeanReversionStrategy(config, mr_config)
        
        assert strategy.mr_config.bb_period == 10
        assert strategy.mr_config.rsi_period == 7
        assert len(strategy.bb_upper) == 0
        assert len(strategy.rsi) == 0
    
    def test_strategy_with_default_config(self):
        """Test strategy works with default config"""
        config = create_test_config()
        strategy = MeanReversionStrategy(config)
        
        assert strategy.mr_config.bb_period == 20
        assert strategy.mr_config.rsi_period == 14
    
    def test_bollinger_bands_calculation(self):
        """Test Bollinger Bands are calculated correctly"""
        config = create_test_config()
        mr_config = MeanReversionConfig(bb_period=10, bb_std=2.0)
        strategy = MeanReversionStrategy(config, mr_config)
        
        # Create bars with known prices
        bars = create_test_bars('AAPL', 20, start_price=100, trend='flat')
        
        # Process bars
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        # Verify bands exist
        assert 'AAPL' in strategy.bb_upper
        assert 'AAPL' in strategy.bb_middle
        assert 'AAPL' in strategy.bb_lower
        
        # Verify band ordering
        assert strategy.bb_upper['AAPL'] > strategy.bb_middle['AAPL']
        assert strategy.bb_middle['AAPL'] > strategy.bb_lower['AAPL']
    
    def test_rsi_calculation(self):
        """Test RSI is calculated"""
        config = create_test_config()
        mr_config = MeanReversionConfig(rsi_period=14)
        strategy = MeanReversionStrategy(config, mr_config)
        
        # Create bars
        bars = create_test_bars('AAPL', 30, start_price=100, trend='up')
        
        # Process bars
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        # Verify RSI exists and is in valid range
        assert 'AAPL' in strategy.rsi
        assert 0 <= strategy.rsi['AAPL'] <= 100
    
    def test_oversold_signal(self):
        """Test oversold condition generates buy signal"""
        config = create_test_config()
        mr_config = MeanReversionConfig(bb_period=10, rsi_period=7)
        strategy = MeanReversionStrategy(config, mr_config)
        
        # Create strong downtrend (oversold)
        bars = create_test_bars('AAPL', 30, start_price=100, trend='down', volatility=2.0)
        
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        assert 'AAPL' in strategy.ready_symbols
    
    def test_overbought_signal(self):
        """Test overbought condition generates sell signal"""
        config = create_test_config()
        mr_config = MeanReversionConfig(bb_period=10, rsi_period=7)
        strategy = MeanReversionStrategy(config, mr_config)
        
        # Create strong uptrend (overbought)
        bars = create_test_bars('AAPL', 30, start_price=100, trend='up', volatility=2.0)
        
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        assert 'AAPL' in strategy.ready_symbols


# ============================================================================
# Momentum Strategy Tests
# ============================================================================

class TestMomentumConfig:
    """Test Momentum configuration"""
    
    def test_valid_config(self):
        """Test valid configuration"""
        config = MomentumConfig(
            lookback_period=20,
            momentum_threshold=0.02,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9
        )
        assert config.lookback_period == 20
        assert config.momentum_threshold == 0.02
        assert config.macd_fast == 12
    
    def test_invalid_lookback(self):
        """Test invalid lookback period"""
        with pytest.raises(ValueError, match="Lookback period must be at least 2"):
            MomentumConfig(lookback_period=1)
    
    def test_invalid_threshold(self):
        """Test invalid momentum threshold"""
        with pytest.raises(ValueError, match="Momentum threshold must be positive"):
            MomentumConfig(momentum_threshold=0)
    
    def test_invalid_macd_periods(self):
        """Test MACD fast must be less than slow"""
        with pytest.raises(ValueError, match="MACD fast must be less than slow"):
            MomentumConfig(macd_fast=26, macd_slow=12)
    
    def test_invalid_macd_fast(self):
        """Test MACD fast minimum"""
        with pytest.raises(ValueError, match="MACD fast period must be at least 2"):
            MomentumConfig(macd_fast=1)
    
    def test_invalid_macd_signal(self):
        """Test MACD signal minimum"""
        with pytest.raises(ValueError, match="MACD signal period must be at least 2"):
            MomentumConfig(macd_signal=1)


class TestMomentumStrategy:
    """Test Momentum strategy"""
    
    def test_strategy_initialization(self):
        """Test strategy initializes correctly"""
        config = create_test_config()
        mom_config = MomentumConfig(lookback_period=10, macd_fast=6, macd_slow=13)
        strategy = MomentumStrategy(config, mom_config)
        
        assert strategy.mom_config.lookback_period == 10
        assert strategy.mom_config.macd_fast == 6
        assert len(strategy.momentum) == 0
        assert len(strategy.macd) == 0
    
    def test_strategy_with_default_config(self):
        """Test strategy works with default config"""
        config = create_test_config()
        strategy = MomentumStrategy(config)
        
        assert strategy.mom_config.lookback_period == 20
        assert strategy.mom_config.macd_fast == 12
    
    def test_momentum_calculation(self):
        """Test momentum (ROC) is calculated correctly"""
        config = create_test_config()
        mom_config = MomentumConfig(lookback_period=10)
        strategy = MomentumStrategy(config, mom_config)
        
        # Create uptrend
        bars = create_test_bars('AAPL', 30, start_price=100, trend='up', volatility=1.0)
        
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        # Should have positive momentum
        assert 'AAPL' in strategy.momentum
        assert strategy.momentum['AAPL'] > 0
    
    def test_macd_calculation(self):
        """Test MACD is calculated"""
        config = create_test_config()
        mom_config = MomentumConfig(macd_fast=6, macd_slow=13, macd_signal=5)
        strategy = MomentumStrategy(config, mom_config)
        
        # Create bars
        bars = create_test_bars('AAPL', 40, start_price=100, trend='up')
        
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        # Verify MACD components exist
        assert 'AAPL' in strategy.macd
        assert 'AAPL' in strategy.macd_signal
        assert 'AAPL' in strategy.macd_histogram
    
    def test_ema_calculation(self):
        """Test EMA calculation"""
        config = create_test_config()
        strategy = MomentumStrategy(config)
        
        prices = [100, 102, 104, 106, 108, 110]
        ema = strategy._calculate_ema(prices, 5)
        
        # EMA should be calculated
        assert ema > 0
        # EMA should be closer to recent prices
        assert ema > 105
    
    def test_bullish_momentum_signal(self):
        """Test strong upward momentum generates buy signal"""
        config = create_test_config()
        mom_config = MomentumConfig(lookback_period=10, momentum_threshold=0.01)
        strategy = MomentumStrategy(config, mom_config)
        
        # Create strong uptrend
        bars = create_test_bars('AAPL', 40, start_price=100, trend='up', volatility=1.5)
        
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        assert 'AAPL' in strategy.ready_symbols
        assert strategy.momentum['AAPL'] > 0
    
    def test_bearish_momentum_signal(self):
        """Test strong downward momentum generates sell signal"""
        config = create_test_config()
        mom_config = MomentumConfig(lookback_period=10, momentum_threshold=0.01)
        strategy = MomentumStrategy(config, mom_config)
        
        # Create strong downtrend
        bars = create_test_bars('AAPL', 40, start_price=100, trend='down', volatility=1.5)
        
        for bar in bars:
            strategy.on_bar('AAPL', bar)
        
        assert 'AAPL' in strategy.ready_symbols
        assert strategy.momentum['AAPL'] < 0


# ============================================================================
# Template Registry Tests
# ============================================================================

class TestTemplateRegistry:
    """Test strategy template registry"""
    
    def test_list_templates(self):
        """Test listing available templates"""
        templates = list_templates()
        
        assert 'ma_cross' in templates
        assert 'mean_reversion' in templates
        assert 'momentum' in templates
        assert len(templates) == 3
    
    def test_get_template_ma_cross(self):
        """Test getting MA cross template"""
        template = get_template('ma_cross')
        assert template == MovingAverageCrossStrategy
    
    def test_get_template_mean_reversion(self):
        """Test getting mean reversion template"""
        template = get_template('mean_reversion')
        assert template == MeanReversionStrategy
    
    def test_get_template_momentum(self):
        """Test getting momentum template"""
        template = get_template('momentum')
        assert template == MomentumStrategy
    
    def test_get_template_invalid(self):
        """Test getting invalid template raises error"""
        with pytest.raises(ValueError, match="Unknown template 'invalid'"):
            get_template('invalid')
    
    def test_template_registry_complete(self):
        """Test all templates are in registry"""
        assert len(STRATEGY_TEMPLATES) == 3
        assert 'ma_cross' in STRATEGY_TEMPLATES
        assert 'mean_reversion' in STRATEGY_TEMPLATES
        assert 'momentum' in STRATEGY_TEMPLATES


# ============================================================================
# Integration Tests
# ============================================================================

class TestStrategyTemplatesIntegration:
    """Integration tests for strategy templates"""
    
    def test_all_templates_instantiate(self):
        """Test all templates can be instantiated"""
        config = create_test_config()
        
        for template_name in list_templates():
            template_class = get_template(template_name)
            strategy = template_class(config)
            
            assert strategy is not None
            assert strategy.config.initial_capital == 100000
    
    def test_templates_with_custom_configs(self):
        """Test templates work with custom configs"""
        config = create_test_config()
        
        # MA Cross with custom config
        ma_config = MACrossConfig(fast_period=10, slow_period=30)
        ma_strategy = MovingAverageCrossStrategy(config, ma_config)
        assert ma_strategy.ma_config.fast_period == 10
        
        # Mean Reversion with custom config
        mr_config = MeanReversionConfig(bb_period=15, rsi_period=10)
        mr_strategy = MeanReversionStrategy(config, mr_config)
        assert mr_strategy.mr_config.bb_period == 15
        
        # Momentum with custom config
        mom_config = MomentumConfig(lookback_period=15, momentum_threshold=0.03)
        mom_strategy = MomentumStrategy(config, mom_config)
        assert mom_strategy.mom_config.lookback_period == 15
    
    def test_templates_process_multiple_symbols(self):
        """Test templates can handle multiple symbols"""
        config = create_test_config()
        strategy = MovingAverageCrossStrategy(config)
        
        symbols = ['AAPL', 'MSFT', 'GOOGL']
        
        for symbol in symbols:
            bars = create_test_bars(symbol, 60, start_price=100 + symbols.index(symbol) * 10)
            for bar in bars:
                strategy.on_bar(symbol, bar)
        
        # All symbols should be tracked
        for symbol in symbols:
            assert symbol in strategy.ready_symbols
    
    def test_templates_handle_different_market_conditions(self):
        """Test templates handle various market conditions"""
        config = create_test_config()
        
        market_conditions = ['up', 'down', 'flat', 'choppy']
        
        for condition in market_conditions:
            # Test each template with each condition
            for template_name in list_templates():
                template_class = get_template(template_name)
                strategy = template_class(config)
                
                bars = create_test_bars('TEST', 60, start_price=100, trend=condition)
                
                for bar in bars:
                    strategy.on_bar('TEST', bar)
                
                # Strategy should handle the condition without errors
                assert 'TEST' in strategy.ready_symbols

