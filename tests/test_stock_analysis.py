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


class TestTechnicalLevelsServiceInternals:
    """Tests for internal helpers in technical_levels_service."""

    # --- _cluster_pivots: empty pivots → return [] (line 133) ---
    def test_cluster_pivots_empty_returns_empty(self):
        result = technical_levels_service._cluster_pivots([], 100.0, False)
        assert result == []

    # --- _cluster_pivots: tight two-pivot zone gets widened (lines 156-157) ---
    def test_cluster_pivots_tight_zone_is_widened(self):
        # 100.0 and 100.1 → spread=0.1 < 100*0.005=0.5 → widening applied
        result = technical_levels_service._cluster_pivots([100.0, 100.1], 100.0, False)
        assert len(result) == 1
        assert result[0]["low"] < 100.0   # widened below
        assert result[0]["high"] > 100.1  # widened above

    # --- _ensure_extreme_zone: new zone appended when no match (lines 183-184) ---
    def test_ensure_extreme_zone_appends_when_no_match(self):
        zones = []
        technical_levels_service._ensure_extreme_zone(zones, 100.0, "52-week low", False)
        assert len(zones) == 1
        assert zones[0]["reason"] == "52-week low"
        assert zones[0]["touches"] == 2

    # --- _ensure_extreme_zone: also works for is_resistance=True ---
    def test_ensure_extreme_zone_resistance_appended(self):
        zones = []
        technical_levels_service._ensure_extreme_zone(zones, 200.0, "52-week high", True)
        assert len(zones) == 1
        assert zones[0]["low"] < 200.0   # spread applied

    # --- _confidence_label: touches < 2 → "low" (line 216) ---
    def test_confidence_label_one_touch_is_low(self):
        assert technical_levels_service._confidence_label(1) == "low"

    # --- _assess_momentum: < 20 closes → "insufficient_data" (line 222) ---
    def test_assess_momentum_insufficient_data(self):
        result = technical_levels_service._assess_momentum([100.0] * 15)
        assert result == "insufficient_data"

    # --- _assess_momentum: downtrend (line 233) ---
    def test_assess_momentum_downtrend(self):
        # Monotonically declining: current < ma20 < ma50
        closes = [100.0 - i * 0.5 for i in range(60)]
        assert technical_levels_service._assess_momentum(closes) == "downtrend"

    # --- _assess_momentum: volatile (line 237) ---
    def test_assess_momentum_volatile(self):
        # current far above ma20, but ma20 == ma50 (no clear trend)
        # [100]*40 + [90]*10 + [110]*10 → current=110, ma20=100, ma50=100 → volatile
        closes = [100.0] * 40 + [90.0] * 10 + [110.0] * 10
        assert technical_levels_service._assess_momentum(closes) == "volatile"

    # --- _technical_position: near_support (line 249) ---
    def test_technical_position_near_support(self):
        support = [{"low": 99.0, "high": 101.0}]
        result = technical_levels_service._technical_position(100.0, support, [])
        assert result == "near_support"

    # --- _technical_position: below_support (line 251) ---
    def test_technical_position_below_support(self):
        support = [{"low": 99.0, "high": 101.0}]
        result = technical_levels_service._technical_position(95.0, support, [])
        assert result == "below_support"

    # --- _technical_position: near_resistance (line 256) ---
    def test_technical_position_near_resistance(self):
        resistance = [{"low": 199.0, "high": 201.0}]
        result = technical_levels_service._technical_position(200.0, [], resistance)
        assert result == "near_resistance"

    # --- _technical_position: breakout (line 258) ---
    def test_technical_position_breakout(self):
        resistance = [{"low": 199.0, "high": 201.0}]
        result = technical_levels_service._technical_position(205.0, [], resistance)
        assert result == "breakout"


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

    def test_near_upper_band_status(self):
        """Price near (but below) the upper band gives near_upper_band status."""
        from web.routes.api_stock_analysis import _compute_bollinger_bands
        # 10 bars at 98, 10 bars at 102 → sma=100, std=2, upper=104, lower=96
        bars = [
            {"open": v, "high": v + 1, "low": v - 1, "close": v, "volume": 1_000_000}
            for v in ([98] * 10 + [102] * 10)
        ]
        # percent_b = (103.5 - 96) / 8 = 0.9375 → near_upper_band
        result = _compute_bollinger_bands(bars, 103.5)
        assert result["status"] == "near_upper_band"
        assert 0.8 <= result["percent_b"] < 1.0

    def test_zero_bandwidth_gives_insufficient_data_status(self):
        """All-equal closes produce std=0, band_width_abs=0, percent_b=None."""
        from web.routes.api_stock_analysis import _compute_bollinger_bands
        bars = [
            {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000}
            for _ in range(25)
        ]
        result = _compute_bollinger_bands(bars, 100.0)
        assert result["percent_b"] is None
        assert result["status"] == "insufficient_data"

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


