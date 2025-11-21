"""
Validation Tests for Drawdown Protection & Monitoring System

Tests all drawdown control features including:
- Real-time drawdown tracking
- Peak equity updates
- Protective stop triggers (daily, weekly, max drawdown)
- Position scaling during drawdown
- Recovery detection and event logging

Author: Trading Bot Development Team
Date: November 21, 2025
"""

from datetime import datetime, timedelta
from risk.drawdown_control import (
    DrawdownMonitor,
    DrawdownMetrics,
    DrawdownSeverity,
)


def test_basic_drawdown_tracking():
    """Test basic drawdown calculation and tracking"""
    print("\n" + "=" * 70)
    print("TEST 1: Basic Drawdown Tracking")
    print("=" * 70)
    
    monitor = DrawdownMonitor(
        initial_equity=100000,
        daily_loss_limit_pct=0.50,  # Set high to not interfere with test
        weekly_loss_limit_pct=0.50,
    )
    
    # Day 1: Starting equity
    date1 = datetime(2025, 1, 1)
    metrics1 = monitor.update(100000, date1)
    print(f"\n✓ Day 1 (Peak): ${metrics1.current_equity:,.0f}")
    print(f"  Drawdown: {metrics1.drawdown_pct:.2f}%")
    print(f"  Severity: {metrics1.severity.value}")
    assert metrics1.drawdown_pct == 0.0
    assert metrics1.severity == DrawdownSeverity.NORMAL
    assert metrics1.position_scale_factor == 1.0
    
    # Day 2: 5% loss (minor drawdown)
    date2 = datetime(2025, 1, 2)
    metrics2 = monitor.update(95000, date2)
    print(f"\n✓ Day 2 (5% loss): ${metrics2.current_equity:,.0f}")
    print(f"  Drawdown: {metrics2.drawdown_pct:.2f}%")
    print(f"  Severity: {metrics2.severity.value}")
    print(f"  Position Scale: {metrics2.position_scale_factor:.2f}x")
    assert abs(metrics2.drawdown_pct - 5.0) < 0.1
    assert metrics2.severity == DrawdownSeverity.MINOR
    assert metrics2.position_scale_factor == 1.0  # No scaling yet
    
    # Day 3: 12% loss (moderate drawdown)
    date3 = datetime(2025, 1, 3)
    metrics3 = monitor.update(88000, date3)
    print(f"\n✓ Day 3 (12% loss): ${metrics3.current_equity:,.0f}")
    print(f"  Drawdown: {metrics3.drawdown_pct:.2f}%")
    print(f"  Severity: {metrics3.severity.value}")
    print(f"  Position Scale: {metrics3.position_scale_factor:.2f}x")
    assert abs(metrics3.drawdown_pct - 12.0) < 0.1
    assert metrics3.severity == DrawdownSeverity.MODERATE
    assert metrics3.position_scale_factor < 1.0  # Scaling kicks in
    
    # Day 4: Recovery to 8% loss
    date4 = datetime(2025, 1, 4)
    metrics4 = monitor.update(92000, date4)
    print(f"\n✓ Day 4 (Recovery to 8% loss): ${metrics4.current_equity:,.0f}")
    print(f"  Drawdown: {metrics4.drawdown_pct:.2f}%")
    print(f"  Severity: {metrics4.severity.value}")
    print(f"  Bars in DD: {metrics4.bars_in_drawdown}")
    assert abs(metrics4.drawdown_pct - 8.0) < 0.1
    assert metrics4.severity == DrawdownSeverity.MINOR
    assert metrics4.bars_in_drawdown == 4  # Still counting
    
    # Day 5: Full recovery (new peak)
    date5 = datetime(2025, 1, 5)
    metrics5 = monitor.update(101000, date5)
    print(f"\n✓ Day 5 (New Peak): ${metrics5.current_equity:,.0f}")
    print(f"  Drawdown: {metrics5.drawdown_pct:.2f}%")
    print(f"  Severity: {metrics5.severity.value}")
    print(f"  Bars in DD: {metrics5.bars_in_drawdown}")
    assert metrics5.drawdown_pct == 0.0
    assert metrics5.severity == DrawdownSeverity.NORMAL
    assert metrics5.bars_in_drawdown == 0  # Reset
    assert len(monitor.drawdown_events) == 1  # Event recorded
    
    print(f"\n✓ Drawdown event recorded: {monitor.drawdown_events[0]}")
    
    print("\n✅ Basic Drawdown Tracking PASSED")
    return True


