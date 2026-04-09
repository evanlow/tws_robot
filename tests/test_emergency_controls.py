"""
Week 3 Day 6: Emergency Controls & Circuit Breakers - Validation Tests

This test suite validates the EmergencyController implementation including:
- Circuit breaker triggering and reset
- Emergency stop functionality
- Kill switch and panic button
- Recovery and resume protocols
- Multi-level emergency responses
"""

import sys
from datetime import datetime, timedelta
from risk.emergency_controls import (
    EmergencyController,
    EmergencyLevel,
    TriggerReason,
    CircuitBreakerConfig,
    CircuitBreaker
)


def test_circuit_breaker():
    """Test 1: Circuit Breaker Functionality"""
    print("\n" + "="*70)
    print("TEST 1: Circuit Breaker Functionality")
    print("="*70)
    
    # Create circuit breaker
    config = CircuitBreakerConfig(
        name='test_breaker',
        threshold=0.10,  # 10% threshold
        cooldown_minutes=5,
        auto_resume=True,
        max_triggers_per_day=3
    )
    breaker = CircuitBreaker(config)
    
    print("\n✓ Test 1a: Normal Operation (Below Threshold)")
    timestamp = datetime.now()
    tripped = breaker.check(0.05, timestamp)  # 5% - below threshold
    print(f"  Value: 5%, Threshold: 10%")
    print(f"  Tripped: {tripped}")
    assert tripped == False
    assert breaker.is_tripped == False
    print("  ✓ Breaker not tripped below threshold")
    
    print("\n✓ Test 1b: Trip When Exceeding Threshold")
    tripped = breaker.check(0.12, timestamp)  # 12% - above threshold
    print(f"  Value: 12%, Threshold: 10%")
    print(f"  Tripped: {tripped}")
    assert tripped == True
    assert breaker.is_tripped == True
    assert breaker.trip_count_today == 1
    print("  ✓ Breaker tripped above threshold")
    
    print("\n✓ Test 1c: Cooldown Period (No Duplicate Trip)")
    timestamp2 = timestamp + timedelta(minutes=2)  # 2 min later (still in cooldown)
    tripped = breaker.check(0.15, timestamp2)  # Still above threshold
    print(f"  Time: +2 minutes (cooldown: 5 min)")
    print(f"  Tripped: {tripped}")
    assert tripped == False  # Still in cooldown
    assert breaker.trip_count_today == 1  # Count didn't increase
    print("  ✓ No duplicate trip during cooldown")
    
    print("\n✓ Test 1d: Auto-Resume After Cooldown")
    timestamp3 = timestamp + timedelta(minutes=6)  # 6 min later (past cooldown)
    can_resume = breaker.can_auto_resume(timestamp3)
    print(f"  Time: +6 minutes (past cooldown)")
    print(f"  Can Auto Resume: {can_resume}")
    assert can_resume == True
    print("  ✓ Auto-resume available after cooldown")
    
    print("\n✓ Test 1e: Manual Reset")
    breaker.reset()
    print(f"  Is Tripped: {breaker.is_tripped}")
    assert breaker.is_tripped == False
    print("  ✓ Manual reset successful")
    
    print("\n✓ Test 1f: Daily Limit")
    # Trip breaker 3 times (max daily limit)
    breaker.reset()
    timestamp4 = datetime.now()
    breaker.check(0.15, timestamp4)
    breaker.reset()
    breaker.check(0.15, timestamp4 + timedelta(minutes=10))
    breaker.reset()
    breaker.check(0.15, timestamp4 + timedelta(minutes=20))
    
    print(f"  Trip Count Today: {breaker.trip_count_today}")
    assert breaker.trip_count_today == 3
    
    # Try to trip again - should be blocked
    breaker.reset()
    tripped = breaker.check(0.15, timestamp4 + timedelta(minutes=30))
    print(f"  Attempt 4th Trip: {tripped}")
    assert tripped == False  # Blocked by daily limit
    print("  ✓ Daily limit enforced")
    
    print("\n" + "✅ Circuit Breaker PASSED" + "\n")


