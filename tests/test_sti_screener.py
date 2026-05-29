"""Tests for the Singapore STI Screener feature.

Covers:
- Constituent CSV loading and SGX ticker handling
- STIScreenerService: caching, failure handling, summary building
- display_symbol field in rows
- API endpoint shape and filtering
- Page route loads
- .SI ticker support in single-stock analysis routes
"""

import csv
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from web import create_app


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def app(monkeypatch):
    """Create Flask test app."""
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


# ==============================================================================
# Sample data helpers
# ==============================================================================


def _make_bars(count=60, base_price=10.0, variance=0.5):
    """Generate synthetic OHLCV bars for SGX-priced stocks."""
    import random
    random.seed(42)
    bars = []
    price = base_price
    for i in range(count):
        change = random.uniform(-variance, variance)
        price = max(price + change, 0.01)
        bars.append({
            "timestamp": f"2024-01-{(i % 28) + 1:02d}",
            "open": round(price, 3),
            "high": round(price + random.uniform(0, 0.5), 3),
            "low": round(price - random.uniform(0, 0.5), 3),
            "close": round(price + random.uniform(-0.3, 0.3), 3),
            "volume": 1_000_000,
        })
    return bars


def _minimal_sti_csv(rows):
    """Build a CSV string from a list of dicts."""
    if not rows:
        return "symbol,display_symbol,security,sector,sub_industry\n"
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["symbol", "display_symbol", "security", "sector", "sub_industry"])
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


# ==============================================================================
# Unit tests: STI constituent CSV loading
# ==============================================================================


class TestSTIConstituentLoading:
    """Tests for loading the STI constituents CSV."""

    def _make_service(self):
        from web.sti_screener_service import STIScreenerService
        return STIScreenerService()

    def test_load_real_sti_csv(self):
        """The bundled STI CSV should be loadable and have expected columns."""
        svc = self._make_service()
        rows = svc._load_constituents()
        assert len(rows) >= 10, "Expected at least 10 STI constituents"
        for row in rows[:5]:
            assert "symbol" in row
            assert "display_symbol" in row
            assert "security" in row
            assert "sector" in row

    def test_sti_csv_symbols_have_si_suffix(self):
        """All symbols in the STI CSV should have the .SI suffix."""
        svc = self._make_service()
        rows = svc._load_constituents()
        for row in rows:
            assert row["symbol"].endswith(".SI"), (
                f"Symbol {row['symbol']} should end with .SI"
            )

    def test_sti_csv_display_symbols_without_si(self):
        """display_symbol should not have the .SI suffix."""
        svc = self._make_service()
        rows = svc._load_constituents()
        for row in rows:
            assert not row["display_symbol"].endswith(".SI"), (
                f"display_symbol {row['display_symbol']} should not end with .SI"
            )

    def test_known_constituents_present(self):
        """Key STI banks should appear in the constituent list."""
        svc = self._make_service()
        rows = svc._load_constituents()
        symbols = {r["symbol"] for r in rows}
        for expected in ("D05.SI", "O39.SI", "U11.SI"):
            assert expected in symbols, f"{expected} should be in STI constituents"

    def test_load_constituents_missing_file(self, tmp_path, monkeypatch):
        """Missing constituents file returns empty list rather than raising."""
        import web.sti_screener_service as mod
        monkeypatch.setattr(mod, "_CONSTITUENTS_PATH", tmp_path / "nonexistent.csv")
        svc = self._make_service()
        rows = svc._load_constituents()
        assert rows == []

    def test_load_constituents_custom_csv(self, tmp_path, monkeypatch):
        """Service correctly parses a custom CSV with display_symbol column."""
        import web.sti_screener_service as mod

        csv_content = _minimal_sti_csv([
            {"symbol": "D05.SI", "display_symbol": "D05", "security": "DBS Group Holdings",
             "sector": "Financials", "sub_industry": "Banks"},
            {"symbol": "Z74.SI", "display_symbol": "Z74", "security": "Singtel",
             "sector": "Communication Services", "sub_industry": "Telecommunications"},
        ])
        csv_file = tmp_path / "sti_constituents.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        monkeypatch.setattr(mod, "_CONSTITUENTS_PATH", csv_file)

        svc = self._make_service()
        rows = svc._load_constituents()
        assert len(rows) == 2
        assert rows[0]["symbol"] == "D05.SI"
        assert rows[0]["display_symbol"] == "D05"
        assert rows[0]["security"] == "DBS Group Holdings"
        assert rows[1]["symbol"] == "Z74.SI"