def test_protective_stops():
    """Test daily, weekly, and max drawdown protective stops"""
    print("\n" + "=" * 70)
    print("TEST 2: Protective Stops")
    print("=" * 70)
    
    # Test 1: Daily loss limit
    monitor1 = DrawdownMonitor(
        initial_equity=100000,
        daily_loss_limit_pct=0.05,  # 5% daily limit
    )
    
    date1 = datetime(2025, 1, 1, 9, 0)  # Morning
    monitor1.update(100000, date1)
    
    date2 = datetime(2025, 1, 1, 16, 0)  # Afternoon (same day, -6% loss)
    metrics1 = monitor1.update(94000, date2)
    
    print(f"\n✓ Daily Loss Limit Test:")
    print(f"  Equity: ${metrics1.current_equity:,.0f} (-6%)")
    print(f"  Daily P&L: {metrics1.daily_pnl_pct:.2f}%")
    print(f"  Trading Halted: {metrics1.is_trading_halted}")
    print(f"  Reason: {metrics1.halt_reason}")
    
    assert metrics1.is_trading_halted == True
    assert "Daily loss limit" in metrics1.halt_reason
    
    # Test 2: Weekly loss limit
    monitor2 = DrawdownMonitor(
        initial_equity=100000,
        weekly_loss_limit_pct=0.10,  # 10% weekly limit
    )
    
    start_date = datetime(2025, 1, 1)
    monitor2.update(100000, start_date)
    
    # Day 1-5: Gradual losses totaling 11%
    for day in range(1, 6):
        date = start_date + timedelta(days=day)
        equity = 100000 - (day * 2200)  # Lose 2.2% per day
        metrics = monitor2.update(equity, date)
    
    print(f"\n✓ Weekly Loss Limit Test:")
    print(f"  Final Equity: ${metrics.current_equity:,.0f}")
    print(f"  Weekly P&L: {metrics.weekly_pnl_pct:.2f}%")
    print(f"  Trading Halted: {metrics.is_trading_halted}")
    print(f"  Reason: {metrics.halt_reason}")
    
    assert metrics.is_trading_halted == True
    assert "Weekly loss limit" in metrics.halt_reason
    
    # Test 3: Max drawdown limit
    monitor3 = DrawdownMonitor(
        initial_equity=100000,
        max_drawdown_pct=0.20,  # 20% max drawdown
    )
    
    date_start = datetime(2025, 1, 1)
    monitor3.update(100000, date_start)
    
    # Large single-day loss of 21%
    date_crash = datetime(2025, 1, 2)
    metrics3 = monitor3.update(79000, date_crash)
    
    print(f"\n✓ Max Drawdown Limit Test:")
    print(f"  Equity: ${metrics3.current_equity:,.0f}")
    print(f"  Drawdown: {metrics3.drawdown_pct:.2f}%")
    print(f"  Severity: {metrics3.severity.value}")
    print(f"  Trading Halted: {metrics3.is_trading_halted}")
    print(f"  Reason: {metrics3.halt_reason}")
    
    assert metrics3.is_trading_halted == True
    assert metrics3.severity == DrawdownSeverity.CRITICAL
    assert "Maximum drawdown limit" in metrics3.halt_reason
    
    print("\n✅ Protective Stops PASSED")
    return True


def test_position_scaling():
    """Test position sizing scale factor during drawdown"""
    print("\n" + "=" * 70)
    print("TEST 3: Position Scaling on Drawdown")
    print("=" * 70)
    
    monitor = DrawdownMonitor(
        initial_equity=100000,
        scale_positions_on_drawdown=True,
        minor_drawdown_threshold=0.05,
        max_drawdown_pct=0.20,
        daily_loss_limit_pct=0.50,  # High to not interfere
        weekly_loss_limit_pct=0.50,
    )
    
    scenarios = [
        (100000, 0.0, 1.00, "NORMAL"),        # No drawdown
        (96000, 4.0, 1.00, "NORMAL"),         # 4% DD - below minor threshold
        (95000, 5.0, 1.00, "MINOR"),          # 5% DD - threshold, no scaling
        (92000, 8.0, 0.90, "MINOR"),          # 8% DD - light scaling
        (88000, 12.0, 0.77, "MODERATE"),      # 12% DD - moderate scaling
        (85000, 15.0, 0.67, "SEVERE"),        # 15% DD - heavy scaling
        (82000, 18.0, 0.57, "SEVERE"),        # 18% DD - severe scaling
    ]
    
    print("\n📊 Position Scaling During Drawdown:")
    print("=" * 70)
    
    for i, (equity, expected_dd, expected_scale, expected_severity) in enumerate(scenarios):
        date = datetime(2025, 1, i + 1)
        metrics = monitor.update(equity, date)
        
        print(f"\n  Day {i+1}: ${equity:,} (-{expected_dd:.1f}%)")
        print(f"    Drawdown: {metrics.drawdown_pct:.2f}%")
        print(f"    Severity: {metrics.severity.value}")
        print(f"    Scale Factor: {metrics.position_scale_factor:.2f}x")
        
        assert abs(metrics.drawdown_pct - expected_dd) < 0.5
        assert metrics.severity.value == expected_severity
        
        # Scale factor should be within reasonable range
        if expected_dd < 5.0:
            assert metrics.position_scale_factor == 1.0
        else:
            assert abs(metrics.position_scale_factor - expected_scale) < 0.15
    
    print("\n✅ Position Scaling PASSED")
    return True


