from datetime import datetime
from unittest.mock import Mock

from execution.live_dry_run_guard import install_live_dry_run_reconciliation_guard
from execution.order_executor import OrderExecutor, OrderStatus
from risk.risk_manager import RiskManager
from strategies.signal import Signal, SignalStrength, SignalType


def _risk_manager_allows_trade():
    rm = Mock(spec=RiskManager)
    rm.check_trade_risk = Mock(return_value=(True, "Trade approved"))
    rm.emergency_stop_active = False
    return rm


def _buy_signal():
    return Signal(
        timestamp=datetime.now(),
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        target_price=150.0,
        quantity=1,
        confidence=0.9,
        reason="unit-test",
    )


def test_live_dry_run_with_no_adapter_reaches_dry_run_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install_live_dry_run_reconciliation_guard()

    executor = OrderExecutor(
        tws_adapter=None,
        risk_manager=_risk_manager_allows_trade(),
        is_live_mode=True,
        dry_run=True,
        live_trading_enabled=False,
        live_confirmation=None,
        limit_orders_only=True,
    )

    result = executor.execute_signal(
        "dry-run-smoke-test",
        _buy_signal(),
        current_equity=50_000.0,
        positions={},
    )

    assert result.status == OrderStatus.DRY_RUN
    assert executor.orders_dry_run == 1
    audit_files = list((tmp_path / "logs").glob("order_audit_*.log"))
    assert audit_files
    audit_text = audit_files[0].read_text()
    assert "EVENT:SIGNAL_RECEIVED" in audit_text
    assert "EVENT:RISK_CHECK_PASSED" in audit_text
    assert "DRY_RUN" in audit_text


def test_non_dry_run_with_no_adapter_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install_live_dry_run_reconciliation_guard()

    executor = OrderExecutor(
        tws_adapter=None,
        risk_manager=_risk_manager_allows_trade(),
        is_live_mode=False,
        dry_run=False,
        limit_orders_only=True,
    )

    result = executor.execute_signal(
        "no-adapter-live-safety-test",
        _buy_signal(),
        current_equity=50_000.0,
        positions={},
    )

    assert result.status == OrderStatus.REJECTED
    assert "Portfolio state mismatch" in result.reason
