"""
Test script for enhanced RiskManager.

Week 3 Day 1 - Validation tests.
"""

import sys
from datetime import datetime
from risk.risk_manager import RiskManager, Position, RiskStatus

def test_basic_risk_checks():
    """Test basic risk checking functionality."""
    print("=" * 70)
    print("TEST 1: Basic Risk Checks")
    print("=" * 70)
    
    risk_mgr = RiskManager(
        initial_capital=100000,
        max_positions=5,
        max_position_pct=0.20,
        max_drawdown_pct=0.15,
        daily_loss_limit_pct=0.05
    )
    
    positions = {}
    
    # Test 1: Normal trade approval
    can_trade, reason = risk_mgr.check_trade_risk(
        symbol="AAPL",
        side="LONG",
        quantity=100,
        price=150.0,
        positions=positions
    )
    print(f"\n✓ Normal trade: {can_trade} - {reason}")
    assert can_trade, "Normal trade should be approved"
    
    # Test 2: Position size too large
    can_trade, reason = risk_mgr.check_trade_risk(
        symbol="AAPL",
        side="LONG",
        quantity=1000,  # $150,000 value = 150% of equity
        price=150.0,
        positions=positions
    )
    print(f"✓ Oversized position: {can_trade} - {reason}")
    assert not can_trade, "Oversized position should be rejected"
    
    # Test 3: Max positions reached
    for i, sym in enumerate(["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]):
        positions[sym] = Position(
            symbol=sym,
            quantity=50,
            entry_price=100.0,
            current_price=100.0,
            side="LONG"
        )
    
    can_trade, reason = risk_mgr.check_trade_risk(
        symbol="META",
        side="LONG",
        quantity=50,
        price=200.0,
        positions=positions
    )
    print(f"✓ Max positions: {can_trade} - {reason}")
    assert not can_trade, "Should reject when max positions reached"
    
    print("\n✅ Basic risk checks PASSED")


def test_position_sizing():
    """Test position sizing calculations."""
    print("\n" + "=" * 70)
    print("TEST 2: Position Sizing")
    print("=" * 70)
    
    risk_mgr = RiskManager(
        initial_capital=100000,
        max_position_pct=0.25
    )
    
    # Test fixed percent sizing
    shares = risk_mgr.calculate_position_size(
        symbol="AAPL",
        price=150.0,
        strategy="fixed_percent",
        position_pct=0.20
    )
    expected_value = 100000 * 0.20  # $20,000
    expected_shares = int(expected_value / 150.0)  # 133 shares
    print(f"\n✓ Fixed % sizing (20%): {shares} shares")
    print(f"  Position value: ${shares * 150:,.2f}")
    assert shares == expected_shares, f"Expected {expected_shares} shares"
    
    # Test risk-based sizing
    shares = risk_mgr.calculate_position_size(
        symbol="AAPL",
        price=150.0,
        strategy="risk_based",
        risk_pct=0.02,  # Risk 2% of capital
        stop_loss_pct=0.05  # 5% stop loss
    )
    risk_amount = 100000 * 0.02  # $2,000 risk
    risk_per_share = 150.0 * 0.05  # $7.50 per share
    expected_shares = int(risk_amount / risk_per_share)  # 266 shares
    print(f"\n✓ Risk-based sizing (2% risk, 5% stop): {shares} shares")
    print(f"  Position value: ${shares * 150:,.2f}")
    print(f"  Risk amount: ${shares * risk_per_share:,.2f}")
    
    # Test Kelly criterion
    shares = risk_mgr.calculate_position_size(
        symbol="AAPL",
        price=150.0,
        strategy="kelly",
        win_rate=0.60,
        avg_win=0.03,
        avg_loss=0.02
    )
    print(f"\n✓ Kelly sizing (60% win rate): {shares} shares")
    print(f"  Position value: ${shares * 150:,.2f}")
    
    print("\n✅ Position sizing PASSED")


def test_drawdown_monitoring():
    """Test drawdown monitoring and emergency stop."""
    print("\n" + "=" * 70)
    print("TEST 3: Drawdown Monitoring")
    print("=" * 70)
    
    risk_mgr = RiskManager(
        initial_capital=100000,
        max_drawdown_pct=0.15,  # 15% max drawdown
        emergency_stop_enabled=True
    )
    
    positions = {}
    current_date = datetime.now()
    
    # Update with normal equity
    metrics = risk_mgr.update(100000, positions, current_date)
    print(f"\n✓ Initial state:")
    print(f"  Equity: ${metrics.equity:,.2f}")
    print(f"  Peak: ${risk_mgr.peak_equity:,.2f}")
    print(f"  Drawdown: {metrics.drawdown_pct:.2%}")
    print(f"  Status: {metrics.risk_status.value}")
    
    # Update with profit
    metrics = risk_mgr.update(110000, positions, current_date)
    print(f"\n✓ After profit:")
    print(f"  Equity: ${metrics.equity:,.2f}")
    print(f"  Peak: ${risk_mgr.peak_equity:,.2f}")
    print(f"  Drawdown: {metrics.drawdown_pct:.2%}")
    assert risk_mgr.peak_equity == 110000
    
    # Update with small loss (warning level)
    metrics = risk_mgr.update(100000, positions, current_date)
    print(f"\n✓ After 9% drawdown (WARNING):")
    print(f"  Equity: ${metrics.equity:,.2f}")
    print(f"  Peak: ${risk_mgr.peak_equity:,.2f}")
    print(f"  Drawdown: {metrics.drawdown_pct:.2%}")
    print(f"  Status: {metrics.risk_status.value}")
    assert metrics.risk_status == RiskStatus.WARNING
    
    # Update with large loss (emergency stop)
    metrics = risk_mgr.update(93000, positions, current_date)  # 15.5% drawdown
    print(f"\n✓ After 15.5% drawdown (EMERGENCY STOP):")
    print(f"  Equity: ${metrics.equity:,.2f}")
    print(f"  Peak: ${risk_mgr.peak_equity:,.2f}")
    print(f"  Drawdown: {metrics.drawdown_pct:.2%}")
    print(f"  Status: {metrics.risk_status.value}")
    print(f"  Emergency stop: {risk_mgr.emergency_stop_active}")
    assert risk_mgr.emergency_stop_active
    
    # Try to trade during emergency stop
    can_trade, reason = risk_mgr.check_trade_risk(
        symbol="AAPL",
        side="LONG",
        quantity=10,
        price=150.0,
        positions=positions
    )
    print(f"\n✓ Trade attempt during emergency stop: {can_trade} - {reason}")
    assert not can_trade
    
    print("\n✅ Drawdown monitoring PASSED")


def test_risk_metrics():
    """Test risk metrics calculation."""
    print("\n" + "=" * 70)
    print("TEST 4: Risk Metrics Calculation")
    print("=" * 70)
    
    risk_mgr = RiskManager(
        initial_capital=100000,
        max_leverage=2.0
    )
    
    # Create test positions
    positions = {
        "AAPL": Position(
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            current_price=155.0,
            side="LONG"
        ),
        "MSFT": Position(
            symbol="MSFT",
            quantity=50,
            entry_price=300.0,
            current_price=295.0,
            side="LONG"
        ),
    }
    
    current_date = datetime.now()
    metrics = risk_mgr.update(105000, positions, current_date)
    
    print(f"\n✓ Risk Metrics:")
    print(f"  Equity: ${metrics.equity:,.2f}")
    print(f"  Cash: ${metrics.cash:,.2f}")
    print(f"  Total Position Value: ${metrics.total_position_value:,.2f}")
    print(f"  Leverage: {metrics.leverage:.2f}x")
    print(f"  # Positions: {metrics.num_positions}")
    print(f"  Largest Position: {metrics.largest_position_pct:.1%}")
    print(f"  Unrealized P&L: ${metrics.unrealized_pnl:,.2f} ({metrics.unrealized_pnl_pct:.2%})")
    print(f"  Drawdown: ${metrics.drawdown:,.2f} ({metrics.drawdown_pct:.2%})")
    
    assert metrics.num_positions == 2
    assert metrics.leverage < 1.0  # Should be less than 1x
    
    # Get risk summary
    summary = risk_mgr.get_risk_summary()
    print(f"\n✓ Risk Summary:")
    print(f"  Status: {summary['risk_status']}")
    print(f"  Emergency Stop: {summary['emergency_stop_active']}")
    print(f"  Drawdown: {summary['drawdown_pct']:.2%}")
    
    print("\n✅ Risk metrics calculation PASSED")


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 70)
    print("WEEK 3 DAY 1: Enhanced RiskManager Validation")
    print("=" * 70)
    
    try:
        test_basic_risk_checks()
        test_position_sizing()
        test_drawdown_monitoring()
        test_risk_metrics()
        
        print("\n" + "=" * 70)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\n✅ Enhanced RiskManager is working correctly")
        print("✅ Ready for Week 3 Day 2: Position Sizing Algorithms")
        
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
