"""Tests for portfolio intelligence and stock deep-dive features.

Covers:
- ai.portfolio_analyzer: strategy deduction, strategy mix, full analysis
- ai.stock_analyzer: technical context, deep-dive analysis
- data.fundamentals: fundamentals fetcher
- data.portfolio_persistence: snapshots, analyses, cache
- web API endpoints: portfolio-insights, stock-deep-dive, snapshots
"""

import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def reset_ai_state():
    """Reset AI client state before each test."""
    from ai.client import reset_client
    reset_client()
    old = {k: os.environ.pop(k, None) for k in ["OPENAI_API_KEY", "AI_ENABLED"]}
    yield
    for k, v in old.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    reset_client()


@pytest.fixture
def app():
    """Create Flask app with test configuration."""
    from web import create_app
    return create_app({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def services(app):
    return app.config["services"]


@pytest.fixture
def sample_positions():
    """Return a dict of sample positions for testing."""
    return {
        "GOOG": {
            "quantity": 50,
            "entry_price": 140.0,
            "current_price": 165.0,
            "market_value": 8250.0,
            "unrealized_pnl": 1250.0,
            "side": "LONG",
            "sec_type": "STK",
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=120)).isoformat(),
        },
        "SLV": {
            "quantity": 200,
            "entry_price": 22.0,
            "current_price": 24.5,
            "market_value": 4900.0,
            "unrealized_pnl": 500.0,
            "side": "LONG",
            "sec_type": "STK",
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
        },
        "AAPL": {
            "quantity": 30,
            "entry_price": 180.0,
            "current_price": 175.0,
            "market_value": 5250.0,
            "unrealized_pnl": -150.0,
            "side": "LONG",
            "sec_type": "STK",
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        },
    }


@pytest.fixture
def db_for_persistence(tmp_path):
    """Set up a temporary SQLite database for persistence tests."""
    from data.database import Database, reset_database

    reset_database()
    db_path = tmp_path / "test_portfolio.db"
    db = Database(f"sqlite:///{db_path}")
    db.create_tables()

    # Patch get_database to return our test DB
    with patch("data.portfolio_persistence._get_db", return_value=db):
        yield db

    db.close()
    reset_database()


# ===========================================================================
# ai.portfolio_analyzer tests
# ===========================================================================