def test_recovery_and_events():
    """Test drawdown recovery detection and event logging"""
    print("\n" + "=" * 70)
    print("TEST 4: Recovery Detection & Event Logging")
    print("=" * 70)
    
    monitor = DrawdownMonitor(
        initial_equity=100000,
        daily_loss_limit_pct=0.50,
        weekly_loss_limit_pct=0.50,
    )
    
    # Simulate a drawdown and recovery cycle
    dates_and_equity = [
        (datetime(2025, 1, 1), 100000),   # Peak
        (datetime(2025, 1, 2), 95000),    # -5% (DD starts)
        (datetime(2025, 1, 3), 90000),    # -10% (trough)
        (datetime(2025, 1, 4), 93000),    # Recovery
        (datetime(2025, 1, 5), 97000),    # More recovery
        (datetime(2025, 1, 6), 102000),   # New peak (recovery complete)
    ]
    
    print("\n📈 Drawdown & Recovery Cycle:")
    for date, equity in dates_and_equity:
        metrics = monitor.update(equity, date)
        status = "PEAK" if equity > monitor.peak_equity else f"DD: {metrics.drawdown_pct:.1f}%"
        print(f"  {date.strftime('%Y-%m-%d')}: ${equity:,} ({status})")
    
    # Check event was recorded
    assert len(monitor.drawdown_events) == 1
    event = monitor.drawdown_events[0]
    
    print(f"\n✓ Drawdown Event Recorded:")
    print(f"  Start: {event.start_date.strftime('%Y-%m-%d')}")
    print(f"  End: {event.end_date.strftime('%Y-%m-%d')}")
    print(f"  Max DD: {event.max_drawdown_pct:.2f}%")
    print(f"  Duration: {event.duration_days} days")
    print(f"  Trough: ${event.trough_equity:,}")
    print(f"  Recovery: ${event.recovery_equity:,}")
    print(f"  Recovered: {event.is_recovered}")
    
    assert event.is_recovered == True
    assert abs(event.max_drawdown_pct - 10.0) < 0.5
    assert event.duration_days == 5
    assert event.trough_equity == 90000
    
    # Test second drawdown cycle
    dates_and_equity_2 = [
        (datetime(2025, 1, 7), 105000),   # New peak
        (datetime(2025, 1, 8), 100000),   # -4.8% (DD starts)
        (datetime(2025, 1, 9), 98000),    # -6.7%
        (datetime(2025, 1, 10), 107000),  # New peak (recovery)
    ]
    
    for date, equity in dates_and_equity_2:
        monitor.update(equity, date)
    
    assert len(monitor.drawdown_events) == 2
    print(f"\n✓ Second drawdown event recorded")
    print(f"  Total events: {len(monitor.drawdown_events)}")
    
    print("\n✅ Recovery Detection & Event Logging PASSED")
    return True


