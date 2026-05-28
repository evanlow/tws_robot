"""Tests for Stock Analysis feature — valuation, technical levels, position appraisal.

Covers both cases: user with open position and user without open position.
"""

from unittest.mock import patch

import pytest

from web import create_app
from web.stock_analysis_services import (
    valuation_service,
    technical_levels_service,
    position_appraisal_service,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def app(monkeypatch):
    """Create Flask app with test configuration."""
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr("web.routes.api_connection.is_accepted", lambda: True)
    app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def services(app):
    return app.config["services"]


# ==============================================================================
# Sample data helpers
# ==============================================================================


def _make_bars(count=60, base_price=100.0):
    """Generate synthetic OHLCV bars for testing."""
    import random
    random.seed(42)
    bars = []
    price = base_price
    for i in range(count):
        change = random.uniform(-2, 2)
        price = max(price + change, 50)
        o = price
        h = price + random.uniform(0, 3)
        l = price - random.uniform(0, 3)
        c = price + random.uniform(-1, 1)
        bars.append({
            "timestamp": f"2024-01-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": random.randint(100000, 1000000),
        })
    return bars


def _make_fundamentals(current_price=100.0):
    """Generate sample fundamentals data."""
    return {
        "symbol": "TEST",
        "name": "Test Corp",
        "current_price": current_price,
        "eps_trailing": 5.0,
        "pe_trailing": 20.0,
        "eps_forward": 6.0,
        "pe_forward": 18.0,
        "target_mean_price": 110.0,
        "target_low_price": 95.0,
        "target_high_price": 130.0,
        "fifty_two_week_high": 130.0,
        "fifty_two_week_low": 80.0,
        "sector": "Technology",
        "industry": "Software",
    }


# ==============================================================================
# Unit Tests: Valuation Service
# ==============================================================================


class TestValuationService:
    """Tests for valuation_service.estimate_fair_value."""

    def test_full_data_produces_range(self):
        fundamentals = _make_fundamentals(100.0)
        result = valuation_service.estimate_fair_value(fundamentals, 100.0)

        assert result["low"] is not None
        assert result["high"] is not None
        assert result["low"] < result["high"]
        assert result["status"] in (
            "potentially_undervalued", "fairly_valued", "potentially_overvalued"
        )
        assert result["confidence"] in ("low", "medium", "high")
        assert len(result["methods_used"]) >= 1

    def test_missing_eps_returns_unavailable(self):
        fundamentals = {"current_price": 100.0}
        result = valuation_service.estimate_fair_value(fundamentals, 100.0)

        assert result["status"] == "unavailable"
        assert result["low"] is None
        assert result["unavailable_reason"] is not None

    def test_no_price_returns_unavailable(self):
        result = valuation_service.estimate_fair_value({}, None)
        assert result["status"] == "unavailable"

    def test_undervalued_status(self):
        fundamentals = _make_fundamentals(50.0)  # Below any fair value
        result = valuation_service.estimate_fair_value(fundamentals, 50.0)
        assert result["status"] == "potentially_undervalued"

    def test_overvalued_status(self):
        fundamentals = _make_fundamentals(200.0)
        result = valuation_service.estimate_fair_value(fundamentals, 200.0)
        assert result["status"] == "potentially_overvalued"


# ==============================================================================
# Unit Tests: Technical Levels Service
# ==============================================================================


class TestTechnicalLevelsService:
    """Tests for technical_levels_service.detect_support_resistance."""

    def test_sufficient_bars_produces_result(self):
        bars = _make_bars(60, 100.0)
        result = technical_levels_service.detect_support_resistance(bars, 100.0)

        assert "support" in result
        assert "resistance" in result
        assert "range_52w" in result
        assert result["range_52w"]["low"] is not None
        assert result["range_52w"]["high"] is not None
        assert result["momentum_status"] in (
            "uptrend", "downtrend", "sideways", "volatile", "insufficient_data"
        )

    def test_insufficient_bars_returns_empty(self):
        bars = _make_bars(5, 100.0)
        result = technical_levels_service.detect_support_resistance(bars, 100.0)
        assert result["support"] == []
        assert result["resistance"] == []
        assert result["momentum_status"] == "insufficient_data"

    def test_empty_bars(self):
        result = technical_levels_service.detect_support_resistance([], 100.0)
        assert result["support"] == []

    def test_zones_have_confidence_and_reason(self):
        bars = _make_bars(100, 100.0)
        result = technical_levels_service.detect_support_resistance(bars, 100.0)
        for zone in result["support"] + result["resistance"]:
            assert "confidence" in zone
            assert "reason" in zone
            assert zone["confidence"] in ("low", "medium", "high")
            assert "low" in zone and "high" in zone


# ==============================================================================
# Unit Tests: Position Appraisal Service
# ==============================================================================


class TestPositionAppraisalService:
    """Tests for position_appraisal_service.appraise_position."""

    def test_no_position(self):
        result = position_appraisal_service.appraise_position(
            position=None,
            current_price=100.0,
            fair_value={"status": "unavailable", "low": None, "high": None},
            technical_levels={"support": [], "resistance": []},
        )
        assert result["has_position"] is False

    def test_with_position(self):
        fair_value = {"status": "fairly_valued", "low": 90.0, "high": 120.0}
        technical_levels = {
            "support": [{"low": 88.0, "high": 90.0, "confidence": "high", "reason": "test"}],
            "resistance": [{"low": 110.0, "high": 115.0, "confidence": "medium", "reason": "test"}],
            "technical_position": "middle_of_range",
        }
        position = {
            "quantity": 500,
            "entry_price": 101.20,
            "unrealized_pnl": -6075.0,
        }
        result = position_appraisal_service.appraise_position(
            position=position,
            current_price=89.05,
            fair_value=fair_value,
            technical_levels=technical_levels,
        )

        assert result["has_position"] is True
        assert result["quantity"] == 500
        assert result["average_entry"] == 101.20
        assert result["unrealised_pnl_percent"] < 0
        assert result["entry_quality"] in ("good", "reasonable", "weak", "unclear")
        assert "summary" in result
        assert len(result["summary"]) > 0

    def test_entry_below_fair_value(self):
        fair_value = {"status": "fairly_valued", "low": 100.0, "high": 120.0}
        technical_levels = {"support": [], "resistance": [], "technical_position": "middle_of_range"}
        position = {"quantity": 100, "entry_price": 90.0, "unrealized_pnl": 500}
        result = position_appraisal_service.appraise_position(
            position=position, current_price=95.0,
            fair_value=fair_value, technical_levels=technical_levels,
        )
        assert result["entry_vs_fair_value"] == "below_fair_value"

    def test_no_buy_sell_in_summary(self):
        fair_value = {"status": "fairly_valued", "low": 90.0, "high": 120.0}
        technical_levels = {
            "support": [{"low": 85.0, "high": 88.0, "confidence": "medium", "reason": "test"}],
            "resistance": [],
            "technical_position": "near_support",
        }
        position = {"quantity": 100, "entry_price": 100.0, "unrealized_pnl": -1000}
        result = position_appraisal_service.appraise_position(
            position=position, current_price=90.0,
            fair_value=fair_value, technical_levels=technical_levels,
        )
        summary_lower = result["summary"].lower()
        assert "buy" not in summary_lower
        assert "sell" not in summary_lower
        assert "hold" not in summary_lower


# ==============================================================================
# Integration Tests: API Endpoint
# ==============================================================================


class TestStockAnalysisAPI:
    """Tests for GET /api/stocks/<ticker>/analysis."""

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_without_position(self, mock_fundamentals, mock_history, client):
        """Test analysis for a stock where user has no open position."""
        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["ticker"] == "TEST"
        assert data["current_price"] == 100.0
        assert "fair_value" in data
        assert "technical_levels" in data
        assert "disclaimer" in data
        assert data["open_position"]["has_position"] is False
        # Disclaimer disclaims buy/sell but does not instruct
        assert "not a buy/sell recommendation" in data["disclaimer"].lower()
        # Price context should not contain direct instructions
        price_ctx = data.get("price_context", "").lower()
        assert "buy now" not in price_ctx
        assert "sell now" not in price_ctx

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_with_position(self, mock_fundamentals, mock_history, client, services):
        """Test analysis for a stock where user has an open position."""
        mock_fundamentals.return_value = _make_fundamentals(89.05)
        mock_history.return_value = _make_bars(60, 90.0)

        # Add a position
        services.update_position("TEST", {
            "quantity": 500,
            "entry_price": 101.20,
            "current_price": 89.05,
            "market_value": 44525.0,
            "unrealized_pnl": -6075.0,
        })

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["open_position"]["has_position"] is True
        assert data["open_position"]["quantity"] == 500
        assert data["open_position"]["average_entry"] == 101.20
        assert "entry_quality" in data["open_position"]
        assert "summary" in data["open_position"]

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_missing_data(self, mock_fundamentals, mock_history, client):
        """Test graceful handling when data is unavailable."""
        mock_fundamentals.return_value = {"error": "not found", "symbol": "UNKNOWN"}
        mock_history.return_value = []

        resp = client.get("/api/stocks/UNKNOWN/analysis")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_missing_valuation_data(self, mock_fundamentals, mock_history, client):
        """Test fair value unavailable when no earnings data."""
        mock_fundamentals.return_value = {
            "symbol": "NOCASH",
            "name": "No Cash Corp",
            "current_price": 50.0,
            "fifty_two_week_high": 60.0,
            "fifty_two_week_low": 40.0,
        }
        mock_history.return_value = _make_bars(60, 50.0)

        resp = client.get("/api/stocks/NOCASH/analysis")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["fair_value"]["status"] == "unavailable"
        assert data["fair_value"]["unavailable_reason"] is not None

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_includes_bollinger_bands(self, mock_fundamentals, mock_history, client):
        """Test that the API response includes Bollinger Bands data."""
        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "bollinger_bands" in data
        bb = data["bollinger_bands"]
        assert bb["upper"] is not None
        assert bb["middle"] is not None
        assert bb["lower"] is not None
        assert bb["upper"] > bb["middle"] > bb["lower"]
        assert bb["bandwidth"] is not None
        assert bb["percent_b"] is not None
        assert bb["status"] in (
            "below_lower_band", "near_lower_band",
            "within_bands",
            "near_upper_band", "above_upper_band",
        )

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_includes_active_strategy_signals(self, mock_fundamentals, mock_history, client):
        """Test that active_strategy_signals key is present (may be empty)."""
        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "active_strategy_signals" in data
        assert isinstance(data["active_strategy_signals"], list)

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_analysis_excludes_non_running_strategy_signals(
        self, mock_fundamentals, mock_history, client, services
    ):
        """Test that only running strategies are exposed in active_strategy_signals."""
        from datetime import datetime, timezone

        from strategies.base_strategy import StrategyConfig
        from strategies.bollinger_bands import BollingerBandsStrategy
        from strategies.signal import Signal, SignalStrength, SignalType
        from strategies.strategy_registry import StrategyRegistry

        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)

        registry = StrategyRegistry(event_bus=services.event_bus, account_id="")
        registry.register_strategy_class("BollingerBands", BollingerBandsStrategy)
        services._strategy_registry = registry

        running = registry.create_strategy(
            "BollingerBands",
            StrategyConfig(name="BB_RUNNING", symbols=["TEST"]),
        )
        running.upper_band["TEST"] = 110.0
        running.middle_band["TEST"] = 100.0
        running.lower_band["TEST"] = 90.0
        running.signals_to_emit.append(
            Signal(
                symbol="TEST",
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                timestamp=datetime.now(timezone.utc),
                reason="Running strategy",
                confidence=0.8,
            )
        )
        registry.start_strategy("BB_RUNNING")

        paused = registry.create_strategy(
            "BollingerBands",
            StrategyConfig(name="BB_PAUSED", symbols=["TEST"]),
        )
        paused.upper_band["TEST"] = 111.0
        paused.middle_band["TEST"] = 101.0
        paused.lower_band["TEST"] = 91.0
        paused.signals_to_emit.append(
            Signal(
                symbol="TEST",
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                timestamp=datetime.now(timezone.utc),
                reason="Paused strategy",
                confidence=0.6,
            )
        )
        registry.start_strategy("BB_PAUSED")
        registry.pause_strategy("BB_PAUSED")

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["active_strategy_signals"]) == 1
        assert data["active_strategy_signals"][0]["strategy_name"] == "BB_RUNNING"
        assert data["active_strategy_signals"][0]["state"] == "RUNNING"

    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_bollinger_bands_insufficient_data(self, mock_fundamentals, mock_history, client):
        """Test Bollinger Bands returns insufficient_data with few bars."""
        mock_fundamentals.return_value = _make_fundamentals(100.0)
        # Only 10 bars — not enough for 20-period BB
        mock_history.return_value = _make_bars(10, 100.0)

        resp = client.get("/api/stocks/TEST/analysis")
        # May get 200 or 404 depending on price availability
        if resp.status_code == 200:
            data = resp.get_json()
            bb = data["bollinger_bands"]
            assert bb["status"] == "insufficient_data"

    def test_stock_analysis_page_renders(self, client):
        """Test the HTML page route renders without error."""
        resp = client.get("/stocks/AAPL/analysis")
        assert resp.status_code == 200
        assert b"AAPL" in resp.data
        assert b"Back to Stock Analysis Dashboard" in resp.data