class TestStrategyDeduction:
    """Tests for rule-based strategy classification."""

    def test_long_term_hold(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_BUY_AND_HOLD
        pos = {
            "symbol": "GOOG",
            "entry_price": 100.0,
            "current_price": 120.0,
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=180)).isoformat(),
            "side": "LONG",
        }
        result = deduce_position_strategy(pos)
        assert result["strategy"] == STRATEGY_BUY_AND_HOLD
        assert result["confidence"] >= 0.5
        assert "GOOG" in result["reasoning"]

    def test_short_term_momentum(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_MOMENTUM
        pos = {
            "symbol": "TSLA",
            "entry_price": 200.0,
            "current_price": 250.0,
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "side": "LONG",
        }
        result = deduce_position_strategy(pos)
        assert result["strategy"] == STRATEGY_MOMENTUM
        assert result["confidence"] >= 0.5

    def test_short_option_income(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_INCOME
        pos = {
            "symbol": "AAPL_PUT",
            "side": "SHORT",
            "sec_type": "OPT",
            "entry_price": 5.0,
            "current_price": 3.0,
        }
        result = deduce_position_strategy(pos)
        assert result["strategy"] == STRATEGY_INCOME
        assert result["confidence"] >= 0.80

    def test_hedging_instrument(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_HEDGING
        pos = {
            "symbol": "SQQQ",
            "side": "LONG",
            "entry_price": 10.0,
            "current_price": 11.0,
        }
        result = deduce_position_strategy(pos)
        assert result["strategy"] == STRATEGY_HEDGING

    def test_small_speculative_position(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_SPECULATIVE
        pos = {
            "symbol": "XYZ",
            "entry_price": 1.0,
            "current_price": 1.2,
            "portfolio_weight": 0.01,
            "side": "LONG",
        }
        result = deduce_position_strategy(pos)
        assert result["strategy"] == STRATEGY_SPECULATIVE

    def test_no_data_returns_unknown(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_UNKNOWN
        pos = {"symbol": "MYSTERY"}
        result = deduce_position_strategy(pos)
        assert result["strategy"] in (STRATEGY_UNKNOWN, "speculative")
        assert "reasoning" in result

    def test_medium_term_value(self):
        from ai.portfolio_analyzer import deduce_position_strategy, STRATEGY_VALUE
        pos = {
            "symbol": "JNJ",
            "entry_price": 150.0,
            "current_price": 155.0,
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            "side": "LONG",
        }
        result = deduce_position_strategy(pos)
        assert result["strategy"] == STRATEGY_VALUE

    def test_large_position_boosts_confidence(self):
        from ai.portfolio_analyzer import deduce_position_strategy
        pos = {
            "symbol": "MSFT",
            "entry_price": 300.0,
            "current_price": 350.0,
            "entry_time": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
            "portfolio_weight": 0.35,
            "side": "LONG",
        }
        result = deduce_position_strategy(pos)
        assert result["confidence"] >= 0.5


class TestStrategyMix:
    """Tests for portfolio-level strategy mix computation."""

    def test_strategy_mix_weights(self):
        from ai.portfolio_analyzer import compute_strategy_mix
        deductions = [
            {"strategy": "momentum"},
            {"strategy": "buy_and_hold"},
            {"strategy": "momentum"},
        ]
        positions = [
            {"market_value": 5000},
            {"market_value": 3000},
            {"market_value": 2000},
        ]
        mix = compute_strategy_mix(deductions, positions)
        assert abs(mix["momentum"] - 0.7) < 0.01
        assert abs(mix["buy_and_hold"] - 0.3) < 0.01

    def test_empty_portfolio(self):
        from ai.portfolio_analyzer import compute_strategy_mix
        mix = compute_strategy_mix([], [])
        assert mix == {}

    def test_zero_value_portfolio(self):
        from ai.portfolio_analyzer import compute_strategy_mix
        mix = compute_strategy_mix(
            [{"strategy": "momentum"}],
            [{"market_value": 0}],
        )
        assert mix == {}


class TestPortfolioAnalyzer:
    """Tests for the full PortfolioAnalyzer class."""

    def test_analyze_without_ai(self, sample_positions):
        from ai.portfolio_analyzer import PortfolioAnalyzer
        analyzer = PortfolioAnalyzer()
        result = analyzer.analyze_portfolio(sample_positions, use_ai=False)

        assert "deductions" in result
        assert "strategy_mix" in result
        assert "positions_enriched" in result
        assert len(result["deductions"]) == 3
        assert len(result["positions_enriched"]) == 3
        assert result["ai_narrative"] is None

        # All enriched positions should have deduced_strategy
        for pe in result["positions_enriched"]:
            assert "deduced_strategy" in pe
            assert "strategy_confidence" in pe
            assert pe["deduced_strategy"] != ""

    def test_analyze_with_ai_disabled(self, sample_positions):
        """When AI is not configured, analysis should still return heuristics."""
        from ai.portfolio_analyzer import PortfolioAnalyzer
        analyzer = PortfolioAnalyzer()
        result = analyzer.analyze_portfolio(sample_positions, use_ai=True)
        # AI client returns None when not configured, so ai_narrative stays None
        assert result["ai_narrative"] is None
        assert len(result["positions_enriched"]) == 3

    def test_analyze_empty_portfolio(self):
        from ai.portfolio_analyzer import PortfolioAnalyzer
        analyzer = PortfolioAnalyzer()
        result = analyzer.analyze_portfolio({}, use_ai=False)
        assert result["deductions"] == []
        assert result["strategy_mix"] == {}
        assert result["positions_enriched"] == []


class TestParseAiJson:
    """Tests for the JSON parsing helper."""

    def test_parse_valid_json(self):
        from ai.portfolio_analyzer import _parse_ai_json
        result = _parse_ai_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_markdown_fences(self):
        from ai.portfolio_analyzer import _parse_ai_json
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_ai_json(raw)
        assert result == {"key": "value"}

    def test_parse_invalid_json(self):
        from ai.portfolio_analyzer import _parse_ai_json
        result = _parse_ai_json("not json at all")
        assert result is None

    def test_parse_empty_string(self):
        from ai.portfolio_analyzer import _parse_ai_json
        assert _parse_ai_json("") is None
        assert _parse_ai_json(None) is None


# ===========================================================================
# ai.stock_analyzer tests
# ===========================================================================


class TestTechnicalContext:
    """Tests for compute_technical_context."""

    def test_with_sufficient_history(self):
        from ai.stock_analyzer import compute_technical_context
        # Generate 250 bars of simulated price data
        history = []
        base_price = 100.0
        for i in range(250):
            price = base_price + i * 0.1
            history.append({
                "close": price,
                "high": price + 1,
                "low": price - 1,
                "volume": 1000000,
            })
        result = compute_technical_context(125.0, history)
        assert "sma_50" in result
        assert "sma_200" in result
        assert "rsi_14" in result
        assert "high_52w" in result
        assert "low_52w" in result
        assert "trend_signals" in result

    def test_with_no_history(self):
        from ai.stock_analyzer import compute_technical_context
        result = compute_technical_context(100.0, None)
        assert result == {"current_price": 100.0}

    def test_with_short_history(self):
        from ai.stock_analyzer import compute_technical_context
        history = [{"close": 100, "high": 101, "low": 99, "volume": 1000}]
        result = compute_technical_context(100.0, history)
        assert "sma_50" not in result  # Not enough data


class TestStockAnalyzer:
    """Tests for StockAnalyzer.analyze_stock."""

    def test_analyze_without_ai(self):
        from ai.stock_analyzer import StockAnalyzer
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock(
            symbol="GOOG",
            position={"entry_price": 140, "current_price": 165, "quantity": 50},
            fundamentals={"pe_trailing": 25.0, "sector": "Technology"},
            technical_context={"sma_50": 155.0, "rsi_14": 60.0},
            use_ai=False,
        )
        assert result["symbol"] == "GOOG"
        assert result["position"]["entry_price"] == 140
        assert result["fundamentals"]["pe_trailing"] == 25.0
        assert result["ai_analysis"] is None

    def test_analyze_with_ai_disabled(self):
        from ai.stock_analyzer import StockAnalyzer
        # AI is not configured (no OPENAI_API_KEY), so ai_analysis should be None
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock(
            symbol="AAPL",
            position={"entry_price": 180, "current_price": 175},
            use_ai=True,
        )
        assert result["ai_analysis"] is None


# ===========================================================================
# data.portfolio_persistence tests
# ===========================================================================


class TestPortfolioPersistence:
    """Tests for SQLite persistence layer."""

    def test_save_and_get_snapshot(self, db_for_persistence):
        from data.portfolio_persistence import save_portfolio_snapshot, get_latest_snapshot

        row_id = save_portfolio_snapshot(
            total_equity=100000.0,
            cash=20000.0,
            positions=[{"symbol": "GOOG", "quantity": 50}],
            strategy_mix={"buy_and_hold": 0.6, "momentum": 0.4},
        )
        assert row_id > 0

        snap = get_latest_snapshot()
        assert snap is not None
        assert snap["total_equity"] == 100000.0
        assert snap["cash"] == 20000.0
        assert len(snap["positions"]) == 1
        assert snap["positions"][0]["symbol"] == "GOOG"
        assert snap["strategy_mix"]["buy_and_hold"] == 0.6

    def test_snapshot_history(self, db_for_persistence):
        from data.portfolio_persistence import save_portfolio_snapshot, get_snapshot_history

        save_portfolio_snapshot(100000, 20000, [])
        save_portfolio_snapshot(101000, 21000, [])
        save_portfolio_snapshot(102000, 22000, [])

        history = get_snapshot_history(limit=2)
        assert len(history) == 2
        assert history[0]["total_equity"] == 102000  # newest first

    def test_save_and_get_stock_analysis(self, db_for_persistence):
        from data.portfolio_persistence import save_stock_analysis, get_latest_stock_analysis

        row_id = save_stock_analysis(
            symbol="GOOG",
            fundamentals={"pe_trailing": 25.0},
            ai_analysis={"verdict": "HOLD", "summary": "Solid company"},
            verdict="HOLD",
        )
        assert row_id > 0

        analysis = get_latest_stock_analysis("GOOG")
        assert analysis is not None
        assert analysis["symbol"] == "GOOG"
        assert analysis["verdict"] == "HOLD"
        assert analysis["fundamentals"]["pe_trailing"] == 25.0

    def test_stock_analysis_ttl(self, db_for_persistence):
        from data.portfolio_persistence import get_latest_stock_analysis

        # With no analyses saved, should return None
        result = get_latest_stock_analysis("NONE")
        assert result is None

    def test_cache_fundamentals(self, db_for_persistence):
        from data.portfolio_persistence import cache_fundamentals, get_cached_fundamentals

        data = {"pe_trailing": 25.0, "sector": "Technology"}
        cache_fundamentals("GOOG", data)

        cached = get_cached_fundamentals("GOOG")
        assert cached is not None
        assert cached["pe_trailing"] == 25.0

    def test_cache_fundamentals_ttl(self, db_for_persistence):
        from data.portfolio_persistence import get_cached_fundamentals

        # Nothing cached for this symbol
        result = get_cached_fundamentals("NONE", ttl_seconds=86400)
        assert result is None

    def test_cache_fundamentals_replaces_old(self, db_for_persistence):
        from data.portfolio_persistence import cache_fundamentals, get_cached_fundamentals

        cache_fundamentals("GOOG", {"pe_trailing": 20.0})
        cache_fundamentals("GOOG", {"pe_trailing": 25.0})

        cached = get_cached_fundamentals("GOOG")
        assert cached["pe_trailing"] == 25.0

    def test_stock_analysis_history(self, db_for_persistence):
        from data.portfolio_persistence import save_stock_analysis, get_stock_analysis_history

        save_stock_analysis("GOOG", verdict="BUY")
        save_stock_analysis("GOOG", verdict="HOLD")
        save_stock_analysis("AAPL", verdict="SELL")

        history = get_stock_analysis_history("GOOG", limit=10)
        assert len(history) == 2
        assert history[0]["verdict"] == "HOLD"  # newest first


# ===========================================================================
# data.fundamentals tests
# ===========================================================================


class TestFundamentals:
    """Tests for the fundamentals data fetcher."""

    def test_fetch_fundamentals_with_mock(self):
        """Test fetch_fundamentals with a mocked yfinance response."""
        from data.fundamentals import fetch_fundamentals

        mock_info = {
            "longName": "Alphabet Inc.",
            "sector": "Technology",
            "industry": "Internet Content & Information",
            "marketCap": 2000000000000,
            "trailingPE": 25.0,
            "forwardPE": 22.0,
            "trailingEps": 6.50,
            "profitMargins": 0.25,
            "returnOnEquity": 0.30,
            "debtToEquity": 10.5,
            "dividendYield": None,
            "currentPrice": 165.0,
            "targetMeanPrice": 190.0,
            "recommendationKey": "buy",
        }

        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = fetch_fundamentals("GOOG")

        assert result["symbol"] == "GOOG"
        assert result["name"] == "Alphabet Inc."
        assert result["pe_trailing"] == 25.0
        assert result["sector"] == "Technology"
        assert result["current_price"] == 165.0

    def test_fetch_fundamentals_error_handling(self):
        """Test graceful error handling when yfinance fails."""
        from data.fundamentals import fetch_fundamentals

        with patch("yfinance.Ticker", side_effect=Exception("API error")):
            result = fetch_fundamentals("INVALID")

        assert "error" in result

    def test_get_fundamentals_without_cache(self):
        """Test get_fundamentals bypassing cache."""
        from data.fundamentals import get_fundamentals

        with patch("data.fundamentals.fetch_fundamentals") as mock_fetch:
            mock_fetch.return_value = {"symbol": "GOOG", "pe_trailing": 25.0}
            result = get_fundamentals("GOOG", use_cache=False)

        assert result["pe_trailing"] == 25.0
        mock_fetch.assert_called_once_with("GOOG")

    def test_sanitize_numeric_valid_values(self):
        """_sanitize_numeric passes through valid finite numbers."""
        from data.fundamentals import _sanitize_numeric

        assert _sanitize_numeric(10.5) == 10.5
        assert _sanitize_numeric(0) == 0.0
        assert _sanitize_numeric(-5.2) == -5.2
        assert _sanitize_numeric("42.5") == 42.5

    def test_sanitize_numeric_rejects_non_numeric(self):
        """_sanitize_numeric returns None for non-numeric placeholders."""
        from data.fundamentals import _sanitize_numeric

        assert _sanitize_numeric(None) is None
        assert _sanitize_numeric("?") is None
        assert _sanitize_numeric("N/A") is None
        assert _sanitize_numeric("") is None

    def test_sanitize_numeric_rejects_nan_and_infinity(self):
        """_sanitize_numeric returns None for NaN and Infinity."""
        from data.fundamentals import _sanitize_numeric

        assert _sanitize_numeric(float("nan")) is None
        assert _sanitize_numeric(float("inf")) is None
        assert _sanitize_numeric(float("-inf")) is None

    def test_fetch_fundamentals_sanitizes_placeholder_values(self):
        """fetch_fundamentals converts '?', NaN, Infinity in yfinance data to None."""
        from data.fundamentals import fetch_fundamentals

        mock_info = {
            "longName": "Alphabet Inc.",
            "sector": "Technology",
            "trailingPE": "?",
            "forwardPE": float("nan"),
            "marketCap": float("inf"),
            "trailingEps": 6.50,
            "profitMargins": "N/A",
            "currentPrice": 165.0,
            "recommendationKey": "buy",
        }

        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = fetch_fundamentals("GOOG")

        # Valid numbers preserved
        assert result["eps_trailing"] == 6.50
        assert result["current_price"] == 165.0
        # Invalid placeholders become None
        assert result["pe_trailing"] is None
        assert result["pe_forward"] is None
        assert result["market_cap"] is None
        assert result["profit_margin"] is None
        # String fields remain untouched
        assert result["name"] == "Alphabet Inc."
        assert result["sector"] == "Technology"
        assert result["recommendation_key"] == "buy"


# ===========================================================================
# Web API endpoint tests
# ===========================================================================


class TestPortfolioInsightsAPI:
    """Tests for /api/account/portfolio-insights."""

    def test_empty_portfolio(self, client):
        resp = client.get("/api/account/portfolio-insights")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["position_count"] == 0
        assert data["positions_enriched"] == []
        assert data["strategy_mix"] == {}

    def test_with_positions(self, client, services, sample_positions):
        for symbol, pos in sample_positions.items():
            services.update_position(symbol, pos)

        resp = client.get("/api/account/portfolio-insights?ai=false")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["position_count"] == 3
        assert len(data["positions_enriched"]) == 3
        assert data["total_value"] > 0
        assert len(data["strategy_mix"]) > 0

        # Check each position has strategy info
        for pe in data["positions_enriched"]:
            assert "deduced_strategy" in pe
            assert "strategy_confidence" in pe

    def test_ai_param_defaults_true(self, client, services, sample_positions):
        """Verify the ai parameter defaults to true (but AI is disabled in test)."""
        for symbol, pos in sample_positions.items():
            services.update_position(symbol, pos)

        resp = client.get("/api/account/portfolio-insights")
        data = resp.get_json()
        assert resp.status_code == 200
        # AI narrative should be None since OPENAI_API_KEY is not set
        assert data["ai_narrative"] is None


class TestStockDeepDiveAPI:
    """Tests for /api/account/stock-deep-dive/<symbol>."""

    def test_symbol_not_in_portfolio(self, client):
        resp = client.get("/api/account/stock-deep-dive/GOOG")
        data = resp.get_json()
        assert resp.status_code == 404
        assert "error" in data

    def test_deep_dive_with_position(self, client, services):
        services.update_position("GOOG", {
            "quantity": 50,
            "entry_price": 140.0,
            "current_price": 165.0,
            "market_value": 8250.0,
            "unrealized_pnl": 1250.0,
            "side": "LONG",
        })

        # Mock yfinance to avoid network calls
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "longName": "Alphabet Inc.",
            "sector": "Technology",
            "trailingPE": 25.0,
            "currentPrice": 165.0,
        }
        mock_df = MagicMock()
        mock_df.empty = True
        mock_ticker.history.return_value = mock_df

        with patch("yfinance.Ticker", return_value=mock_ticker):
            resp = client.get("/api/account/stock-deep-dive/GOOG?ai=false&cache=false")
            data = resp.get_json()

        assert resp.status_code == 200
        assert data["symbol"] == "GOOG"
        assert "position" in data
        assert "fundamentals" in data
        assert data["from_cache"] is False

    def test_case_insensitive_symbol(self, client, services):
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 180.0,
            "current_price": 175.0,
            "market_value": 17500.0,
            "side": "LONG",
        })

        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 175.0}
        mock_df = MagicMock()
        mock_df.empty = True
        mock_ticker.history.return_value = mock_df

        with patch("yfinance.Ticker", return_value=mock_ticker):
            resp = client.get("/api/account/stock-deep-dive/aapl?ai=false&cache=false")
            data = resp.get_json()

        assert resp.status_code == 200
        assert data["symbol"] == "AAPL"

    def test_cached_response_matches_fresh_schema(self, client, services):
        """Cached deep-dive response must have the same keys as a fresh one."""
        services.update_position("GOOG", {
            "quantity": 50,
            "entry_price": 140.0,
            "current_price": 165.0,
            "market_value": 8250.0,
            "unrealized_pnl": 1250.0,
            "side": "LONG",
        })

        cached_row = {
            "id": 1,
            "symbol": "GOOG",
            "analysis_date": "2026-04-17T12:00:00+00:00",
            "fundamentals": {"pe_trailing": 25.0},
            "technical": {"sma_50": 160.0, "rsi_14": 55.0},
            "ai_analysis": {"verdict": "HOLD", "summary": "looks ok"},
            "verdict": "HOLD",
        }

        with patch(
            "data.portfolio_persistence.get_latest_stock_analysis",
            return_value=cached_row,
        ):
            resp = client.get("/api/account/stock-deep-dive/GOOG")
            data = resp.get_json()

        assert resp.status_code == 200
        # Must match the fresh-response schema
        assert data["symbol"] == "GOOG"
        assert data["from_cache"] is True
        assert "position" in data
        assert data["position"]["entry_price"] == 140.0
        assert data["position"]["portfolio_weight"] == 1.0
        # Field renamed: "technical" → "technicals"
        assert "technicals" in data
        assert data["technicals"]["sma_50"] == 160.0
        # Field renamed: "analysis_date" → "timestamp"
        assert "timestamp" in data
        assert data["timestamp"] == "2026-04-17T12:00:00+00:00"
        assert data["fundamentals"]["pe_trailing"] == 25.0
        assert data["ai_analysis"]["verdict"] == "HOLD"
        # Internal DB fields should NOT leak
        assert "id" not in data
        assert "verdict" not in data
        assert "analysis_date" not in data
        assert "technical" not in data


class TestPortfolioSnapshotAPI:
    """Tests for /api/account/portfolio-snapshot and /api/account/portfolio-snapshots."""

    def test_save_snapshot(self, client, services):
        services.update_position("GOOG", {
            "quantity": 50,
            "entry_price": 140.0,
            "current_price": 165.0,
            "market_value": 8250.0,
        })

        with patch("data.portfolio_persistence.save_portfolio_snapshot", return_value=1) as mock_save:
            resp = client.post("/api/account/portfolio-snapshot")
            data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "saved"

    def test_list_snapshots_empty(self, client):
        with patch("data.portfolio_persistence.get_snapshot_history", return_value=[]):
            resp = client.get("/api/account/portfolio-snapshots")
            data = resp.get_json()

        assert resp.status_code == 200
        assert data["count"] == 0


class TestStockAnalysisHistoryAPI:
    """Tests for /api/account/stock-analysis-history/<symbol>."""

    def test_empty_history(self, client):
        with patch("data.portfolio_persistence.get_stock_analysis_history", return_value=[]):
            resp = client.get("/api/account/stock-analysis-history/GOOG")
            data = resp.get_json()

        assert resp.status_code == 200
        assert data["symbol"] == "GOOG"
        assert data["count"] == 0


class TestPortfolioAnalysisPage:
    """Tests for the portfolio analysis HTML page."""

    def test_page_loads(self, client):
        resp = client.get("/portfolio-analysis/")
        assert resp.status_code == 200
        assert b"Portfolio Analysis" in resp.data

    def test_page_shows_empty_state(self, client):
        resp = client.get("/portfolio-analysis/")
        assert resp.status_code == 200
        assert b"No open positions" in resp.data

    def test_page_shows_positions(self, client, services, sample_positions):
        for symbol, pos in sample_positions.items():
            services.update_position(symbol, pos)

        resp = client.get("/portfolio-analysis/")
        assert resp.status_code == 200
        assert b"GOOG" in resp.data
        assert b"SLV" in resp.data
        assert b"AAPL" in resp.data
        assert b"Deep Dive" in resp.data


class TestNavigationLink:
    """Test that the Analysis nav link is present."""

    def test_nav_link_exists(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Analysis" in resp.data
        assert b"portfolio-analysis" in resp.data


# ===========================================================================
# ai.prompts tests
# ===========================================================================


class TestNewPrompts:
    """Verify the new prompts exist and have correct placeholders."""

    def test_portfolio_strategy_analysis_prompt(self):
        from ai.prompts import Prompts
        assert hasattr(Prompts, "PORTFOLIO_STRATEGY_ANALYSIS")
        assert "{portfolio_json}" in Prompts.PORTFOLIO_STRATEGY_ANALYSIS

    def test_stock_deep_dive_prompt(self):
        from ai.prompts import Prompts
        assert hasattr(Prompts, "STOCK_DEEP_DIVE")
        assert "{symbol}" in Prompts.STOCK_DEEP_DIVE
        assert "{position_json}" in Prompts.STOCK_DEEP_DIVE
        assert "{fundamentals_json}" in Prompts.STOCK_DEEP_DIVE
        assert "{technical_json}" in Prompts.STOCK_DEEP_DIVE


# ===========================================================================
# Integration test: full pipeline without AI
# ===========================================================================


class TestFullPipelineNoAI:
    """End-to-end test of the portfolio analysis pipeline without AI."""

    def test_full_pipeline(self, client, services, sample_positions):
        # 1. Add positions
        for symbol, pos in sample_positions.items():
            services.update_position(symbol, pos)

        # 2. Get portfolio insights
        resp = client.get("/api/account/portfolio-insights?ai=false")
        insights = resp.get_json()
        assert resp.status_code == 200
        assert insights["position_count"] == 3
        assert len(insights["strategy_mix"]) > 0

        # 3. Verify strategy mix sums to ~1
        total_mix = sum(insights["strategy_mix"].values())
        assert abs(total_mix - 1.0) < 0.01

        # 4. Verify each position has been classified
        for pe in insights["positions_enriched"]:
            assert pe["deduced_strategy"] != ""
            assert 0 <= pe["strategy_confidence"] <= 1.0
