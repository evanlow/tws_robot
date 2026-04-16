"""Tests for strategy-aware drawdown: stock-only drawdown and premium retention.

Validates that:
- Stock drawdown excludes short option mark-to-market
- Premium retention tracks collected vs current liability
- Risk limits trigger on stock drawdown, not total portfolio drawdown
- ServiceManager.recompute_strategy_metrics correctly separates position types
- API returns the new fields
"""

import json
import threading
from datetime import datetime
from unittest.mock import Mock

import pytest

from risk.risk_manager import RiskManager, Position, RiskMetrics, RiskStatus


# ==============================================================================
# RiskManager — stock-only drawdown
# ==============================================================================


class TestStockOnlyDrawdown:
    """Test that drawdown calculations exclude short options."""

    def test_stock_equity_follows_total_equity_without_positions(self):
        """Without position-level data, stock_equity mirrors total equity."""
        rm = RiskManager(initial_capital=100000)
        metrics = rm.update(95000, {}, datetime.now())

        assert rm.stock_equity == 95000
        assert rm.peak_stock_equity == 100000
        assert metrics.stock_drawdown_pct == pytest.approx(0.05)

    def test_stock_equity_tracks_peak(self):
        """Peak stock equity is updated when stock equity rises."""
        rm = RiskManager(initial_capital=100000)
        rm.update(110000, {}, datetime.now())
        assert rm.peak_stock_equity == 110000

        rm.update(105000, {}, datetime.now())
        assert rm.peak_stock_equity == 110000  # unchanged

    def test_stock_drawdown_triggers_emergency_stop(self):
        """Emergency stop triggers on stock drawdown exceeding limit."""
        rm = RiskManager(initial_capital=100000, max_drawdown_pct=0.15,
                         emergency_stop_enabled=True)
        now = datetime.now()

        rm.update(110000, {}, now)
        assert not rm.emergency_stop_active

        # 15.5% stock drawdown
        rm.update(93000, {}, now)
        assert rm.emergency_stop_active
        assert rm.drawdown_breached

    def test_stock_drawdown_with_separate_stock_equity(self):
        """When stock equity is set independently, it drives risk limits."""
        rm = RiskManager(initial_capital=100000, max_drawdown_pct=0.20,
                         emergency_stop_enabled=True)
        now = datetime.now()

        # Set stock equity via the flag (simulating recompute_strategy_metrics)
        rm._stock_equity_from_positions = True
        rm.stock_equity = 80000
        rm.peak_stock_equity = 100000

        # Total equity is higher (includes short option premium)
        metrics = rm.update(95000, {}, now)

        # Total drawdown is ~5%, but stock drawdown is 20%
        assert metrics.drawdown_pct == pytest.approx(0.05)
        assert metrics.stock_drawdown_pct == pytest.approx(0.20)
        assert rm.emergency_stop_active  # triggered by stock drawdown

    def test_total_drawdown_alone_does_not_trigger_stop(self):
        """If only total equity drops but stock equity is fine, no emergency."""
        rm = RiskManager(initial_capital=100000, max_drawdown_pct=0.15,
                         emergency_stop_enabled=True)
        now = datetime.now()

        rm._stock_equity_from_positions = True
        rm.stock_equity = 98000
        rm.peak_stock_equity = 100000

        # Total equity drops 16% from peak but stock is only 2% down
        rm.current_equity = 100000
        rm.peak_equity = 100000
        metrics = rm.update(84000, {}, now)

        assert metrics.drawdown_pct == pytest.approx(0.16)
        assert metrics.stock_drawdown_pct == pytest.approx(0.02)
        assert not rm.emergency_stop_active  # stock drawdown is fine


# ==============================================================================
# RiskManager — premium retention
# ==============================================================================