class TestStockAnalysisDashboard:
    """Tests for GET /stocks/analysis — the stock analysis dashboard."""

    def test_dashboard_loads(self, client):
        """Test the dashboard page loads successfully."""
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"Stock Analysis" in resp.data
        assert b"Enter ticker symbol" in resp.data

    def test_dashboard_empty_positions(self, client):
        """Test dashboard shows empty state when no positions."""
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"No open positions" in resp.data

    def test_dashboard_with_positions(self, client, services):
        """Test dashboard shows position shortcuts."""
        services.update_position("GOOG", {
            "quantity": 100,
            "entry_price": 190.0,
            "current_price": 385.0,
            "unrealized_pnl": 19500.0,
            "unrealized_pnl_pct": 1.026,
            "side": "LONG",
        })
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"GOOG" in resp.data
        assert b"/stocks/GOOG/analysis" in resp.data
        assert b"Analyze" in resp.data

    def test_dashboard_option_symbol_links_to_underlying(self, client, services):
        """Test that option symbols link to underlying stock analysis."""
        services.update_position("GOOG 260821C00415000", {
            "quantity": -1,
            "entry_price": 5.0,
            "current_price": 3.0,
            "unrealized_pnl": 200.0,
            "unrealized_pnl_pct": 0.4,
            "side": "SHORT",
            "sec_type": "OPT",
        })
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"/stocks/GOOG/analysis" in resp.data

    def test_dashboard_unparseable_symbol(self, client, services):
        """Test that unparseable symbols show disabled state."""
        services.update_position("???WEIRD", {
            "quantity": 100,
            "entry_price": 10.0,
            "current_price": 12.0,
            "unrealized_pnl": 200.0,
            "unrealized_pnl_pct": 0.2,
            "side": "LONG",
        })
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"Analysis unavailable" in resp.data