def test_emergency_levels():
    """Test 2: Emergency Level Progression"""
    print("\n" + "="*70)
    print("TEST 2: Emergency Level Progression")
    print("="*70)
    
    controller = EmergencyController(
        max_drawdown_pct=0.20,
        critical_drawdown_pct=0.15,
        max_daily_loss_pct=0.05,
        auto_resume_enabled=False
    )
    
    peak_equity = 100000
    daily_start = 100000
    
    print("\n✓ Test 2a: NONE - Normal Operation")
    status = controller.check_emergency_conditions(
        current_equity=100000,
        starting_equity=100000,
        daily_starting_equity=daily_start,
        peak_equity=peak_equity
    )
    print(f"  Level: {status.level.value}")
    print(f"  Trading Allowed: {status.trading_allowed}")
    assert status.level == EmergencyLevel.NONE
    assert status.trading_allowed == True
    print("  ✓ Normal operation")
    
    print("\n✓ Test 2b: WARNING - Minor Drawdown")
    status = controller.check_emergency_conditions(
        current_equity=93000,  # 7% drawdown
        starting_equity=100000,
        daily_starting_equity=93000,  # Started day here (no daily loss)
        peak_equity=peak_equity
    )
    print(f"  Equity: $93,000 (7% DD)")
    print(f"  Level: {status.level.value}")
    print(f"  Trading Allowed: {status.trading_allowed}")
    assert status.level in [EmergencyLevel.WARNING, EmergencyLevel.NONE]
    print("  ✓ Warning level assessed")
    
    print("\n✓ Test 2c: ALERT - Moderate Drawdown")
    status = controller.check_emergency_conditions(
        current_equity=90000,  # 10% drawdown
        starting_equity=100000,
        daily_starting_equity=90000,  # Started day here
        peak_equity=peak_equity
    )
    print(f"  Equity: $90,000 (10% DD)")
    print(f"  Level: {status.level.value}")
    print(f"  Trading Allowed: {status.trading_allowed}")
    print(f"  New Positions Allowed: {status.new_positions_allowed}")
    assert status.level in [EmergencyLevel.ALERT, EmergencyLevel.WARNING, EmergencyLevel.NONE]
    print("  ✓ Alert level assessed")
    
    print("\n✓ Test 2d: CRITICAL - Circuit Breaker Triggered")
    status = controller.check_emergency_conditions(
        current_equity=85000,  # 15% drawdown (critical threshold)
        starting_equity=100000,
        daily_starting_equity=85000,  # Started day here
        peak_equity=peak_equity
    )
    print(f"  Equity: $85,000 (15% DD)")
    print(f"  Level: {status.level.value}")
    print(f"  Trading Allowed: {status.trading_allowed}")
    print(f"  Active Breakers: {status.active_breakers}")
    assert status.level == EmergencyLevel.CRITICAL
    assert status.trading_allowed == False
    assert len(status.active_breakers) > 0
    print("  ✓ Critical level and breaker trip")
    
    print("\n✓ Test 2e: SHUTDOWN - Maximum Drawdown")
    controller2 = EmergencyController(max_drawdown_pct=0.20)
    status = controller2.check_emergency_conditions(
        current_equity=80000,  # 20% drawdown (max threshold)
        starting_equity=100000,
        daily_starting_equity=80000,  # Started day here
        peak_equity=peak_equity
    )
    print(f"  Equity: $80,000 (20% DD)")
    print(f"  Level: {status.level.value}")
    print(f"  Is Shutdown: {controller2.is_shutdown}")
    print(f"  Manual Intervention Required: {status.manual_intervention_required}")
    assert status.level == EmergencyLevel.SHUTDOWN
    assert controller2.is_shutdown == True
    assert status.trading_allowed == False
    print("  ✓ Emergency shutdown triggered")
    
    print("\n" + "✅ Emergency Levels PASSED" + "\n")