class TestPremiumRetention:
    """Test short options premium retention calculation."""

    def test_no_short_options_means_full_retention(self):
        """Without short options, premium retention is 100%."""
        rm = RiskManager(initial_capital=100000)
        metrics = rm.update(100000, {}, datetime.now())
        assert metrics.premium_retention_pct == 1.0

    def test_premium_retention_calculation(self):
        """Premium retention = (collected - liability) / collected."""
        rm = RiskManager(initial_capital=100000)
        rm.short_options_premium_collected = 1000.0
        rm.short_options_current_liability = 200.0

        metrics = rm.update(100000, {}, datetime.now())
        # (1000 - 200) / 1000 = 0.80
        assert metrics.premium_retention_pct == pytest.approx(0.80)

    def test_premium_retention_near_zero(self):
        """When liability equals premium, retention is 0%."""
        rm = RiskManager(initial_capital=100000)
        rm.short_options_premium_collected = 500.0
        rm.short_options_current_liability = 500.0

        metrics = rm.update(100000, {}, datetime.now())
        assert metrics.premium_retention_pct == pytest.approx(0.0)

    def test_premium_retention_floor_at_zero(self):
        """Retention doesn't go negative if liability exceeds premium."""
        rm = RiskManager(initial_capital=100000)
        rm.short_options_premium_collected = 500.0
        rm.short_options_current_liability = 800.0

        metrics = rm.update(100000, {}, datetime.now())
        assert metrics.premium_retention_pct == 0.0

    def test_premium_in_risk_summary(self):
        """get_risk_summary includes premium retention fields."""
        rm = RiskManager(initial_capital=100000)
        rm.short_options_premium_collected = 1000.0
        rm.short_options_current_liability = 50.0

        summary = rm.get_risk_summary()
        assert summary["premium_retention_pct"] == pytest.approx(0.95)
        assert summary["short_options_premium_collected"] == 1000.0
        assert summary["short_options_current_liability"] == 50.0


# ==============================================================================
# RiskManager — risk summary new fields
# ==============================================================================


class TestRiskSummaryNewFields:
    """Test that get_risk_summary includes strategy-aware fields."""

    def test_summary_has_stock_drawdown(self):
        rm = RiskManager(initial_capital=100000)
        rm.update(90000, {}, datetime.now())
        summary = rm.get_risk_summary()

        assert "stock_drawdown_pct" in summary
        assert "stock_equity" in summary
        assert "peak_stock_equity" in summary
        assert summary["stock_drawdown_pct"] == pytest.approx(0.10)

    def test_reset_clears_strategy_fields(self):
        rm = RiskManager(initial_capital=100000)
        rm.stock_equity = 50000
        rm.peak_stock_equity = 80000
        rm._stock_equity_from_positions = True
        rm.short_options_premium_collected = 999.0
        rm.short_options_current_liability = 100.0

        rm.reset()

        assert rm.stock_equity == 100000
        assert rm.peak_stock_equity == 100000
        assert rm._stock_equity_from_positions is False
        assert rm.short_options_premium_collected == 0.0
        assert rm.short_options_current_liability == 0.0


# ==============================================================================
# RiskManager — risk status uses stock drawdown
# ==============================================================================


class TestRiskStatusUsesStockDrawdown:
    """Risk status thresholds should check stock drawdown, not total."""

    def test_warning_from_stock_drawdown(self):
        rm = RiskManager(initial_capital=100000, max_drawdown_pct=0.20)
        now = datetime.now()

        rm._stock_equity_from_positions = True
        rm.stock_equity = 83000   # 17% stock drawdown → >80% of 20% limit
        rm.peak_stock_equity = 100000

        metrics = rm.update(99000, {}, now)  # total equity fine
        assert rm.risk_status == RiskStatus.WARNING

    def test_critical_from_stock_drawdown(self):
        rm = RiskManager(initial_capital=100000, max_drawdown_pct=0.20)
        now = datetime.now()

        rm._stock_equity_from_positions = True
        rm.stock_equity = 81000   # 19% stock drawdown → 95% of 20% limit
        rm.peak_stock_equity = 100000

        metrics = rm.update(99000, {}, now)
        assert rm.risk_status == RiskStatus.CRITICAL

    def test_normal_when_only_total_drawdown_high(self):
        rm = RiskManager(initial_capital=100000, max_drawdown_pct=0.20)
        now = datetime.now()

        rm._stock_equity_from_positions = True
        rm.stock_equity = 98000   # 2% stock drawdown
        rm.peak_stock_equity = 100000

        rm.current_equity = 100000
        rm.peak_equity = 100000
        metrics = rm.update(82000, {}, now)  # 18% total drawdown
        assert rm.risk_status == RiskStatus.NORMAL