# ==============================================================================
# Unit Tests: Bollinger Bands Computation
# ==============================================================================


class TestBollingerBandsComputation:
    """Tests for the _compute_bollinger_bands helper in the API."""

    def test_compute_bollinger_bands_basic(self):
        from web.routes.api_stock_analysis import _compute_bollinger_bands
        bars = _make_bars(60, 100.0)
        result = _compute_bollinger_bands(bars, 100.0)

        assert result["upper"] is not None
        assert result["middle"] is not None
        assert result["lower"] is not None
        assert result["upper"] > result["middle"] > result["lower"]
        assert result["bandwidth"] > 0
        assert result["percent_b"] is not None
        assert result["status"] != "insufficient_data"

    def test_compute_bollinger_bands_insufficient_bars(self):
        from web.routes.api_stock_analysis import _compute_bollinger_bands
        bars = _make_bars(5, 100.0)
        result = _compute_bollinger_bands(bars, 100.0)

        assert result["status"] == "insufficient_data"
        assert result["upper"] is None

    def test_compute_bollinger_bands_percent_b_extremes(self):
        from web.routes.api_stock_analysis import _compute_bollinger_bands
        # Bars with some variance so bands are non-zero width
        bars = [
            {"open": 100, "high": 102, "low": 98, "close": 100 + (i % 3) - 1, "volume": 1000}
            for i in range(25)
        ]
        # Price far above should give %B > 1
        result = _compute_bollinger_bands(bars, 200.0)
        assert result["percent_b"] is not None
        assert result["percent_b"] > 1
        assert result["status"] == "above_upper_band"

        # Price far below should give %B < 0
        result = _compute_bollinger_bands(bars, 50.0)
        assert result["percent_b"] is not None
        assert result["percent_b"] < 0
        assert result["status"] == "below_lower_band"

    def test_price_context_includes_bollinger_narrative(self):
        from web.routes.api_stock_analysis import _build_price_context
        bb_below = {"status": "below_lower_band", "percent_b": -0.1}
        context = _build_price_context(
            current_price=90.0,
            fair_value={"status": "unavailable"},
            technical_levels={"technical_position": "", "momentum_status": ""},
            range_52w={"position_percentile": 10},
            bollinger_bands=bb_below,
        )
        assert "oversold" in context.lower()

        bb_above = {"status": "above_upper_band", "percent_b": 1.1}
        context = _build_price_context(
            current_price=130.0,
            fair_value={"status": "unavailable"},
            technical_levels={"technical_position": "", "momentum_status": ""},
            range_52w={"position_percentile": 90},
            bollinger_bands=bb_above,
        )
        assert "overbought" in context.lower()