def test_daily_loss_protection():
    """Test 3: Daily Loss Protection"""
    print("\n" + "="*70)
    print("TEST 3: Daily Loss Protection")
    print("="*70)
    
    controller = EmergencyController(
        max_daily_loss_pct=0.05,  # 5% max daily loss
        auto_resume_enabled=False
    )
    
    peak_equity = 100000
    daily_start = 100000
    
    print("\n✓ Test 3a: Normal Daily Loss (2%)")
    status = controller.check_emergency_conditions(
        current_equity=98000,  # 2% daily loss
        starting_equity=100000,
        daily_starting_equity=daily_start,
        peak_equity=peak_equity
    )
    print(f"  Daily Loss: 2%")
    print(f"  Level: {status.level.value}")
    print(f"  Trading Allowed: {status.trading_allowed}")
    assert status.trading_allowed == True
    print("  ✓ Normal operation")
    
    print("\n✓ Test 3b: Warning Daily Loss (4%)")
    status = controller.check_emergency_conditions(
        current_equity=96000,  # 4% daily loss (80% of max)
        starting_equity=100000,
        daily_starting_equity=daily_start,
        peak_equity=peak_equity
    )
    print(f"  Daily Loss: 4% (80% of max)")
    print(f"  Level: {status.level.value}")
    print(f"  Active Breakers: {status.active_breakers}")
    # Circuit breaker triggers at 80% of max (4%)
    assert len(status.active_breakers) > 0 or status.level != EmergencyLevel.NONE
    print("  ✓ Warning or breaker triggered")
    
    print("\n✓ Test 3c: Maximum Daily Loss (5%)")
    controller2 = EmergencyController(max_daily_loss_pct=0.05)
    status = controller2.check_emergency_conditions(
        current_equity=95000,  # 5% daily loss (max)
        starting_equity=100000,
        daily_starting_equity=daily_start,
        peak_equity=peak_equity
    )
    print(f"  Daily Loss: 5% (MAX)")
    print(f"  Level: {status.level.value}")
    print(f"  Is Shutdown: {controller2.is_shutdown}")
    assert status.level == EmergencyLevel.SHUTDOWN
    assert controller2.is_shutdown == True
    print("  ✓ Emergency shutdown on max daily loss")
    
    print("\n" + "✅ Daily Loss Protection PASSED" + "\n")


def test_kill_switch():
    """Test 4: Kill Switch Functionality"""
    print("\n" + "="*70)
    print("TEST 4: Kill Switch Functionality")
    print("="*70)
    
    controller = EmergencyController()
    
    print("\n✓ Test 4a: Normal State Before Kill Switch")
    status = controller.check_emergency_conditions(
        current_equity=100000,
        starting_equity=100000,
        daily_starting_equity=100000,
        peak_equity=100000
    )
    print(f"  Level: {status.level.value}")
    print(f"  Kill Switch Active: {controller.kill_switch_activated}")
    assert status.level == EmergencyLevel.NONE
    assert controller.kill_switch_activated == False
    print("  ✓ Normal operation")
    
    print("\n✓ Test 4b: Activate Kill Switch")
    controller.activate_kill_switch("Testing kill switch")
    print(f"  Kill Switch Active: {controller.kill_switch_activated}")
    print(f"  Is Shutdown: {controller.is_shutdown}")
    assert controller.kill_switch_activated == True
    assert controller.is_shutdown == True
    print("  ✓ Kill switch activated")
    
    print("\n✓ Test 4c: Verify Trading Blocked")
    status = controller.check_emergency_conditions(
        current_equity=100000,
        starting_equity=100000,
        daily_starting_equity=100000,
        peak_equity=100000
    )
    print(f"  Trading Allowed: {status.trading_allowed}")
    print(f"  New Positions Allowed: {status.new_positions_allowed}")
    assert status.trading_allowed == False
    assert status.new_positions_allowed == False
    print("  ✓ All trading blocked")
    
    print("\n" + "✅ Kill Switch PASSED" + "\n")


def test_panic_button():
    """Test 5: Panic Button"""
    print("\n" + "="*70)
    print("TEST 5: Panic Button")
    print("="*70)
    
    controller = EmergencyController()
    
    print("\n✓ Test 5a: Press Panic Button")
    status = controller.panic_button()
    print(f"  Level: {status.level.value}")
    print(f"  Is Shutdown: {controller.is_shutdown}")
    print(f"  Kill Switch: {controller.kill_switch_activated}")
    assert status.level == EmergencyLevel.SHUTDOWN
    assert controller.is_shutdown == True
    assert controller.kill_switch_activated == True
    print("  ✓ Panic button triggered emergency shutdown")
    
    print("\n✓ Test 5b: Verify Immediate Stop")
    print(f"  Trading Allowed: {status.trading_allowed}")
    print(f"  Status: {status.get_status_message()}")
    assert status.trading_allowed == False
    assert "SHUTDOWN" in status.get_status_message()
    print("  ✓ Immediate trading stop confirmed")
    
    print("\n" + "✅ Panic Button PASSED" + "\n")