# ==============================================================================
# ServiceManager.recompute_strategy_metrics
# ==============================================================================


class TestRecomputeStrategyMetrics:
    """Test ServiceManager.recompute_strategy_metrics position classification."""

    @pytest.fixture
    def app(self):
        from web import create_app
        return create_app({"TESTING": True})

    @pytest.fixture
    def svc(self, app):
        return app.config["services"]

    def test_long_stock_counted_in_stock_equity(self, svc):
        svc.update_account_summary({"cash_balance": 50000.0})
        svc.update_position("GOOG", {
            "quantity": 10, "market_value": 15000.0,
            "side": "LONG", "sec_type": "STK",
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager
        assert rm.stock_equity == 65000.0  # 50k cash + 15k stock

    def test_short_option_excluded_from_stock_equity(self, svc):
        svc.update_account_summary({"cash_balance": 50000.0})
        svc.update_position("GOOG", {
            "quantity": 10, "market_value": 15000.0,
            "side": "LONG", "sec_type": "STK",
        })
        svc.update_position("GOOG 250418P150", {
            "quantity": -1, "market_value": -200.0,
            "side": "SHORT", "sec_type": "OPT",
            "premium_collected": 500.0, "current_liability": 200.0,
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager

        # Stock equity = cash + long stock only
        assert rm.stock_equity == 65000.0
        assert rm._stock_equity_from_positions is True
        # Premium tracking
        assert rm.short_options_premium_collected == 500.0
        assert rm.short_options_current_liability == 200.0

    def test_multiple_short_options_aggregated(self, svc):
        svc.update_account_summary({"cash_balance": 30000.0})
        svc.update_position("OPT1", {
            "side": "SHORT", "sec_type": "OPT",
            "market_value": -100.0,
            "premium_collected": 300.0, "current_liability": 100.0,
        })
        svc.update_position("OPT2", {
            "side": "SHORT", "sec_type": "OPT",
            "market_value": -50.0,
            "premium_collected": 200.0, "current_liability": 50.0,
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager

        assert rm.stock_equity == 30000.0  # only cash, no long positions
        assert rm.short_options_premium_collected == 500.0
        assert rm.short_options_current_liability == 150.0

    def test_peak_stock_equity_tracked(self, svc):
        svc.update_account_summary({"cash_balance": 80000.0})
        svc.update_position("GOOG", {
            "market_value": 20000.0, "side": "LONG", "sec_type": "STK",
        })
        svc.recompute_strategy_metrics()
        assert svc.risk_manager.peak_stock_equity == 100000.0

        # Cash drops
        svc.update_account_summary({"cash_balance": 70000.0})
        svc.recompute_strategy_metrics()
        assert svc.risk_manager.stock_equity == 90000.0
        assert svc.risk_manager.peak_stock_equity == 100000.0  # unchanged

    def test_short_stock_excluded_from_stock_equity(self, svc):
        """Short stock positions should NOT be included in stock equity."""
        svc.update_account_summary({"cash_balance": 50000.0})
        svc.update_position("TSLA", {
            "quantity": -10, "market_value": -5000.0,
            "side": "SHORT", "sec_type": "STK",
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager
        # Short stock excluded — stock equity is cash only
        assert rm.stock_equity == 50000.0

    def test_long_option_excluded_from_stock_equity(self, svc):
        """Long option positions should NOT be included in stock equity."""
        svc.update_account_summary({"cash_balance": 50000.0})
        svc.update_position("AAPL 250418C200", {
            "quantity": 5, "market_value": 2500.0,
            "side": "LONG", "sec_type": "OPT",
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager
        # Long options excluded — stock equity is cash only
        assert rm.stock_equity == 50000.0

    def test_mixed_portfolio_only_long_stocks_in_stock_equity(self, svc):
        """Only long STK positions contribute to stock equity."""
        svc.update_account_summary({"cash_balance": 40000.0})
        svc.update_position("GOOG", {
            "quantity": 10, "market_value": 15000.0,
            "side": "LONG", "sec_type": "STK",
        })
        svc.update_position("TSLA", {
            "quantity": -5, "market_value": -3000.0,
            "side": "SHORT", "sec_type": "STK",
        })
        svc.update_position("AAPL 250418C200", {
            "quantity": 2, "market_value": 1000.0,
            "side": "LONG", "sec_type": "OPT",
        })
        svc.update_position("SPY 250418P400", {
            "quantity": -3, "market_value": -600.0,
            "side": "SHORT", "sec_type": "OPT",
            "premium_collected": 900.0, "current_liability": 600.0,
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager
        # Only cash + long GOOG stock
        assert rm.stock_equity == 55000.0  # 40k cash + 15k GOOG
        assert rm.short_options_premium_collected == 900.0
        assert rm.short_options_current_liability == 600.0

    def test_skips_update_when_cash_balance_missing(self, svc):
        """recompute_strategy_metrics should not set the flag when cash_balance is missing."""
        # Only add a position, no cash_balance in account summary
        svc.update_position("GOOG", {
            "quantity": 10, "market_value": 15000.0,
            "side": "LONG", "sec_type": "STK",
        })
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager
        # Flag should remain False — fallback sync in RiskManager.update()
        # must continue to operate until cash_balance is known
        assert rm._stock_equity_from_positions is False

    def test_proceeds_once_cash_balance_arrives(self, svc):
        """recompute_strategy_metrics should work once cash_balance is present."""
        svc.update_position("GOOG", {
            "quantity": 10, "market_value": 15000.0,
            "side": "LONG", "sec_type": "STK",
        })
        # First call — no cash_balance yet
        svc.recompute_strategy_metrics()
        assert svc.risk_manager._stock_equity_from_positions is False

        # Now cash balance arrives
        svc.update_account_summary({"cash_balance": 50000.0})
        svc.recompute_strategy_metrics()
        rm = svc.risk_manager
        assert rm._stock_equity_from_positions is True
        assert rm.stock_equity == 65000.0  # 50k cash + 15k stock


# ==============================================================================
# API response
# ==============================================================================


class TestAPINewFields:
    """Test that /api/account/summary includes strategy-aware drawdown fields."""

    @pytest.fixture
    def app(self):
        from web import create_app
        return create_app({"TESTING": True})

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    @pytest.fixture
    def svc(self, app):
        return app.config["services"]

    def test_summary_includes_stock_drawdown(self, client, svc):
        svc.update_account_summary({"buying_power": 100000.0})
        resp = client.get("/api/account/summary")
        data = json.loads(resp.data)

        assert "stock_drawdown_pct" in data
        assert "premium_retention_pct" in data
        assert "short_options_premium_collected" in data
        assert "short_options_current_liability" in data

    def test_summary_values_reflect_risk_manager(self, client, svc):
        rm = svc.risk_manager
        rm.short_options_premium_collected = 1000.0
        rm.short_options_current_liability = 100.0
        rm.stock_equity = 90000.0
        rm.peak_stock_equity = 100000.0

        svc.update_account_summary({"buying_power": 100000.0})
        resp = client.get("/api/account/summary")
        data = json.loads(resp.data)

        assert data["stock_drawdown_pct"] == pytest.approx(0.10)
        assert data["premium_retention_pct"] == pytest.approx(0.90)