# ==============================================================================
# Unit Tests: _build_price_context branches
# ==============================================================================


class TestBuildPriceContextBranches:
    """Covers _build_price_context paths not hit by existing tests."""

    def _call(self, **kwargs):
        from web.routes.api_stock_analysis import _build_price_context
        base = dict(
            current_price=100.0,
            fair_value={"status": "fairly_valued"},
            technical_levels={"technical_position": "", "momentum_status": ""},
            range_52w={"position_percentile": 50},
            bollinger_bands=None,
        )
        base.update(kwargs)
        return _build_price_context(**base)

    def test_potentially_undervalued_narrative(self):
        result = self._call(fair_value={"status": "potentially_undervalued"})
        assert "reasonable relative to estimated fair value" in result

    def test_potentially_overvalued_narrative(self):
        result = self._call(fair_value={"status": "potentially_overvalued"})
        assert "elevated relative to estimated fair value" in result

    def test_near_support_narrative(self):
        result = self._call(
            technical_levels={"technical_position": "near_support", "momentum_status": ""}
        )
        assert "near a detected support zone" in result

    def test_below_support_narrative(self):
        result = self._call(
            technical_levels={"technical_position": "below_support", "momentum_status": ""}
        )
        assert "below the nearest support zone" in result

    def test_near_resistance_narrative(self):
        result = self._call(
            technical_levels={"technical_position": "near_resistance", "momentum_status": ""}
        )
        assert "approaching a resistance zone" in result

    def test_downtrend_momentum_narrative(self):
        result = self._call(
            technical_levels={"technical_position": "", "momentum_status": "downtrend"}
        )
        assert "momentum remains weak" in result

    def test_uptrend_momentum_narrative(self):
        result = self._call(
            technical_levels={"technical_position": "", "momentum_status": "uptrend"}
        )
        assert "momentum appears positive" in result

    def test_near_upper_band_narrative(self):
        result = self._call(
            bollinger_bands={"status": "near_upper_band", "upper": 105.0, "middle": 100.0, "lower": 95.0}
        )
        assert "approaching overbought territory" in result


# ==============================================================================
# Unit Tests: position_appraisal_service edge cases
# ==============================================================================


