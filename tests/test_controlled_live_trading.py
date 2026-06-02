"""
Tests for the Phase 1 "controlled live trading" safeguards.

Covers:
- Environment/port consistency in :class:`TwsTradingAdapter` /
  :class:`PaperTradingAdapter`.
- Live-mode application switch (`live_trading_enabled`).
- Per-session :class:`LiveTradingConfirmation` gating.
- End-to-end live-mode *dry-run* path: full pipeline runs, audit log is
  written, but no order is submitted to TWS.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from execution.order_executor import (
    LiveTradingConfirmation,
    OrderExecutor,
    OrderStatus,
    RejectionReason,
)
from execution.paper_adapter import PaperTradingAdapter, TwsTradingAdapter
from risk.risk_manager import RiskManager
from strategies.signal import Signal, SignalStrength, SignalType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_adapter():
    adapter = Mock()
    adapter.buy = Mock(return_value=42)
    adapter.sell = Mock(return_value=43)
    adapter.close_position = Mock(return_value=44)
    adapter.get_all_positions = Mock(return_value={})
    adapter.environment = "live"
    adapter.port = 7496
    return adapter


@pytest.fixture
def risk_manager():
    rm = Mock(spec=RiskManager)
    rm.check_trade_risk = Mock(return_value=(True, ""))
    rm.emergency_stop_active = False
    return rm


@pytest.fixture
def buy_signal():
    return Signal(
        timestamp=datetime.now(),
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        target_price=150.0,
        quantity=10,
        confidence=0.9,
        reason="unit-test",
    )


def _make_confirmation(**overrides) -> LiveTradingConfirmation:
    defaults = dict(
        environment="live",
        account_id="U1234567",
        port=7496,
        confirmed_by="op-tester",
    )
    defaults.update(overrides)
    return LiveTradingConfirmation(**defaults)


# ---------------------------------------------------------------------------
# TwsTradingAdapter env/port consistency
# ---------------------------------------------------------------------------


def test_paper_adapter_rejects_live_port():
    with pytest.raises(ValueError, match="paper"):
        PaperTradingAdapter(port=7496)


def test_tws_adapter_rejects_live_env_on_paper_port():
    with pytest.raises(ValueError, match="LIVE adapter on paper port"):
        TwsTradingAdapter(port=7497, environment="live")


def test_tws_adapter_rejects_paper_env_on_live_port():
    with pytest.raises(ValueError, match="PAPER adapter on live port"):
        TwsTradingAdapter(port=7496, environment="paper")


def test_tws_adapter_allows_matched_live_combo():
    adapter = TwsTradingAdapter(port=7496, environment="live")
    assert adapter.environment == "live"
    assert adapter.port == 7496


def test_tws_adapter_rejects_unknown_environment():
    with pytest.raises(ValueError, match="Invalid environment"):
        TwsTradingAdapter(port=7497, environment="prod")


def test_paper_adapter_alias_refuses_live_environment():
    with pytest.raises(ValueError, match="paper-only"):
        PaperTradingAdapter(environment="live")


# ---------------------------------------------------------------------------
# Live-mode application switch
# ---------------------------------------------------------------------------


def test_live_mode_blocks_when_app_switch_off(mock_adapter, risk_manager, buy_signal):
    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,
        live_trading_enabled=False,  # switch OFF
        live_confirmation=_make_confirmation(),
    )
    result = executor.execute_signal("s", buy_signal, 100_000.0, {})
    assert result.status == OrderStatus.REJECTED
    assert RejectionReason.LIVE_TRADING_DISABLED.value in result.reason
    mock_adapter.buy.assert_not_called()


def test_live_mode_blocks_without_confirmation(mock_adapter, risk_manager, buy_signal):
    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,
        live_trading_enabled=True,
        live_confirmation=None,  # missing per-session token
    )
    result = executor.execute_signal("s", buy_signal, 100_000.0, {})
    assert result.status == OrderStatus.REJECTED
    assert RejectionReason.LIVE_CONFIRMATION_MISSING.value in result.reason
    mock_adapter.buy.assert_not_called()


def test_live_mode_blocks_on_env_mismatch(mock_adapter, risk_manager, buy_signal):
    # Confirmation says port 7496 (live) but adapter reports paper port.
    mock_adapter.environment = "paper"
    mock_adapter.port = 7497
    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,
        live_trading_enabled=True,
        live_confirmation=_make_confirmation(),
    )
    result = executor.execute_signal("s", buy_signal, 100_000.0, {})
    assert result.status == OrderStatus.REJECTED
    assert RejectionReason.LIVE_ENV_MISMATCH.value in result.reason
    mock_adapter.buy.assert_not_called()


def test_live_mode_blocks_on_account_mismatch(mock_adapter, risk_manager, buy_signal):
    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,
        live_trading_enabled=True,
        live_confirmation=_make_confirmation(account_id="U9999999"),
        expected_account_id="U1234567",
    )
    result = executor.execute_signal("s", buy_signal, 100_000.0, {})
    assert result.status == OrderStatus.REJECTED
    assert RejectionReason.LIVE_ENV_MISMATCH.value in result.reason


def test_live_mode_passes_when_all_safeguards_satisfied(
    mock_adapter, risk_manager, buy_signal
):
    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,  # skip interactive prompt for this test
        live_trading_enabled=True,
        live_confirmation=_make_confirmation(),
        expected_account_id="U1234567",
    )
    result = executor.execute_signal("s", buy_signal, 100_000.0, {})
    assert result.status == OrderStatus.SUBMITTED
    mock_adapter.buy.assert_called_once_with(
        symbol="AAPL", quantity=10, order_type="MARKET"
    )


# ---------------------------------------------------------------------------
# Dry-run mode (end-to-end live rehearsal without real orders)
# ---------------------------------------------------------------------------


def test_dry_run_live_mode_does_not_submit(
    mock_adapter, risk_manager, buy_signal, tmp_path, monkeypatch
):
    # Run the audit log inside the tmp dir so we don't touch the repo.
    monkeypatch.chdir(tmp_path)

    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,
        dry_run=True,
        # Dry-run intentionally requires NO live confirmation: it's the safe
        # rehearsal path and must always work without flipping the live
        # switch ON.
        live_trading_enabled=False,
        live_confirmation=None,
    )
    result = executor.execute_signal("dry-strategy", buy_signal, 100_000.0, {})

    assert result.status == OrderStatus.DRY_RUN
    mock_adapter.buy.assert_not_called()
    mock_adapter.sell.assert_not_called()

    stats = executor.get_statistics()
    assert stats["dry_run"] == 1
    assert stats["submitted"] == 0

    # Audit log must contain at least one SIGNAL_RECEIVED event and the
    # DRY_RUN outcome.
    audit_files = list((tmp_path / "logs").glob("order_audit_*.log"))
    assert audit_files, "audit log file was not written"
    audit_text = audit_files[0].read_text()
    assert "EVENT:SIGNAL_RECEIVED" in audit_text
    assert "DRY_RUN" in audit_text


def test_dry_run_still_blocks_on_emergency_stop(
    mock_adapter, risk_manager, buy_signal, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    stop_file = tmp_path / "EMERGENCY_STOP"
    stop_file.write_text("halt")

    executor = OrderExecutor(
        tws_adapter=mock_adapter,
        risk_manager=risk_manager,
        is_live_mode=True,
        require_confirmation=False,
        dry_run=True,
        emergency_stop_file=str(stop_file),
    )
    result = executor.execute_signal("dry-strategy", buy_signal, 100_000.0, {})
    # Emergency stop overrides dry-run: must surface as REJECTED, not DRY_RUN.
    assert result.status == OrderStatus.REJECTED
    assert "Emergency stop" in result.reason