# ==============================================================================
# Unit tests: SGX / yfinance ticker handling
# ==============================================================================


class TestSGXTickerHandling:
    """Tests for .SI ticker handling in the STI screener."""

    def test_display_symbol_stripped_from_si(self):
        """_sti_insufficient_data_row uses display_symbol from constituent."""
        from web.sti_screener_service import _sti_insufficient_data_row
        row = _sti_insufficient_data_row({
            "symbol": "D05.SI",
            "display_symbol": "D05",
            "security": "DBS Group Holdings",
            "sector": "Financials",
            "sub_industry": "Banks",
        })
        assert row["symbol"] == "D05.SI"
        assert row["display_symbol"] == "D05"

    def test_display_symbol_fallback_strips_si(self):
        """When display_symbol is missing, it is derived by stripping .SI."""
        from web.sti_screener_service import _sti_insufficient_data_row
        row = _sti_insufficient_data_row({
            "symbol": "O39.SI",
            "security": "OCBC Bank",
            "sector": "Financials",
        })
        assert row["symbol"] == "O39.SI"
        assert row["display_symbol"] == "O39"

    def test_scan_ticker_row_has_display_symbol(self):
        """_scan_ticker should include display_symbol in the row."""
        from web.sti_screener_service import STIScreenerService
        svc = STIScreenerService()
        constituent = {
            "symbol": "D05.SI",
            "display_symbol": "D05",
            "security": "DBS Group Holdings",
            "sector": "Financials",
            "sub_industry": "Banks",
        }
        bars = _make_bars(60, 30.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert row["symbol"] == "D05.SI"
        assert row["display_symbol"] == "D05"

    def test_si_ticker_matches_api_ticker_regex(self):
        """SGX .SI tickers should pass the API-level ticker regex."""
        import re
        _TICKER_RE = re.compile(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$")
        for ticker in ("D05.SI", "O39.SI", "A17U.SI", "ME8U.SI", "C38U.SI", "BUOU.SI"):
            assert _TICKER_RE.match(ticker), f"{ticker} should match the ticker regex"

    def test_si_ticker_uppercase_preserved(self):
        """Uppercase .SI tickers should remain unchanged after .upper()."""
        for ticker in ("D05.SI", "Z74.SI", "A17U.SI"):
            assert ticker.upper() == ticker


# ==============================================================================
# Unit tests: STIScreenerService
# ==============================================================================


class TestSTIScreenerService:
    """Tests for web.sti_screener_service.STIScreenerService."""

    def _make_service(self):
        from web.sti_screener_service import STIScreenerService
        return STIScreenerService()

    def test_scan_ticker_returns_row_shape(self):
        """_scan_ticker should always return a dict with required keys."""
        svc = self._make_service()
        constituent = {
            "symbol": "D05.SI",
            "display_symbol": "D05",
            "security": "DBS Group Holdings",
            "sector": "Financials",
            "sub_industry": "Banks",
        }
        bars = _make_bars(60, 30.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        required_keys = [
            "symbol", "display_symbol", "company", "sector", "current_price",
            "range_52w_position_percentile", "bollinger_percent_b",
            "bollinger_status", "status_label", "status_rank",
            "quality_score", "quality_label", "quality_reasons", "quality_warnings",
            "last_updated",
        ]
        for key in required_keys:
            assert key in row, f"Missing key: {key}"

    def test_scan_ticker_failure_returns_insufficient_data(self):
        """If price fetch raises, the row should reflect insufficient_data."""
        svc = self._make_service()
        constituent = {
            "symbol": "BADFETCH.SI",
            "display_symbol": "BADFETCH",
            "security": "Bad Co",
            "sector": "X",
            "sub_industry": "",
        }
        with patch("data.fundamentals.fetch_price_history", side_effect=RuntimeError("timeout")):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert row["bollinger_status"] == "insufficient_data"
        assert row["current_price"] is None
        assert row["symbol"] == "BADFETCH.SI"
        assert row["display_symbol"] == "BADFETCH"

    def test_scan_ticker_empty_bars_returns_insufficient_data(self):
        """Empty bar list → insufficient_data row."""
        svc = self._make_service()
        constituent = {
            "symbol": "EMPTY.SI",
            "display_symbol": "EMPTY",
            "security": "Empty Co",
            "sector": "X",
            "sub_industry": "",
        }
        with patch("data.fundamentals.fetch_price_history", return_value=[]):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert row["bollinger_status"] == "insufficient_data"

    def test_scan_ticker_missing_fundamentals_is_graceful(self):
        """Fundamentals failure does not break the scan; quality shows Insufficient Data."""
        svc = self._make_service()
        constituent = {
            "symbol": "D05.SI",
            "display_symbol": "D05",
            "security": "DBS Group Holdings",
            "sector": "Financials",
            "sub_industry": "Banks",
        }
        bars = _make_bars(60, 30.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", side_effect=RuntimeError("no data")):
                row = svc._scan_ticker(constituent)
        # Price data should be present even if fundamentals failed
        assert row["current_price"] is not None
        assert row["quality_label"] == "Insufficient Data"

    def test_get_screener_data_caching(self):
        """Second call within TTL should return cached result without re-scanning."""
        svc = self._make_service()
        scan_calls = [0]

        def counting_scan():
            scan_calls[0] += 1
            return {"as_of": "x", "source": "x", "count": 0, "summary": {}, "rows": []}

        svc._scan = counting_scan
        svc.get_screener_data(refresh=False)
        svc.get_screener_data(refresh=False)
        assert scan_calls[0] == 1, "Second call should have used cache"

    def test_get_screener_data_refresh_bypass_cache(self):
        """Passing refresh=True should always re-scan."""
        svc = self._make_service()
        scan_calls = [0]

        def counting_scan():
            scan_calls[0] += 1
            return {"as_of": "x", "source": "x", "count": 0, "summary": {}, "rows": []}

        svc._scan = counting_scan
        svc.get_screener_data(refresh=True)
        svc.get_screener_data(refresh=True)
        assert scan_calls[0] == 2

    def test_invalidate_cache(self):
        """invalidate_cache should force a re-scan on next call."""
        svc = self._make_service()
        scan_calls = [0]

        def counting_scan():
            scan_calls[0] += 1
            return {"as_of": "x", "source": "x", "count": 0, "summary": {}, "rows": []}

        svc._scan = counting_scan
        svc.get_screener_data(refresh=False)
        svc.invalidate_cache()
        svc.get_screener_data(refresh=False)
        assert scan_calls[0] == 2

    def test_scan_multiple_tickers_concurrently(self):
        """Multiple SGX tickers are scanned concurrently; all appear in result."""
        svc = self._make_service()
        constituents = [
            {
                "symbol": f"T{i:02d}.SI",
                "display_symbol": f"T{i:02d}",
                "security": f"Corp {i}",
                "sector": "Financials",
                "sub_industry": "Banks",
            }
            for i in range(10)
        ]
        bars = _make_bars(60, 10.0)

        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("data.fundamentals.fetch_price_history", return_value=bars):
                with patch("data.fundamentals.get_fundamentals", return_value={}):
                    result = svc._scan()

        assert result["count"] == 10
        symbols_in_result = {r["symbol"] for r in result["rows"]}
        for c in constituents:
            assert c["symbol"] in symbols_in_result

    def test_scan_isolates_failures(self):
        """A failing ticker does not stop the scan; others return data."""
        svc = self._make_service()
        constituents = [
            {"symbol": "D05.SI", "display_symbol": "D05", "security": "DBS", "sector": "Financials", "sub_industry": ""},
            {"symbol": "FAIL.SI", "display_symbol": "FAIL", "security": "Bad Corp", "sector": "Financials", "sub_industry": ""},
        ]
        bars = _make_bars(60, 30.0)

        def side_effect(symbol, **kwargs):
            if symbol == "FAIL.SI":
                raise RuntimeError("yfinance timeout")
            return bars

        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("data.fundamentals.fetch_price_history", side_effect=side_effect):
                with patch("data.fundamentals.get_fundamentals", return_value={}):
                    result = svc._scan()

        assert result["count"] == 2
        fail_row = next(r for r in result["rows"] if r["symbol"] == "FAIL.SI")
        good_row = next(r for r in result["rows"] if r["symbol"] == "D05.SI")
        assert fail_row["bollinger_status"] == "insufficient_data"
        assert good_row["current_price"] is not None

    def test_scan_result_has_display_symbol_in_all_rows(self):
        """Every row in the scan result should have a display_symbol field."""
        svc = self._make_service()
        constituents = [
            {"symbol": "D05.SI", "display_symbol": "D05", "security": "DBS", "sector": "Financials", "sub_industry": ""},
            {"symbol": "O39.SI", "display_symbol": "O39", "security": "OCBC", "sector": "Financials", "sub_industry": ""},
        ]
        bars = _make_bars(60, 30.0)
        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("data.fundamentals.fetch_price_history", return_value=bars):
                with patch("data.fundamentals.get_fundamentals", return_value={}):
                    result = svc._scan()

        for row in result["rows"]:
            assert "display_symbol" in row
            assert row["display_symbol"]


# ==============================================================================
# Integration tests: API endpoint
# ==============================================================================


class TestSTIScreenerAPI:
    """Integration tests for GET /api/stocks/sti/screener."""

    def _mock_screener_data(self):
        """Return a minimal but valid STI screener payload for mocking."""
        return {
            "as_of": "2026-01-01T00:00:00+00:00",
            "source": "sti_constituents.csv",
            "count": 3,
            "summary": {
                "overbought": 0,
                "near_overbought": 1,
                "neutral": 1,
                "near_oversold": 0,
                "oversold": 1,
                "insufficient_data": 0,
            },
            "rows": [
                {
                    "symbol": "D05.SI",
                    "display_symbol": "D05",
                    "company": "DBS Group Holdings",
                    "sector": "Financials",
                    "current_price": 35.50,
                    "range_52w_position_percentile": 72.1,
                    "bollinger_percent_b": 0.81,
                    "bollinger_status": "near_upper_band",
                    "status_label": "Near Overbought",
                    "status_rank": 3,
                    "quality_score": 86,
                    "quality_label": "Strong",
                    "quality_reasons": ["Positive profit margin", "Positive return on equity"],
                    "quality_warnings": [],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
                {
                    "symbol": "Z74.SI",
                    "display_symbol": "Z74",
                    "company": "Singtel",
                    "sector": "Communication Services",
                    "current_price": 2.45,
                    "range_52w_position_percentile": 40.0,
                    "bollinger_percent_b": 0.5,
                    "bollinger_status": "within_bands",
                    "status_label": "Neutral",
                    "status_rank": 2,
                    "quality_score": 57,
                    "quality_label": "Moderate",
                    "quality_reasons": ["Positive profit margin"],
                    "quality_warnings": ["Revenue growth unavailable"],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
                {
                    "symbol": "C6L.SI",
                    "display_symbol": "C6L",
                    "company": "Singapore Airlines",
                    "sector": "Industrials",
                    "current_price": 6.80,
                    "range_52w_position_percentile": 20.0,
                    "bollinger_percent_b": -0.05,
                    "bollinger_status": "below_lower_band",
                    "status_label": "Oversold",
                    "status_rank": 0,
                    "quality_score": 43,
                    "quality_label": "Weak",
                    "quality_reasons": [],
                    "quality_warnings": ["Earnings growth unavailable"],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
            ],
        }

    def test_screener_returns_200(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener")
        assert resp.status_code == 200

    def test_screener_response_shape(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener")
        data = resp.get_json()
        for key in ("as_of", "source", "count", "summary", "rows"):
            assert key in data, f"Missing key: {key}"
        assert "scan_duration_seconds" in data

    def test_screener_row_shape(self, client):
        """Each row in the STI screener response must have required fields."""
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener")
        data = resp.get_json()
        assert len(data["rows"]) > 0
        row = data["rows"][0]
        for key in (
            "symbol", "display_symbol", "company", "sector", "current_price",
            "bollinger_status", "status_label",
            "quality_score", "quality_label", "quality_reasons", "quality_warnings",
        ):
            assert key in row, f"Row missing key: {key}"

    def test_screener_row_symbol_has_si_suffix(self, client):
        """Row symbols should have the .SI suffix for yfinance compatibility."""
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener")
        data = resp.get_json()
        for row in data["rows"]:
            assert row["symbol"].endswith(".SI"), (
                f"symbol {row['symbol']} should end with .SI"
            )

    def test_screener_row_display_symbol_no_si(self, client):
        """display_symbol should not have the .SI suffix."""
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener")
        data = resp.get_json()
        for row in data["rows"]:
            assert not row["display_symbol"].endswith(".SI"), (
                f"display_symbol {row['display_symbol']} should not end with .SI"
            )

    def test_screener_status_filter_oversold(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener?status=oversold")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "C6L.SI"

    def test_screener_status_filter_all(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener?status=all")
        data = resp.get_json()
        assert data["count"] == 3

    def test_screener_sector_filter(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener?sector=financials")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "D05.SI"

    def test_screener_combined_filter(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener?status=neutral&sector=communication")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "Z74.SI"

    def test_screener_summary_preserved(self, client):
        """Summary should reflect the full dataset regardless of filter."""
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sti/screener?status=oversold")
        data = resp.get_json()
        assert data["summary"]["near_overbought"] == 1
        assert data["summary"]["oversold"] == 1

    def test_screener_service_error_returns_500(self, client):
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            side_effect=RuntimeError("scan error"),
        ):
            resp = client.get("/api/stocks/sti/screener")
        assert resp.status_code == 500

    def test_screener_refresh_param_forwarded(self, client):
        """?refresh=true should call get_screener_data(refresh=True)."""
        calls = {}

        def mock_get(refresh=False):
            calls["refresh"] = refresh
            return self._mock_screener_data()

        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            side_effect=mock_get,
        ):
            client.get("/api/stocks/sti/screener?refresh=true")

        assert calls.get("refresh") is True

    def test_screener_missing_data_row_does_not_break(self, client):
        """A row with None price fields should not break the API response."""
        data = self._mock_screener_data()
        data["rows"].append({
            "symbol": "FAIL.SI",
            "display_symbol": "FAIL",
            "company": "Failed Stock",
            "sector": "Unknown",
            "current_price": None,
            "range_52w_position_percentile": None,
            "bollinger_percent_b": None,
            "bollinger_status": "insufficient_data",
            "status_label": "Insufficient Data",
            "status_rank": 5,
            "quality_score": None,
            "quality_label": "Insufficient Data",
            "quality_reasons": [],
            "quality_warnings": [],
            "last_updated": None,
        })
        data["count"] = len(data["rows"])
        with patch(
            "web.routes.api_sti_screener.sti_screener_service.get_screener_data",
            return_value=data,
        ):
            resp = client.get("/api/stocks/sti/screener")
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["count"] == 4


# ==============================================================================
# Integration tests: page route
# ==============================================================================


class TestSTIScreenerPageRoute:
    """Tests for the GET /stocks/sti page."""

    def test_screener_page_returns_200(self, client):
        resp = client.get("/stocks/sti")
        assert resp.status_code == 200

    def test_screener_page_contains_title(self, client):
        resp = client.get("/stocks/sti")
        assert b"STI Screener" in resp.data or b"Singapore STI" in resp.data

    def test_screener_page_has_disclaimer(self, client):
        resp = client.get("/stocks/sti")
        assert b"not financial advice" in resp.data

    def test_screener_page_has_singapore_disclaimer(self, client):
        """Page should mention SGX/Singapore-specific wording."""
        resp = client.get("/stocks/sti")
        assert b"REIT" in resp.data or b"currency risk" in resp.data

    def test_screener_page_links_back_to_dashboard(self, client):
        resp = client.get("/stocks/sti")
        assert b"/stocks/analysis" in resp.data

    def test_screener_page_has_table_element(self, client):
        resp = client.get("/stocks/sti")
        assert b"screenerTable" in resp.data or b"screener" in resp.data.lower()

    def test_screener_page_uses_sti_api_endpoint(self, client):
        """Template should fetch from the STI-specific API endpoint."""
        resp = client.get("/stocks/sti")
        assert b"/api/stocks/sti/screener" in resp.data


# ==============================================================================
# Integration tests: .SI ticker in single-stock analysis route
# ==============================================================================


class TestSITickerInAnalysisRoute:
    """Tests that .SI tickers work in the single-stock analysis routes."""

    def test_stock_analysis_page_accepts_si_ticker(self, client):
        """GET /stocks/D05.SI/analysis should return 200."""
        resp = client.get("/stocks/D05.SI/analysis")
        assert resp.status_code == 200

    def test_stock_analysis_page_accepts_reit_si_ticker(self, client):
        """GET /stocks/A17U.SI/analysis should return 200 (REIT-style ticker)."""
        resp = client.get("/stocks/A17U.SI/analysis")
        assert resp.status_code == 200

    def test_stock_analysis_page_accepts_multi_char_si_ticker(self, client):
        """GET /stocks/ME8U.SI/analysis should return 200."""
        resp = client.get("/stocks/ME8U.SI/analysis")
        assert resp.status_code == 200

    def test_api_analysis_accepts_si_ticker(self, client):
        """GET /api/stocks/D05.SI/analysis should not return 400 (ticker validation)."""
        # The endpoint may return 500 due to missing yfinance data in test env,
        # but it should NOT return 400 (invalid ticker).
        with patch("data.fundamentals.fetch_fundamentals", return_value={"error": "no data"}):
            with patch("data.fundamentals.fetch_price_history", return_value=[]):
                resp = client.get("/api/stocks/D05.SI/analysis")
        assert resp.status_code != 400, "D05.SI should be a valid ticker, not rejected as invalid"

    def test_us_ticker_still_works(self, client):
        """Existing US tickers without .SI should continue to work."""
        resp = client.get("/stocks/AAPL/analysis")
        assert resp.status_code == 200


# ==============================================================================
# Integration tests: dashboard link
# ==============================================================================


class TestDashboardSTILink:
    """The Stock Analysis dashboard should link to the STI screener."""

    def test_dashboard_has_sti_screener_link(self, client):
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"/stocks/sti" in resp.data

    def test_dashboard_still_has_sp500_link(self, client):
        """Adding the STI link should not remove the existing S&P 500 link."""
        resp = client.get("/stocks/analysis")
        assert b"/stocks/sp500" in resp.data
