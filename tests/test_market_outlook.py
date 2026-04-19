"""Tests for the Market Outlook feature.

Covers:
- compute_market_pulse()
- build_outlook_context()
- MarketOutlookGenerator (with mocked AI client)
- /api/market/outlook API endpoint
- Dashboard renders the outlook section
"""

import json
import time
from datetime import datetime, date
from unittest.mock import patch, MagicMock

import pytest

from web import create_app
from ai.market_outlook import (
    MarketOutlookGenerator,
    compute_market_pulse,
    build_outlook_context,
    _parse_outlook_json,
    get_market_outlook_generator,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def app():
    """Create Flask app with test configuration."""
    # Reset singletons
    import ai.market_outlook as mo
    mo._instance = None
    import data.market_overview as mkt
    mkt._instance = None
    app = create_app({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def sample_snapshots():
    """Representative market snapshot data."""
    now = datetime.now()
    return [
        {
            "symbol": "^GSPC",
            "name": "S&P 500",
            "region": "US",
            "price": 5842.0,
            "change": 23.41,
            "change_pct": 0.40,
            "prev_close": 5818.59,
            "timestamp": now,
            "market_date": now.date(),
        },
        {
            "symbol": "^DJI",
            "name": "Dow Jones",
            "region": "US",
            "price": 43100.0,
            "change": 150.0,
            "change_pct": 0.35,
            "prev_close": 42950.0,
            "timestamp": now,
            "market_date": now.date(),
        },
        {
            "symbol": "^IXIC",
            "name": "Nasdaq",
            "region": "US",
            "price": 18500.0,
            "change": 120.0,
            "change_pct": 0.65,
            "prev_close": 18380.0,
            "timestamp": now,
            "market_date": now.date(),
        },
        {
            "symbol": "^VIX",
            "name": "VIX",
            "region": "US",
            "price": 15.2,
            "change": -0.5,
            "change_pct": -3.18,
            "prev_close": 15.7,
            "timestamp": now,
            "market_date": now.date(),
        },
        {
            "symbol": "^FTSE",
            "name": "FTSE 100",
            "region": "Europe",
            "price": 8354.0,
            "change": -42.0,
            "change_pct": -0.50,
            "prev_close": 8396.0,
            "timestamp": now,
            "market_date": now.date(),
        },
        {
            "symbol": "^N225",
            "name": "Nikkei 225",
            "region": "Asia",
            "price": 38900.0,
            "change": 310.0,
            "change_pct": 0.80,
            "prev_close": 38590.0,
            "timestamp": now,
            "market_date": now.date(),
        },
    ]


@pytest.fixture
def sample_positions():
    """Representative portfolio positions."""
    return {
        "AAPL": {
            "quantity": 100,
            "entry_price": 170.0,
            "current_price": 185.0,
            "market_value": 18500.0,
            "unrealized_pnl": 1500.0,
        },
        "GOOGL": {
            "quantity": 50,
            "entry_price": 140.0,
            "current_price": 155.0,
            "market_value": 7750.0,
            "unrealized_pnl": 750.0,
        },
    }


@pytest.fixture
def sample_market_overview(sample_snapshots):
    """Market overview dict as returned by MarketOverviewService."""
    return {
        "regions": [],
        "market_status": {"US": "open", "Europe": "closed", "Asia": "closed"},
        "last_updated": datetime.now().isoformat(),
        "snapshots": sample_snapshots,
    }


# ==============================================================================
# compute_market_pulse
# ==============================================================================


class TestComputeMarketPulse:
    """Tests for the data-only market pulse computation."""

    def test_empty_snapshots(self):
        pulse = compute_market_pulse([])
        assert pulse["overall_sentiment"] == 0.0
        assert pulse["sentiment_label"] == "neutral"
        assert pulse["vix"] is None

    def test_bullish_market(self, sample_snapshots):
        pulse = compute_market_pulse(sample_snapshots)
        assert pulse["overall_sentiment"] > 0
        assert pulse["sentiment_label"] in ("bullish", "slightly bullish")
        assert "US" in pulse["regions"]
        assert pulse["vix"] is not None
        assert pulse["vix"]["price"] == 15.2

    def test_bearish_market(self):
        snapshots = [
            {"symbol": "^GSPC", "name": "S&P 500", "region": "US",
             "price": 5000.0, "change_pct": -2.5},
            {"symbol": "^DJI", "name": "Dow", "region": "US",
             "price": 40000.0, "change_pct": -2.0},
        ]
        pulse = compute_market_pulse(snapshots)
        assert pulse["overall_sentiment"] < 0
        assert pulse["sentiment_label"] in ("bearish", "slightly bearish")

    def test_vix_levels(self):
        # Low VIX
        snapshots = [
            {"symbol": "^VIX", "name": "VIX", "region": "US",
             "price": 12.0, "change_pct": -1.0},
        ]
        pulse = compute_market_pulse(snapshots)
        assert pulse["vix"]["level"] == "low"

        # Elevated VIX
        snapshots[0]["price"] = 30.0
        pulse = compute_market_pulse(snapshots)
        assert pulse["vix"]["level"] == "elevated"

    def test_regions_populated(self, sample_snapshots):
        pulse = compute_market_pulse(sample_snapshots)
        assert "US" in pulse["regions"]
        assert "Europe" in pulse["regions"]
        assert "Asia" in pulse["regions"]
        assert pulse["regions"]["US"]["direction"] == "up"
        assert pulse["regions"]["Europe"]["direction"] == "down"
        assert pulse["regions"]["Asia"]["direction"] == "up"

    def test_summary_text_not_empty(self, sample_snapshots):
        pulse = compute_market_pulse(sample_snapshots)
        assert len(pulse["summary_text"]) > 0
        assert "US" in pulse["summary_text"]


# ==============================================================================
# build_outlook_context
# ==============================================================================


class TestBuildOutlookContext:
    """Tests for the LLM context builder."""

    def test_basic_context(self, sample_snapshots):
        pulse = compute_market_pulse(sample_snapshots)
        ctx_str = build_outlook_context(
            market_pulse=pulse,
            snapshots=sample_snapshots,
        )
        ctx = json.loads(ctx_str)
        assert "market_pulse" in ctx
        assert "index_data" in ctx
        assert len(ctx["index_data"]) == len(sample_snapshots)
        assert ctx["portfolio"] is None

    def test_with_portfolio(self, sample_snapshots, sample_positions):
        pulse = compute_market_pulse(sample_snapshots)
        ctx_str = build_outlook_context(
            market_pulse=pulse,
            snapshots=sample_snapshots,
            positions=sample_positions,
            strategy_mix={"momentum": 0.6, "value": 0.4},
        )
        ctx = json.loads(ctx_str)
        assert ctx["portfolio"] is not None
        assert ctx["portfolio"]["position_count"] == 2
        assert "AAPL" in ctx["portfolio"]["symbols"]
        assert ctx["portfolio"]["strategy_mix"]["momentum"] == 0.6

    def test_account_level_fallback_when_positions_empty(self, sample_snapshots):
        """When positions are empty but account_summary exists, the portfolio
        summary should contain account-level data instead of being None."""
        pulse = compute_market_pulse(sample_snapshots)
        account_summary = {
            "position_count": 7,
            "equity": 60234.38,
            "unrealized_pnl": 15697.39,
            "daily_pnl": 0.0,
        }
        ctx_str = build_outlook_context(
            market_pulse=pulse,
            snapshots=sample_snapshots,
            positions=None,
            account_summary=account_summary,
        )
        ctx = json.loads(ctx_str)
        portfolio = ctx["portfolio"]
        assert portfolio is not None
        assert portfolio["position_count"] == 7
        assert portfolio["equity"] == 60234.38
        assert portfolio["unrealized_pnl"] == 15697.39
        assert portfolio["daily_pnl"] == 0.0
        assert "note" in portfolio


# ==============================================================================
# _parse_outlook_json
# ==============================================================================


class TestParseOutlookJson:
    """Tests for the JSON parser helper."""

    def test_valid_json(self):
        raw = '{"session_recap": "Markets rose", "portfolio_outlook": "OK", "recommendations": ["Buy"]}'
        result = _parse_outlook_json(raw)
        assert result is not None
        assert result["session_recap"] == "Markets rose"

    def test_json_with_code_fences(self):
        raw = '```json\n{"session_recap": "test", "portfolio_outlook": "ok", "recommendations": []}\n```'
        result = _parse_outlook_json(raw)
        assert result is not None
        assert result["session_recap"] == "test"

    def test_invalid_json(self):
        result = _parse_outlook_json("not json at all")
        assert result is None

    def test_empty_string(self):
        assert _parse_outlook_json("") is None

    def test_none_input(self):
        assert _parse_outlook_json(None) is None


# ==============================================================================
# MarketOutlookGenerator
# ==============================================================================


class TestMarketOutlookGenerator:
    """Tests for the generator class."""

    def test_data_only_outlook(self, sample_snapshots, sample_market_overview):
        """When AI is disabled, returns data-only pulse without AI content."""
        generator = MarketOutlookGenerator()
        with patch("ai.client.get_client", return_value=None):
            outlook = generator.get_outlook(
                market_overview=sample_market_overview,
            )
        assert outlook["market_pulse"]["overall_sentiment"] > 0
        assert outlook["ai_session_recap"] is None
        assert outlook["ai_portfolio_outlook"] is None
        assert outlook["ai_recommendations"] == []

    def test_with_ai(self, sample_market_overview, sample_positions):
        """When AI is available, returns enriched outlook."""
        generator = MarketOutlookGenerator()
        mock_client = MagicMock()
        mock_client.chat.return_value = json.dumps({
            "session_recap": "US markets rose modestly.",
            "portfolio_outlook": "Your tech-heavy portfolio benefits.",
            "recommendations": ["Consider taking profits", "Watch VIX levels"],
        })

        with patch("ai.client.get_client", return_value=mock_client):
            outlook = generator.get_outlook(
                market_overview=sample_market_overview,
                positions=sample_positions,
                strategy_mix={"momentum": 0.7},
            )

        assert outlook["ai_session_recap"] == "US markets rose modestly."
        assert outlook["ai_portfolio_outlook"] == "Your tech-heavy portfolio benefits."
        assert len(outlook["ai_recommendations"]) == 2
        assert outlook["from_cache"] is False

    def test_caching(self, sample_market_overview):
        """Second call returns cached result."""
        generator = MarketOutlookGenerator(cache_ttl=300)
        with patch("ai.client.get_client", return_value=None):
            first = generator.get_outlook(market_overview=sample_market_overview)
            second = generator.get_outlook(market_overview=sample_market_overview)
        assert second["from_cache"] is True

    def test_force_refresh_bypasses_cache(self, sample_market_overview):
        """force_refresh=True regenerates even if cache is fresh."""
        generator = MarketOutlookGenerator(cache_ttl=300)
        with patch("ai.client.get_client", return_value=None):
            first = generator.get_outlook(market_overview=sample_market_overview)
            second = generator.get_outlook(
                market_overview=sample_market_overview,
                force_refresh=True,
            )
        assert second["from_cache"] is False

    def test_cache_expires(self, sample_market_overview):
        """After TTL expires, is_stale returns True."""
        generator = MarketOutlookGenerator(cache_ttl=60)
        with patch("ai.client.get_client", return_value=None):
            generator.get_outlook(market_overview=sample_market_overview)
            assert generator.is_stale() is False

            # Simulate time advancing past the TTL
            with patch("time.time", return_value=time.time() + 61):
                assert generator.is_stale() is True

    def test_invalidate(self, sample_market_overview):
        """invalidate() clears cache."""
        generator = MarketOutlookGenerator()
        with patch("ai.client.get_client", return_value=None):
            generator.get_outlook(market_overview=sample_market_overview)
            assert generator.is_stale() is False
            generator.invalidate()
            assert generator.is_stale() is True

    def test_cache_invalidated_when_positions_arrive(
        self, sample_market_overview, sample_positions,
    ):
        """Cached outlook generated without positions is not served once
        positions become available."""
        generator = MarketOutlookGenerator(cache_ttl=300)
        with patch("ai.client.get_client", return_value=None):
            # First call — no positions
            first = generator.get_outlook(
                market_overview=sample_market_overview,
                positions=None,
            )
            assert first["from_cache"] is False

            # Second call — same params → still cached
            second = generator.get_outlook(
                market_overview=sample_market_overview,
                positions=None,
            )
            assert second["from_cache"] is True

            # Third call — positions now available → cache should be
            # invalidated, resulting in a freshly generated result.
            third = generator.get_outlook(
                market_overview=sample_market_overview,
                positions=sample_positions,
            )
            assert third["from_cache"] is False

    def test_try_get_cached_returns_none_when_positions_arrive(
        self, sample_market_overview, sample_positions,
    ):
        """try_get_cached returns None (does not serve stale cache) once
        positions are available but cached outlook was generated without."""
        generator = MarketOutlookGenerator(cache_ttl=300)
        with patch("ai.client.get_client", return_value=None):
            generator.get_outlook(
                market_overview=sample_market_overview,
                positions=None,
            )

            # Cache is fresh — returns cached result when no positions passed
            assert generator.try_get_cached() is not None

            # Positions now available — try_get_cached should invalidate and
            # return None so the caller gathers full context and regenerates.
            assert generator.try_get_cached(positions=sample_positions) is None

            # Cache was cleared, so is_stale should be True
            assert generator.is_stale() is True

    def test_ai_failure_graceful(self, sample_market_overview):
        """AI failure still returns data-only pulse."""
        generator = MarketOutlookGenerator()
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("API error")

        with patch("ai.client.get_client", return_value=mock_client):
            outlook = generator.get_outlook(
                market_overview=sample_market_overview,
            )
        assert outlook["market_pulse"] is not None
        assert outlook["ai_session_recap"] is None

    def test_empty_market_data(self):
        """With no market data, returns neutral pulse."""
        generator = MarketOutlookGenerator()
        with patch("ai.client.get_client", return_value=None):
            outlook = generator.get_outlook(market_overview=None)
        assert outlook["market_pulse"]["sentiment_label"] == "neutral"

    def test_empty_snapshots_short_ttl(self):
        """When snapshots are empty, cache uses shorter TTL so data refreshes sooner."""
        generator = MarketOutlookGenerator(cache_ttl=900)
        empty_overview = {"snapshots": [], "regions": [], "market_status": {}}
        with patch("ai.client.get_client", return_value=None):
            generator.get_outlook(market_overview=empty_overview)
            assert generator.is_stale() is False
            # After short TTL (30s) the empty-data cache should be stale,
            # even though the normal TTL is 900s
            with patch("time.time", return_value=time.time() + 31):
                assert generator.is_stale() is True

    def test_concurrent_generation_guard(self, sample_market_overview):
        """Only one thread generates at a time; others wait for the result."""
        import threading
        generator = MarketOutlookGenerator(cache_ttl=300)
        results = []
        call_count = {"n": 0}

        original_generate = generator._generate

        def slow_generate(**kwargs):
            call_count["n"] += 1
            time.sleep(0.01)
            return original_generate(**kwargs)

        generator._generate = slow_generate

        def worker():
            with patch("ai.client.get_client", return_value=None):
                r = generator.get_outlook(market_overview=sample_market_overview)
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 3
        # Only one thread should have actually called _generate
        assert call_count["n"] == 1

    def test_singleton(self):
        """Module-level singleton works correctly."""
        import ai.market_outlook as mo
        mo._instance = None
        gen1 = get_market_outlook_generator()
        gen2 = get_market_outlook_generator()
        assert gen1 is gen2


# ==============================================================================
# API Endpoint
# ==============================================================================


class TestOutlookAPI:
    """Tests for /api/market/outlook endpoint."""

    def test_outlook_endpoint(self, client):
        resp = client.get("/api/market/outlook")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "market_pulse" in data
        assert "ai_session_recap" in data
        assert "ai_portfolio_outlook" in data
        assert "ai_recommendations" in data
        assert "generated_at" in data

    def test_outlook_with_refresh(self, client):
        resp = client.get("/api/market/outlook?refresh=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "market_pulse" in data

    def test_outlook_market_pulse_structure(self, client):
        resp = client.get("/api/market/outlook")
        data = resp.get_json()
        pulse = data["market_pulse"]
        assert "overall_sentiment" in pulse
        assert "sentiment_label" in pulse
        assert "regions" in pulse
        assert "summary_text" in pulse


# ==============================================================================
# Dashboard renders the outlook section
# ==============================================================================


class TestDashboardOutlookSection:
    """Verify the dashboard page renders with the Market Outlook section."""

    def test_dashboard_has_outlook_section(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Market Outlook" in resp.data
        assert b"marketOutlookSection" in resp.data

    def test_dashboard_has_pulse_bar(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"marketPulseBar" in resp.data

    def test_dashboard_has_outlook_cards(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"outlookSessionRecap" in resp.data
        assert b"outlookPortfolio" in resp.data
        assert b"outlookRecommendations" in resp.data
