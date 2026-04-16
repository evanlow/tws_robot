"""Tests for the market overview feature.

Covers:
- MarketSnapshot model
- MarketOverviewService (with mocked yfinance)
- /api/market/* API endpoints
"""

import json
from datetime import datetime, date
from unittest.mock import patch, MagicMock

import pytest

from web import create_app
from data.models import Base, MarketSnapshot
from data.market_overview import (
    MarketOverviewService,
    _market_status,
    INDEX_DEFINITIONS,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def app():
    """Create Flask app with test configuration."""
    # Reset the module-level singleton so each test gets a fresh service
    import data.market_overview as mo
    mo._instance = None
    app = create_app({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def db():
    """In-memory SQLite database for testing."""
    from data.database import Database
    database = Database("sqlite:///:memory:")
    database.create_tables()
    yield database
    database.close()


@pytest.fixture
def market_service(db):
    """MarketOverviewService backed by in-memory DB."""
    return MarketOverviewService(database=db)


# ==============================================================================
# MarketSnapshot Model
# ==============================================================================


class TestMarketSnapshotModel:
    """Tests for the MarketSnapshot SQLAlchemy model."""

    def test_create_snapshot(self, db):
        with db.session_scope() as session:
            snap = MarketSnapshot(
                symbol="^GSPC",
                name="S&P 500",
                region="US",
                price=5842.0,
                change=23.41,
                change_pct=0.40,
                day_high=5860.0,
                day_low=5820.0,
                prev_close=5818.59,
                volume=3_500_000_000,
                timestamp=datetime.now(),
                market_date=date.today(),
            )
            session.add(snap)

        with db.session_scope() as session:
            rows = session.query(MarketSnapshot).all()
            assert len(rows) == 1
            assert rows[0].symbol == "^GSPC"
            assert rows[0].name == "S&P 500"
            assert rows[0].region == "US"
            assert rows[0].price == 5842.0

    def test_to_dict(self, db):
        now = datetime.now()
        today = date.today()
        with db.session_scope() as session:
            snap = MarketSnapshot(
                symbol="^VIX",
                name="VIX",
                region="US",
                price=14.82,
                change=-0.38,
                change_pct=-2.50,
                timestamp=now,
                market_date=today,
            )
            session.add(snap)
            session.flush()
            d = snap.to_dict()

        assert d["symbol"] == "^VIX"
        assert d["price"] == 14.82
        assert d["change"] == -0.38
        assert d["change_pct"] == -2.50
        assert d["market_date"] == today.isoformat()

    def test_multiple_snapshots_same_symbol(self, db):
        """Append-only: multiple rows for the same symbol is expected."""
        with db.session_scope() as session:
            for price in [5800.0, 5810.0, 5820.0]:
                session.add(MarketSnapshot(
                    symbol="^GSPC",
                    name="S&P 500",
                    region="US",
                    price=price,
                    timestamp=datetime.now(),
                ))

        with db.session_scope() as session:
            count = session.query(MarketSnapshot).filter_by(symbol="^GSPC").count()
            assert count == 3


# ==============================================================================
# MarketOverviewService
# ==============================================================================


class TestMarketOverviewService:
    """Tests for the service layer (yfinance mocked)."""

    def test_empty_overview(self, market_service):
        """No data yet → returns stub with empty index lists."""
        overview = market_service.get_overview()
        assert overview["snapshots"] == []
        assert len(overview["regions"]) == 3
        for region in overview["regions"]:
            assert region["indices"] == []

    def test_persist_and_load(self, market_service, db):
        """Manually persist snapshots, then verify get_overview loads them."""
        now = datetime.now()
        snapshots = [
            {
                "symbol": "^GSPC",
                "name": "S&P 500",
                "region": "US",
                "price": 5842.0,
                "change": 23.41,
                "change_pct": 0.40,
                "timestamp": now,
                "market_date": now.date(),
            },
            {
                "symbol": "^FTSE",
                "name": "FTSE 100",
                "region": "Europe",
                "price": 8354.0,
                "change": 41.20,
                "change_pct": 0.50,
                "timestamp": now,
                "market_date": now.date(),
            },
        ]
        market_service._persist_snapshots(snapshots)

        # Clear in-memory cache so it reads from DB
        market_service._cache = None
        market_service._cache_time = None

        overview = market_service.get_overview()
        assert len(overview["snapshots"]) == 2
        symbols = {s["symbol"] for s in overview["snapshots"]}
        assert "^GSPC" in symbols
        assert "^FTSE" in symbols

    def test_cache_hit(self, market_service):
        """After a refresh, subsequent calls serve from cache."""
        fake_snapshots = [
            {
                "symbol": "^DJI",
                "name": "Dow Jones",
                "region": "US",
                "price": 43000.0,
                "change": -85.0,
                "change_pct": -0.20,
                "timestamp": datetime.now(),
                "market_date": date.today(),
            },
        ]
        market_service._persist_snapshots(fake_snapshots)
        # Warm the cache
        market_service._cache = market_service._build_overview(fake_snapshots)
        market_service._cache_time = datetime.now()

        overview = market_service.get_overview()
        assert len(overview["snapshots"]) == 1
        assert overview["snapshots"][0]["symbol"] == "^DJI"

    def test_is_stale_initially(self, market_service):
        assert market_service.is_stale() is True

    def test_is_stale_after_cache(self, market_service):
        market_service._cache = {"snapshots": []}
        market_service._cache_time = datetime.now()
        assert market_service.is_stale() is False

    @patch("data.market_overview._fetch_from_yfinance")
    @patch("data.market_overview._fetch_sparkline_from_yfinance")
    def test_refresh_mocked(self, mock_sparkline, mock_fetch, market_service):
        """Test refresh() with mocked yfinance calls."""
        mock_fetch.return_value = [
            {
                "symbol": "^GSPC",
                "name": "S&P 500",
                "region": "US",
                "price": 5900.0,
                "change": 58.0,
                "change_pct": 0.99,
                "day_high": 5920.0,
                "day_low": 5850.0,
                "prev_close": 5842.0,
                "volume": None,
                "timestamp": datetime.now(),
                "market_date": date.today(),
            },
        ]
        mock_sparkline.return_value = {
            "^GSPC": [5800.0, 5810.0, 5830.0, 5842.0, 5900.0],
        }

        overview = market_service.refresh()
        assert len(overview["snapshots"]) == 1
        assert overview["snapshots"][0]["price"] == 5900.0
        # Sparkline should be attached
        us_region = next(r for r in overview["regions"] if r["name"] == "US")
        assert len(us_region["indices"]) == 1
        assert len(us_region["indices"][0]["sparkline"]) == 5


# ==============================================================================
# Market Status Helper
# ==============================================================================


class TestMarketStatus:
    """Test the heuristic market open/closed logic."""

    def test_returns_dict(self):
        status = _market_status()
        assert "US" in status
        assert "Europe" in status
        assert "Asia" in status
        for v in status.values():
            assert v in ("open", "closed")


# ==============================================================================
# API Endpoints
# ==============================================================================


class TestMarketAPI:
    """Tests for /api/market/* endpoints."""

    def test_overview_endpoint(self, client):
        resp = client.get("/api/market/overview")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "regions" in data
        assert "market_status" in data
        assert len(data["regions"]) == 3

    @patch("data.market_overview._fetch_from_yfinance")
    @patch("data.market_overview._fetch_sparkline_from_yfinance")
    def test_refresh_endpoint(self, mock_sparkline, mock_fetch, client):
        mock_fetch.return_value = [
            {
                "symbol": "^GSPC",
                "name": "S&P 500",
                "region": "US",
                "price": 5900.0,
                "change": 58.0,
                "change_pct": 0.99,
                "timestamp": datetime.now(),
                "market_date": date.today(),
            },
        ]
        mock_sparkline.return_value = {}

        resp = client.post("/api/market/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "regions" in data
        assert "market_status" in data
        # Should contain at least the snapshot we mocked
        assert len(data["snapshots"]) >= 1
        symbols = [s["symbol"] for s in data["snapshots"]]
        assert "^GSPC" in symbols

    def test_overview_has_all_regions(self, client):
        resp = client.get("/api/market/overview")
        data = resp.get_json()
        region_names = [r["name"] for r in data["regions"]]
        assert region_names == ["US", "Europe", "Asia"]


# ==============================================================================
# Dashboard page smoke test (Market tab renders)
# ==============================================================================


class TestDashboardMarketTab:
    """Verify the dashboard page still renders with the new market section."""

    def test_dashboard_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Global Markets" in resp.data
        assert b"Refresh" in resp.data

    def test_dashboard_contains_region_labels(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"US Markets" in resp.data
        assert b"European Markets" in resp.data
        assert b"Asian Markets" in resp.data
