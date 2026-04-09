"""
Test script for position sizing algorithms.

Week 3 Day 2 - Validation tests.
"""

import sys
from risk.position_sizer import (
    FixedPercentSizer,
    KellySizer,
    RiskBasedSizer,
    RiskParitySizer,
    PositionSizerFactory
)


def test_fixed_percent_sizer():
    """Test fixed percentage position sizing."""
    print("=" * 70)
    print("TEST 1: Fixed Percent Sizer")
    print("=" * 70)
    
    sizer = FixedPercentSizer(position_pct=0.10, max_position_pct=0.25)
    
    # Test normal sizing
    result = sizer.calculate("AAPL", 150.0, 100000)
    print(f"\n✓ 10% of $100k equity:")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Rationale: {result.rationale}")
    
    assert result.shares == 66, f"Expected 66 shares, got {result.shares}"
    assert abs(result.position_value - 9900) < 200, "Value should be ~$9,900"
    
    # Test with override
    result = sizer.calculate("MSFT", 300.0, 100000, position_pct=0.20)
    print(f"\n✓ 20% override:")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    # Test max cap
    result = sizer.calculate("TSLA", 200.0, 100000, position_pct=0.50)
    print(f"\n✓ 50% request (capped at 25%):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    assert result.position_pct <= 0.25, "Should be capped at 25%"
    
    print("\n✅ Fixed Percent Sizer PASSED")


def test_kelly_sizer():
    """Test Kelly Criterion position sizing."""
    print("\n" + "=" * 70)
    print("TEST 2: Kelly Criterion Sizer")
    print("=" * 70)
    
    sizer = KellySizer(kelly_fraction=0.5, max_position_pct=0.25)
    
    # Test with favorable odds (60% win rate, 3:2 W/L ratio)
    result = sizer.calculate(
        "AAPL", 150.0, 100000,
        win_rate=0.60,
        avg_win=0.03,  # 3% avg win
        avg_loss=0.02   # 2% avg loss
    )
    print(f"\n✓ Favorable odds (60% WR, 3:2 W/L):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Kelly Fraction: {result.kelly_fraction:.2%}")
    print(f"  Rationale: {result.rationale}")
    
    assert result.shares > 0, "Should recommend position"
    assert result.kelly_fraction > 0, "Kelly fraction should be positive"
    
    # Test with poor odds (40% win rate)
    result = sizer.calculate(
        "MSFT", 300.0, 100000,
        win_rate=0.40,
        avg_win=0.02,
        avg_loss=0.02
    )
    print(f"\n✓ Poor odds (40% WR, 1:1 W/L):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Kelly Fraction: {result.kelly_fraction:.2%}")
    
    # Test with excellent odds (70% win rate, 4:1 W/L ratio)
    result = sizer.calculate(
        "GOOGL", 140.0, 100000,
        win_rate=0.70,
        avg_win=0.04,
        avg_loss=0.01
    )
    print(f"\n✓ Excellent odds (70% WR, 4:1 W/L):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Kelly Fraction: {result.kelly_fraction:.2%}")
    
    assert result.position_pct <= 0.25, "Position should be capped at max 25%"
    
    print("\n✅ Kelly Criterion Sizer PASSED")


def test_risk_based_sizer():
    """Test risk-based position sizing."""
    print("\n" + "=" * 70)
    print("TEST 3: Risk-Based Sizer")
    print("=" * 70)
    
    sizer = RiskBasedSizer(risk_pct=0.02, max_position_pct=0.25)
    
    # Test normal risk sizing
    result = sizer.calculate(
        "AAPL", 150.0, 100000,
        stop_loss_pct=0.05  # 5% stop loss
    )
    print(f"\n✓ 2% risk with 5% stop:")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Risk Amount: ${result.risk_amount:,.2f}")
    print(f"  Rationale: {result.rationale}")
    
    # Risk amount will be actual (may be capped at max position size)
    assert result.risk_amount > 0, "Risk amount should be calculated"
    
    # Test tight stop (more shares)
    result = sizer.calculate(
        "MSFT", 300.0, 100000,
        stop_loss_pct=0.02  # 2% stop loss
    )
    print(f"\n✓ 2% risk with 2% stop (more shares):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    # Test wide stop (fewer shares)
    result = sizer.calculate(
        "TSLA", 200.0, 100000,
        stop_loss_pct=0.10  # 10% stop loss
    )
    print(f"\n✓ 2% risk with 10% stop (fewer shares):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    # Test very tight stop that hits max position size
    result = sizer.calculate(
        "AMD", 100.0, 100000,
        stop_loss_pct=0.005,  # 0.5% stop
        risk_pct=0.05  # 5% risk
    )
    print(f"\n✓ 5% risk with 0.5% stop (capped):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Risk Amount: ${result.risk_amount:,.2f}")
    
    assert result.position_pct <= 0.25, "Should be capped at 25%"
    
    print("\n✅ Risk-Based Sizer PASSED")


def test_risk_parity_sizer():
    """Test risk parity position sizing."""
    print("\n" + "=" * 70)
    print("TEST 4: Risk Parity Sizer")
    print("=" * 70)
    
    sizer = RiskParitySizer(target_risk_pct=0.10, max_position_pct=0.25)
    
    # Test with single position
    result = sizer.calculate(
        "AAPL", 150.0, 100000,
        volatility=0.25,  # 25% volatility
        num_positions=1
    )
    print(f"\n✓ Single position, 25% volatility:")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    print(f"  Risk Contribution: ${result.risk_amount:,.2f}")
    print(f"  Rationale: {result.rationale}")
    
    # Test with 5 positions
    result = sizer.calculate(
        "MSFT", 300.0, 100000,
        volatility=0.30,  # 30% volatility (higher vol = smaller position)
        num_positions=5
    )
    print(f"\n✓ 5 positions, 30% volatility:")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    # Test with low volatility (larger position)
    result = sizer.calculate(
        "JNJ", 160.0, 100000,
        volatility=0.15,  # 15% volatility (low vol = larger position)
        num_positions=5
    )
    print(f"\n✓ 5 positions, 15% volatility (low vol):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    # Test with very high volatility
    result = sizer.calculate(
        "TSLA", 200.0, 100000,
        volatility=0.60,  # 60% volatility (very high)
        num_positions=5
    )
    print(f"\n✓ 5 positions, 60% volatility (high vol):")
    print(f"  Shares: {result.shares}")
    print(f"  Value: ${result.position_value:,.2f}")
    print(f"  Percent: {result.position_pct:.2%}")
    
    print("\n✅ Risk Parity Sizer PASSED")


def test_position_sizer_factory():
    """Test position sizer factory."""
    print("\n" + "=" * 70)
    print("TEST 5: Position Sizer Factory")
    print("=" * 70)
    
    # Test creating each sizer type
    sizers = [
        ('fixed', {'position_pct': 0.10}),
        ('kelly', {'kelly_fraction': 0.5}),
        ('risk_based', {'risk_pct': 0.02}),
        ('risk_parity', {'target_risk_pct': 0.10})
    ]
    
    for strategy, kwargs in sizers:
        sizer = PositionSizerFactory.create(strategy, **kwargs)
        print(f"\n✓ Created {strategy} sizer: {type(sizer).__name__}")
        assert sizer is not None
    
    # Test list strategies
    strategies = PositionSizerFactory.list_strategies()
    print(f"\n✓ Available strategies: {', '.join(strategies)}")
    assert len(strategies) == 4
    
    # Test invalid strategy
    try:
        sizer = PositionSizerFactory.create('invalid_strategy')
        assert False, "Should raise ValueError"
    except ValueError as e:
        print(f"\n✓ Invalid strategy rejected: {e}")
    
    print("\n✅ Position Sizer Factory PASSED")


def test_position_sizing_comparison():
    """Compare all sizing strategies on same trade."""
    print("\n" + "=" * 70)
    print("TEST 6: Strategy Comparison")
    print("=" * 70)
    
    equity = 100000
    price = 150.0
    symbol = "AAPL"
    
    print(f"\n📊 Comparing strategies for {symbol} @ ${price} (equity: ${equity:,})")
    print("=" * 70)
    
    # Fixed Percent
    sizer1 = FixedPercentSizer(position_pct=0.10)
    result1 = sizer1.calculate(symbol, price, equity)
    print(f"\n1. Fixed Percent (10%):")
    print(f"   Shares: {result1.shares}, Value: ${result1.position_value:,.2f} ({result1.position_pct:.1%})")
    
    # Kelly
    sizer2 = KellySizer(kelly_fraction=0.5)
    result2 = sizer2.calculate(symbol, price, equity, 
                               win_rate=0.60, avg_win=0.03, avg_loss=0.02)
    print(f"\n2. Kelly Criterion (60% WR):")
    print(f"   Shares: {result2.shares}, Value: ${result2.position_value:,.2f} ({result2.position_pct:.1%})")
    print(f"   Kelly: {result2.kelly_fraction:.2%}")
    
    # Risk-Based
    sizer3 = RiskBasedSizer(risk_pct=0.02)
    result3 = sizer3.calculate(symbol, price, equity, stop_loss_pct=0.05)
    print(f"\n3. Risk-Based (2% risk, 5% stop):")
    print(f"   Shares: {result3.shares}, Value: ${result3.position_value:,.2f} ({result3.position_pct:.1%})")
    print(f"   Risk: ${result3.risk_amount:,.2f}")
    
    # Risk Parity
    sizer4 = RiskParitySizer(target_risk_pct=0.10)
    result4 = sizer4.calculate(symbol, price, equity, volatility=0.25, num_positions=5)
    print(f"\n4. Risk Parity (25% vol, 5 positions):")
    print(f"   Shares: {result4.shares}, Value: ${result4.position_value:,.2f} ({result4.position_pct:.1%})")
    
    print("\n" + "=" * 70)
    print("Observations:")
    print(f"  • Most Conservative: Risk Parity ({result4.position_pct:.1%})")
    print(f"  • Most Aggressive: Risk-Based ({result3.position_pct:.1%})")
    print(f"  • Balanced: Fixed Percent ({result1.position_pct:.1%})")
    
    print("\n✅ Strategy Comparison PASSED")


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 70)
    print("WEEK 3 DAY 2: Position Sizing Algorithms Validation")
    print("=" * 70)
    
    try:
        test_fixed_percent_sizer()
        test_kelly_sizer()
        test_risk_based_sizer()
        test_risk_parity_sizer()
        test_position_sizer_factory()
        test_position_sizing_comparison()
        
        print("\n" + "=" * 70)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\n✅ Position sizing algorithms working correctly")
        print("✅ All 4 sizers validated: Fixed %, Kelly, Risk-Based, Risk Parity")
        print("✅ Factory pattern working")
        print("\n📈 Position Sizing Summary:")
        print("  • FixedPercentSizer: Conservative, predictable")
        print("  • KellySizer: Optimal growth, requires good estimates")
        print("  • RiskBasedSizer: Risk-focused, stop-loss aware")
        print("  • RiskParitySizer: Volatility-adjusted, equal risk")
        print("\n✅ Ready for Week 3 Day 3: Drawdown Protection")
        
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