def test_drawdown_summary():
    """Test summary statistics and reporting"""
    print("\n" + "=" * 70)
    print("TEST 5: Drawdown Summary Statistics")
    print("=" * 70)
    
    monitor = DrawdownMonitor(
        initial_equity=100000,
        daily_loss_limit_pct=0.50,
        weekly_loss_limit_pct=0.50,
    )
    
    # Simulate multiple drawdown cycles
    equity_series = [
        100000, 95000, 90000, 95000, 102000,  # DD #1: -10%, 4 days
        102000, 98000, 95000, 100000, 105000,  # DD #2: -6.9%, 4 days
        105000, 100000, 98000, 103000, 108000, # DD #3: -6.7%, 4 days
    ]
    
    for i, equity in enumerate(equity_series):
        date = datetime(2025, 1, 1) + timedelta(days=i)
        monitor.update(equity, date)
    
    summary = monitor.get_drawdown_summary()
    
    print(f"\n📊 Drawdown Summary:")
    print(f"  Current Equity: ${summary['current_equity']:,.0f}")
    print(f"  Peak Equity: ${summary['peak_equity']:,.0f}")
    print(f"  Current DD: {summary['current_drawdown_pct']:.2f}%")
    print(f"  Severity: {summary['current_severity']}")
    print(f"  Position Scale: {summary['position_scale_factor']:.2f}x")
    print(f"  Trading Halted: {summary['is_trading_halted']}")
    
    print(f"\n📈 Historical Statistics:")
    stats = summary['historical_stats']
    print(f"  Total DD Events: {stats['total_drawdown_events']}")
    print(f"  Recovered Events: {stats['recovered_events']}")
    print(f"  Max DD: {stats['max_drawdown_pct']:.2f}%")
    print(f"  Avg DD: {stats['avg_drawdown_pct']:.2f}%")
    print(f"  Avg Recovery Time: {stats['avg_recovery_days']:.1f} days")
    
    assert stats['total_drawdown_events'] == 3
    assert stats['recovered_events'] == 3
    assert stats['max_drawdown_pct'] >= 9.0  # ~10% max
    assert stats['avg_recovery_days'] == 4.0
    
    print("\n✅ Drawdown Summary Statistics PASSED")
    return True


def test_manual_resume():
    """Test manual trading resume after halt"""
    print("\n" + "=" * 70)
    print("TEST 6: Manual Trading Resume")
    print("=" * 70)
    
    monitor = DrawdownMonitor(
        initial_equity=100000,
        max_drawdown_pct=0.20,
    )
    
    # Trigger a halt with 21% drawdown
    date1 = datetime(2025, 1, 1)
    monitor.update(100000, date1)
    
    date2 = datetime(2025, 1, 2)
    metrics1 = monitor.update(79000, date2)  # -21%
    
    print(f"\n✓ Trading halted at 21% drawdown")
    print(f"  Halted: {metrics1.is_trading_halted}")
    print(f"  Reason: {metrics1.halt_reason}")
    assert metrics1.is_trading_halted == True
    
    # Try to resume - should fail (DD still >18%)
    success1 = monitor.resume_trading("Attempted early resume")
    print(f"\n✓ Attempted resume at 21% DD: {success1}")
    assert success1 == False
    assert monitor.is_trading_halted == True
    
    # Partial recovery to 17% drawdown
    date3 = datetime(2025, 1, 3)
    metrics2 = monitor.update(83000, date3)  # -17%
    
    # Try to resume - should succeed (DD <18% = 90% of max)
    success2 = monitor.resume_trading("Risk conditions improved")
    print(f"\n✓ Attempted resume at 17% DD: {success2}")
    assert success2 == True
    assert monitor.is_trading_halted == False
    
    print(f"\n✓ Trading resumed successfully")
    print(f"  Current DD: {metrics2.drawdown_pct:.2f}%")
    print(f"  Position Scale: {monitor.get_position_scale_factor():.2f}x")
    
    print("\n✅ Manual Trading Resume PASSED")
    return True


def run_all_tests():
    """Run all drawdown control validation tests"""
    print("\n" + "=" * 70)
    print("WEEK 3 DAY 3: Drawdown Protection & Monitoring Validation")
    print("=" * 70)
    
    tests = [
        test_basic_drawdown_tracking,
        test_protective_stops,
        test_position_scaling,
        test_recovery_and_events,
        test_drawdown_summary,
        test_manual_resume,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {str(e)}")
            results.append(False)
        except Exception as e:
            print(f"\n❌ TEST ERROR: {str(e)}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 70)
    if all(results):
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\n✅ Drawdown protection system working correctly")
        print("✅ All protective stops validated")
        print("✅ Position scaling functional")
        print("✅ Recovery detection working")
        print("✅ Event logging operational")
        print("✅ Manual resume controls working")
        
        print("\n📊 Drawdown Control Summary:")
        print("  • Real-time drawdown tracking from peak equity")
        print("  • 5 severity levels: NORMAL → MINOR → MODERATE → SEVERE → CRITICAL")
        print("  • Protective stops: Daily (5%), Weekly (10%), Max (20%)")
        print("  • Position scaling: 1.0x → 0.5x during drawdown")
        print("  • Automatic recovery detection and event logging")
        print("  • Manual trading resume with safety checks")
        
        print("\n✅ Ready for Week 3 Day 4: Correlation Analysis")
        return True
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 70)
        failed = sum(1 for r in results if not r)
        print(f"\n{len(results) - failed}/{len(results)} tests passed")
        return False


if __name__ == "__main__":
    run_all_tests()