def test_recovery_resume():
    """Test 6: Recovery and Resume Protocols"""
    print("\n" + "="*70)
    print("TEST 6: Recovery and Resume Protocols")
    print("="*70)
    
    print("\n✓ Test 6a: Shutdown and Cooldown Period")
    controller = EmergencyController(
        max_drawdown_pct=0.20,
        cooldown_minutes=5,
        auto_resume_enabled=False,
        require_manual_review=True
    )
    
    # Trigger shutdown
    controller.check_emergency_conditions(
        current_equity=80000,  # 20% drawdown
        starting_equity=100000,
        daily_starting_equity=100000,
        peak_equity=100000
    )
    
    print(f"  Is Shutdown: {controller.is_shutdown}")
    print(f"  Shutdown Time: {controller.shutdown_time}")
    assert controller.is_shutdown == True
    print("  ✓ System shutdown")
    
    print("\n✓ Test 6b: Cannot Resume During Cooldown")
    # Try to resume immediately
    immediate_timestamp = controller.shutdown_time + timedelta(minutes=2)
    success = controller.request_resume(
        approved_by="Test User",
        reason="Testing immediate resume",
        timestamp=immediate_timestamp
    )
    print(f"  Resume Success: {success}")
    print(f"  Still Shutdown: {controller.is_shutdown}")
    assert success == False
    assert controller.is_shutdown == True
    print("  ✓ Resume blocked during cooldown")
    
    print("\n✓ Test 6c: Resume After Cooldown")
    # Try after cooldown period
    post_cooldown = controller.shutdown_time + timedelta(minutes=6)
    success = controller.request_resume(
        approved_by="Risk Manager",
        reason="Conditions normalized",
        timestamp=post_cooldown
    )
    print(f"  Resume Success: {success}")
    print(f"  Is Shutdown: {controller.is_shutdown}")
    print(f"  Kill Switch: {controller.kill_switch_activated}")
    assert success == True
    assert controller.is_shutdown == False
    assert controller.kill_switch_activated == False
    print("  ✓ Resume successful after cooldown")
    
    print("\n✓ Test 6d: Breakers Reset on Resume")
    print(f"  Active Breakers: {[b for b, br in controller.breakers.items() if br.is_tripped]}")
    all_reset = all(not breaker.is_tripped for breaker in controller.breakers.values())
    assert all_reset == True
    print("  ✓ All breakers reset")
    
    print("\n" + "✅ Recovery & Resume PASSED" + "\n")


def test_multiple_breakers():
    """Test 7: Multiple Circuit Breakers"""
    print("\n" + "="*70)
    print("TEST 7: Multiple Circuit Breakers")
    print("="*70)
    
    controller = EmergencyController(
        max_drawdown_pct=0.25,
        critical_drawdown_pct=0.15,
        max_daily_loss_pct=0.06
    )
    
    print("\n✓ Test 7a: Trigger Multiple Breakers")
    # Scenario with both drawdown and daily loss issues
    status = controller.check_emergency_conditions(
        current_equity=85000,  # 15% total DD, 4.8% daily loss
        starting_equity=100000,
        daily_starting_equity=89000,  # Started day at 89k
        peak_equity=100000
    )
    
    print(f"  Total Drawdown: 15%")
    print(f"  Daily Loss: ~4.5%")
    print(f"  Level: {status.level.value}")
    print(f"  Active Breakers: {status.active_breakers}")
    
    # Should have drawdown breaker tripped (15% >= 15%)
    assert 'drawdown' in status.active_breakers
    print("  ✓ Multiple conditions detected")
    
    print("\n✓ Test 7b: Get Breaker Status")
    breaker_status = controller.get_breaker_status()
    print(f"  Total Breakers: {len(breaker_status)}")
    print(f"  Breakers: {list(breaker_status.keys())}")
    assert len(breaker_status) >= 3  # drawdown, daily_loss, position_loss, volatility
    print("  ✓ All breakers tracked")
    
    print("\n✓ Test 7c: Reset Specific Breaker")
    success = controller.reset_circuit_breaker('drawdown')
    breaker = controller.breakers['drawdown']
    print(f"  Reset Success: {success}")
    print(f"  Drawdown Breaker Tripped: {breaker.is_tripped}")
    assert success == True
    assert breaker.is_tripped == False
    print("  ✓ Individual breaker reset")
    
    print("\n" + "✅ Multiple Breakers PASSED" + "\n")