# ==============================================================================
# Unit Tests: parse_underlying_symbol
# ==============================================================================


class TestParseUnderlyingSymbol:
    """Tests for parse_underlying_symbol helper."""

    def test_plain_equity(self):
        from web.routes.stock_analysis import parse_underlying_symbol
        assert parse_underlying_symbol("GOOG") == "GOOG"
        assert parse_underlying_symbol("AAPL") == "AAPL"
        assert parse_underlying_symbol("BRK.B") == "BRK.B"

    def test_option_call(self):
        from web.routes.stock_analysis import parse_underlying_symbol
        assert parse_underlying_symbol("GOOG 260821C00415000") == "GOOG"

    def test_option_put(self):
        from web.routes.stock_analysis import parse_underlying_symbol
        assert parse_underlying_symbol("BIDU 2605P00121000") == "BIDU"

    def test_option_no_space(self):
        from web.routes.stock_analysis import parse_underlying_symbol
        assert parse_underlying_symbol("SPX250620C05500000") == "SPX"

    def test_empty_or_none(self):
        from web.routes.stock_analysis import parse_underlying_symbol
        assert parse_underlying_symbol("") is None
        assert parse_underlying_symbol(None) is None
        assert parse_underlying_symbol("   ") is None

    def test_unparseable(self):
        from web.routes.stock_analysis import parse_underlying_symbol
        assert parse_underlying_symbol("???WEIRD") is None
        assert parse_underlying_symbol("some random text") is None