class TestPositionAppraisalEdgeCases:
    """Covers paths in position_appraisal_service not hit by existing tests."""

    # --- zero entry_price → has_position: False (line 48) ---
    def test_zero_entry_price_returns_no_position(self):
        result = position_appraisal_service.appraise_position(
            position={"quantity": 100, "entry_price": 0, "unrealized_pnl": 0},
            current_price=100.0,
            fair_value={"status": "fairly_valued", "low": 90.0, "high": 110.0},
            technical_levels={"support": [], "resistance": []},
        )
        assert result["has_position"] is False

    # --- _entry_vs_fair_value: fv_low or fv_high is None → "unavailable" ---
    def test_entry_vs_fair_value_null_bounds_returns_unavailable(self):
        result = position_appraisal_service._entry_vs_fair_value(
            100.0, {"status": "fairly_valued", "low": None, "high": 120.0}
        )
        assert result == "unavailable"

    # --- _entry_vs_fair_value: entry > fv_high → "above_fair_value" (line 100) ---
    def test_entry_vs_fair_value_above_range(self):
        result = position_appraisal_service._entry_vs_fair_value(
            150.0, {"status": "fairly_valued", "low": 90.0, "high": 120.0}
        )
        assert result == "above_fair_value"

    # --- _entry_vs_support: entry <= nearest.high → "near_support" (line 113) ---
    def test_entry_vs_support_near_support(self):
        support = [{"low": 88.0, "high": 92.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._entry_vs_support(
            91.0, {"support": support, "resistance": []}
        )
        assert result == "near_support"

    # --- _entry_vs_support: entry > nearest.high*1.05 → "well_above_support" (line 116) ---
    def test_entry_vs_support_well_above(self):
        support = [{"low": 88.0, "high": 90.0, "confidence": "high", "reason": "t"}]
        # 100 > 90 * 1.05 = 94.5 → well_above_support
        result = position_appraisal_service._entry_vs_support(
            100.0, {"support": support, "resistance": []}
        )
        assert result == "well_above_support"

    # --- _assess_entry_quality: "good" valuation score (line 138) ---
    def test_assess_entry_quality_good_when_entry_below_fv_low(self):
        # entry=85 <= fv_low=90 → "good" valuation; no support → no technical dim
        result = position_appraisal_service._assess_entry_quality(
            entry_price=85.0,
            current_price=95.0,
            fair_value={"status": "fairly_valued", "low": 90.0, "high": 120.0},
            technical_levels={"support": [], "resistance": []},
        )
        assert result == "good"

    # --- _assess_entry_quality: "weak" valuation score (line 145) ---
    def test_assess_entry_quality_weak_when_entry_above_fv_high(self):
        # entry=130 > fv_high=120 → "weak" valuation; no support → scores=["weak"]
        result = position_appraisal_service._assess_entry_quality(
            entry_price=130.0,
            current_price=125.0,
            fair_value={"status": "fairly_valued", "low": 90.0, "high": 120.0},
            technical_levels={"support": [], "resistance": []},
        )
        assert result == "weak"

    # --- _assess_entry_quality: "good" technical score (line 147) ---
    def test_assess_entry_quality_good_technical_when_entry_near_support(self):
        # entry=91 <= support_high*1.02=91.8 → "good" technical; unavailable fv
        support = [{"low": 88.0, "high": 90.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._assess_entry_quality(
            entry_price=91.0,
            current_price=95.0,
            fair_value={"status": "unavailable"},
            technical_levels={"support": support, "resistance": []},
        )
        assert result == "good"

    # --- _assess_entry_quality: "weak" technical score (line 152) ---
    def test_assess_entry_quality_weak_technical_when_entry_well_above_support(self):
        # entry=100 > support_high*1.10=99 → "weak" technical; unavailable fv
        support = [{"low": 85.0, "high": 90.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._assess_entry_quality(
            entry_price=100.0,
            current_price=95.0,
            fair_value={"status": "unavailable"},
            technical_levels={"support": support, "resistance": []},
        )
        assert result == "weak"

    # --- _assess_entry_quality: no data → "unclear" (lines 159-161) ---
    def test_assess_entry_quality_unclear_without_any_data(self):
        result = position_appraisal_service._assess_entry_quality(
            entry_price=100.0,
            current_price=100.0,
            fair_value={"status": "unavailable"},
            technical_levels={"support": [], "resistance": []},
        )
        assert result == "unclear"

    # --- _build_summary: below_support tech position (line 192) ---
    def test_build_summary_includes_below_support_narrative(self):
        result = position_appraisal_service._build_summary(
            entry_price=100.0,
            current_price=80.0,
            quantity=100,
            unrealized_pnl_pct=-20.0,
            entry_vs_fair_value="within_fair_value",
            entry_vs_support="near_support",
            entry_quality="reasonable",
            technical_levels={"technical_position": "below_support"},
        )
        assert "below the nearest detected support zone" in result

    # --- _build_summary: near_resistance tech position (line 194) ---
    def test_build_summary_includes_near_resistance_narrative(self):
        result = position_appraisal_service._build_summary(
            entry_price=100.0,
            current_price=108.0,
            quantity=100,
            unrealized_pnl_pct=8.0,
            entry_vs_fair_value="within_fair_value",
            entry_vs_support="above_support",
            entry_quality="reasonable",
            technical_levels={"technical_position": "near_resistance"},
        )
        assert "near a detected resistance zone" in result

    # --- _build_summary: above_fair_value entry context (lines 205-206) ---
    def test_build_summary_includes_above_fair_value_narrative(self):
        result = position_appraisal_service._build_summary(
            entry_price=150.0,
            current_price=145.0,
            quantity=100,
            unrealized_pnl_pct=-3.3,
            entry_vs_fair_value="above_fair_value",
            entry_vs_support="well_above_support",
            entry_quality="weak",
            technical_levels={"technical_position": ""},
        )
        assert "above the estimated fair value range" in result

    # --- _entry_vs_fair_value: status == "unavailable" → return "unavailable" (line 92) ---
    def test_entry_vs_fair_value_unavailable_status_returns_unavailable(self):
        result = position_appraisal_service._entry_vs_fair_value(
            100.0, {"status": "unavailable"}
        )
        assert result == "unavailable"

    # --- _entry_vs_support: above support but < 1.05x → "above_support" (line 116) ---
    def test_entry_vs_support_above_but_not_well_above(self):
        # entry=93 > high=90 but 93 < 90*1.05=94.5 → "above_support"
        support = [{"low": 88.0, "high": 90.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._entry_vs_support(
            93.0, {"support": support, "resistance": []}
        )
        assert result == "above_support"

    # --- _assess_entry_quality: "reasonable" technical score (line 147) ---
    def test_assess_entry_quality_reasonable_technical(self):
        # entry=95 in range (90*1.02=91.8, 90*1.10=99] → "reasonable" technical; unavail fv
        support = [{"low": 88.0, "high": 90.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._assess_entry_quality(
            entry_price=95.0,
            current_price=95.0,
            fair_value={"status": "unavailable"},
            technical_levels={"support": support, "resistance": []},
        )
        assert result == "reasonable"

    # --- _assess_entry_quality: mixed good+weak → "reasonable" (lines 159-160) ---
    def test_assess_entry_quality_mixed_good_weak_returns_reasonable(self):
        # entry=95: fv_low=100 → 95 <= 100 → "good" valuation
        # support_high=85: 95 > 85*1.10=93.5 → "weak" technical
        # scores=["good","weak"] → weak in scores AND good in scores → line 159 elif → "reasonable"
        support = [{"low": 82.0, "high": 85.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._assess_entry_quality(
            entry_price=95.0,
            current_price=100.0,
            fair_value={"status": "fairly_valued", "low": 100.0, "high": 120.0},
            technical_levels={"support": support, "resistance": []},
        )
        assert result == "reasonable"

    # --- _assess_entry_quality: all "reasonable" scores → fallback return (line 161) ---
    def test_assess_entry_quality_all_reasonable_returns_reasonable(self):
        # fv_low=90, fv_high=120; entry=100 → 90 < 100 <= 120 → "reasonable" valuation
        # support_high=90; entry=94 → 90*1.02=91.8 < 94 <= 90*1.10=99 → "reasonable" technical
        support = [{"low": 85.0, "high": 90.0, "confidence": "high", "reason": "t"}]
        result = position_appraisal_service._assess_entry_quality(
            entry_price=94.0,
            current_price=100.0,
            fair_value={"status": "fairly_valued", "low": 90.0, "high": 120.0},
            technical_levels={"support": support, "resistance": []},
        )
        assert result == "reasonable"


# ==============================================================================
# API edge cases: invalid ticker, price fallback, exception paths
# ==============================================================================


class TestStockAnalysisAPIEdgeCases:
    """Covers API route branches not exercised by existing TestStockAnalysisAPI."""

    # --- invalid ticker → 400 (line 37) ---
    def test_invalid_ticker_returns_400(self, client):
        resp = client.get("/api/stocks/inv@lid!/analysis")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid ticker symbol" in data["error"]

    # --- current_price from bars when fundamentals has none (lines 63-65) ---
    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_price_falls_back_to_latest_bar_close(self, mock_fundamentals, mock_history, client):
        """When fundamentals has no current_price, the last bar's close is used."""
        mock_fundamentals.return_value = {"symbol": "TEST", "name": "Test Corp"}
        mock_history.return_value = _make_bars(60, 100.0)

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["current_price"] > 0

    # --- route-level exception → 500 (line 159) ---
    @patch("data.fundamentals.fetch_fundamentals")
    def test_unexpected_exception_returns_500(self, mock_fundamentals, client):
        """An unhandled exception in the route returns 500 with a safe message."""
        mock_fundamentals.side_effect = RuntimeError("unexpected boom")
        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "could not be completed" in data["error"].lower()

    # --- 52-week range fallback to fundamentals (lines 149-151) ---
    @patch("web.stock_analysis_services.technical_levels_service.detect_support_resistance")
    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_range_52w_falls_back_to_fundamentals_when_missing(
        self, mock_fundamentals, mock_history, mock_levels, client
    ):
        """When technical_levels returns no range_52w.low, fundamentals values are used."""
        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)
        mock_levels.return_value = {
            "support": [],
            "resistance": [],
            "technical_position": "",
            "momentum_status": "",
            "range_52w": {},  # no low/high
        }

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()
        # Fallback uses fifty_two_week_low / high from _make_fundamentals
        assert data["range_52w"]["low"] == 80.0
        assert data["range_52w"]["high"] == 130.0

    # --- active signals exception → empty list (lines 283-285) ---
    @patch("web.routes.api_stock_analysis.get_services")
    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_active_signals_exception_returns_empty_list(
        self, mock_fundamentals, mock_history, mock_get_services, client
    ):
        """If strategy_registry raises, active_strategy_signals is empty list."""
        from unittest.mock import Mock
        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)

        mock_svc = Mock()
        mock_svc.get_positions.return_value = {}
        mock_svc.strategy_registry.get_all_strategies.side_effect = RuntimeError("registry boom")
        mock_get_services.return_value = mock_svc

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active_strategy_signals"] == []

    # --- strategy with no indicators is skipped (line 260) ---
    @patch("web.routes.api_stock_analysis.get_services")
    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_strategy_with_no_indicators_is_skipped(
        self, mock_fundamentals, mock_history, mock_get_services, client
    ):
        """Strategies whose get_indicator_values returns falsy are not included."""
        from unittest.mock import Mock
        from strategies.base_strategy import StrategyState

        mock_fundamentals.return_value = _make_fundamentals(100.0)
        mock_history.return_value = _make_bars(60, 100.0)

        mock_strategy = Mock()
        mock_strategy.middle_band = {"TEST": 100.0}
        mock_strategy.state = StrategyState.RUNNING
        mock_strategy.config.symbols = ["TEST"]
        mock_strategy.get_indicator_values.return_value = None  # triggers the continue

        mock_svc = Mock()
        mock_svc.get_positions.return_value = {}
        mock_svc.strategy_registry.get_all_strategies.return_value = [mock_strategy]
        mock_get_services.return_value = mock_svc

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active_strategy_signals"] == []

    # --- _calc_percentile: return None for invalid inputs (line 159) ---
    def test_calc_percentile_returns_none_for_invalid_inputs(self):
        """_calc_percentile returns None when price, low, or high are missing/equal."""
        from web.routes.api_stock_analysis import _calc_percentile
        assert _calc_percentile(None, 80.0, 130.0) is None
        assert _calc_percentile(100.0, None, 130.0) is None
        assert _calc_percentile(100.0, 100.0, 100.0) is None  # high == low

    # --- non-finite current_price from fundamentals → bar fallback (line 63) ---
    @patch("data.fundamentals.fetch_price_history")
    @patch("data.fundamentals.fetch_fundamentals")
    def test_nonfinite_current_price_falls_back_to_bars(
        self, mock_fundamentals, mock_history, client
    ):
        """A NaN/inf current_price from fundamentals is discarded; bar close is used."""
        import math
        fdata = _make_fundamentals(float("nan"))
        mock_fundamentals.return_value = fdata
        mock_history.return_value = _make_bars(60, 100.0)

        resp = client.get("/api/stocks/TEST/analysis")
        assert resp.status_code == 200
        data = resp.get_json()
        assert math.isfinite(data["current_price"])
        assert data["current_price"] > 0