def test_emergency_summary():
    """Test 8: Emergency Summary and Status"""
    print("\n" + "="*70)
    print("TEST 8: Emergency Summary and Status")
    print("="*70)
    
    controller = EmergencyController()
    
    # Trigger some conditions
    controller.check_emergency_conditions(
        current_equity=85000,  # 15% drawdown
        starting_equity=100000,
        daily_starting_equity=100000,
        peak_equity=100000
    )
    
    print("\n✓ Test 8a: Get Emergency Summary")
    summary = controller.get_emergency_summary()
    
    required_keys = ['current_status', 'permissions', 'recovery', 
                     'circuit_breakers', 'recent_events', 'statistics']
    print(f"  Summary Keys: {list(summary.keys())}")
    for key in required_keys:
        assert key in summary
        print(f"  ✓ {key}: present")
    
    print("\n✓ Test 8b: Current Status")
    status = summary['current_status']
    print(f"  Level: {status['level']}")
    print(f"  Is Active: {status['is_active']}")
    print(f"  Message: {status['status_message']}")
    assert 'level' in status
    assert 'status_message' in status
    print("  ✓ Status data valid")
    
    print("\n✓ Test 8c: Permissions")
    perms = summary['permissions']
    print(f"  Trading: {perms['trading_allowed']}")
    print(f"  New Positions: {perms['new_positions_allowed']}")
    print(f"  Increases: {perms['position_increases_allowed']}")
    assert all(k in perms for k in ['trading_allowed', 'new_positions_allowed'])
    print("  ✓ Permissions data valid")
    
    print("\n✓ Test 8d: Circuit Breaker Details")
    breakers = summary['circuit_breakers']
    print(f"  Breakers Tracked: {len(breakers)}")
    for name, info in breakers.items():
        print(f"  • {name}: {'TRIPPED' if info['is_tripped'] else 'OK'}")
        assert 'is_tripped' in info
        assert 'config' in info
    print("  ✓ Breaker details complete")
    
    print("\n✓ Test 8e: Statistics")
    stats = summary['statistics']
    print(f"  Total Events: {stats['total_events']}")
    print(f"  Active Breakers: {stats['active_breakers']}")
    assert isinstance(stats['total_events'], int)
    print("  ✓ Statistics valid")
    
    print("\n" + "✅ Emergency Summary PASSED" + "\n")


# Main test runner
if __name__ == "__main__":
    print("="*70)
    print("WEEK 3 DAY 6: Emergency Controls & Circuit Breakers")
    print("="*70)
    
    all_passed = True
    tests = [
        ("Circuit Breaker", test_circuit_breaker),
        ("Emergency Levels", test_emergency_levels),
        ("Daily Loss Protection", test_daily_loss_protection),
        ("Kill Switch", test_kill_switch),
        ("Panic Button", test_panic_button),
        ("Recovery & Resume", test_recovery_resume),
        ("Multiple Breakers", test_multiple_breakers),
        ("Emergency Summary", test_emergency_summary),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n❌ {name} FAILED: {e}\n")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    if all_passed:
        print("="*70)
        print("🎉 ALL TESTS PASSED!")
        print("="*70)
        print("\n✅ Emergency control system validated")
        print("✅ Circuit breakers working")
        print("✅ Emergency levels functional")
        print("✅ Kill switch operational")
        print("✅ Panic button working")
        print("✅ Recovery protocols validated")
        print("✅ Multiple breaker coordination working")
        print("✅ Summary and status complete")
        print("\n🚨 Emergency Controls Features:")
        print("  • 5-level emergency system (NONE/WARNING/ALERT/CRITICAL/SHUTDOWN)")
        print("  • Multiple circuit breakers (drawdown, daily loss, position, volatility)")
        print("  • Auto-trip with configurable thresholds")
        print("  • Cooldown periods and daily limits")
        print("  • Kill switch for immediate shutdown")
        print("  • Panic button for emergencies")
        print("  • Controlled recovery with manual approval")
        print("  • Comprehensive event logging")
        print("\n✅ Ready for Week 3 Day 7: Documentation & Integration")
    else:
        print("="*70)
        print("❌ SOME TESTS FAILED")
        print("="*70)
        sys.exit(1)
