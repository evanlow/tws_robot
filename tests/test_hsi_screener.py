"""Tests for the Hong Kong HSI Screener feature.

Covers:
- Constituent CSV loading and HK ticker handling
- HSIScreenerService: caching, failure handling, summary building
- display_symbol field in rows (leading-zero preservation)
- API endpoint shape and filtering
- Page route loads
- .HK ticker support in single-stock analysis routes
"""

import csv
import io
import threading
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def _make_bars(count=60, base_price=100.0, variance=5.0):
    """Generate synthetic OHLCV bars for HKD-priced stocks."""
    import random
    random.seed(42)
    bars = []
    price = base_price
    for i in range(count):
        change = random.uniform(-variance, variance)
        price = max(price + change, 0.01)
        bars.append({
            "timestamp": f"2024-01-{(i % 28) + 1:02d}",
            "open": round(price, 2),
            "high": round(price + random.uniform(0, 5), 2),
            "low": round(price - random.uniform(0, 5), 2),
            "close": round(price + random.uniform(-3, 3), 2),
            "volume": 1_000_000,
        })
    return bars


def _minimal_hsi_csv(rows):
    """Build a CSV string from a list of dicts."""
    if not rows:
        return "symbol,display_symbol,security,sector,sub_industry\n"
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["symbol", "display_symbol", "security", "sector", "sub_industry"])
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


# ==============================================================================
# Unit tests: HSI constituent CSV loading
# ==============================================================================


class TestHSIConstituentLoading:
    """Tests for loading the HSI constituents CSV."""

    def _make_service(self):
        from web.hsi_screener_service import HSIScreenerService
        return HSIScreenerService()

    def test_load_real_hsi_csv(self):
        """The bundled HSI CSV should be loadable and have expected columns."""
        svc = self._make_service()
        rows = svc._load_constituents()
        # HSI is a large universe; a much smaller count likely means the file is stale/truncated.
        assert len(rows) >= 70, "Expected at least 70 HSI constituents"
        for row in rows[:5]:
            assert "symbol" in row
            assert "display_symbol" in row
            assert "security" in row
            assert "sector" in row

    def test_hsi_csv_symbols_have_hk_suffix(self):
        """All symbols in the HSI CSV should have the .HK suffix."""
        svc = self._make_service()
        rows = svc._load_constituents()
        for row in rows:
            assert row["symbol"].endswith(".HK"), (
                f"Symbol {row['symbol']} should end with .HK"
            )

    def test_hsi_csv_display_symbols_without_hk(self):
        """display_symbol should not have the .HK suffix."""
        svc = self._make_service()
        rows = svc._load_constituents()
        for row in rows:
            assert not row["display_symbol"].endswith(".HK"), (
                f"display_symbol {row['display_symbol']} should not end with .HK"
            )

    def test_hsi_csv_leading_zeros_preserved(self):
        """Hong Kong stock codes with leading zeros must be preserved in display_symbol."""
        svc = self._make_service()
        rows = svc._load_constituents()
        symbols = {r["symbol"] for r in rows}
        display_symbols = {r["display_symbol"] for r in rows}
        # These tickers all have leading zeros and must be kept intact
        for sym, disp in (("0700.HK", "0700"), ("0005.HK", "0005"), ("0001.HK", "0001")):
            if sym in symbols:
                row = next(r for r in rows if r["symbol"] == sym)
                assert row["display_symbol"] == disp, (
                    f"Leading zeros must be preserved: expected {disp}, got {row['display_symbol']}"
                )

    def test_known_constituents_present(self):
        """Key HSI constituents should appear in the constituent list."""
        svc = self._make_service()
        rows = svc._load_constituents()
        symbols = {r["symbol"] for r in rows}
        for expected in ("0700.HK", "0005.HK", "0941.HK"):
            assert expected in symbols, f"{expected} should be in HSI constituents"

    def test_load_constituents_missing_file(self, tmp_path, monkeypatch):
        """Missing constituents file returns empty list rather than raising."""
        import web.hsi_screener_service as mod
        monkeypatch.setattr(mod, "_CONSTITUENTS_PATH", tmp_path / "nonexistent.csv")
        svc = self._make_service()
        rows = svc._load_constituents()
        assert rows == []

    def test_load_constituents_custom_csv(self, tmp_path, monkeypatch):
        """Service correctly parses a custom CSV with display_symbol column."""
        import web.hsi_screener_service as mod

        csv_content = _minimal_hsi_csv([
            {"symbol": "0700.HK", "display_symbol": "0700", "security": "Tencent Holdings",
             "sector": "Communication Services", "sub_industry": "Internet Content & Information"},
            {"symbol": "0005.HK", "display_symbol": "0005", "security": "HSBC Holdings",
             "sector": "Financials", "sub_industry": "Banks"},
        ])
        csv_file = tmp_path / "hsi_constituents.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        monkeypatch.setattr(mod, "_CONSTITUENTS_PATH", csv_file)

        svc = self._make_service()
        rows = svc._load_constituents()
        assert len(rows) == 2
        assert rows[0]["symbol"] == "0700.HK"
        assert rows[0]["display_symbol"] == "0700"
        assert rows[0]["security"] == "Tencent Holdings"
        assert rows[1]["symbol"] == "0005.HK"


# ==============================================================================
# Unit tests: HK / yfinance ticker handling
# ==============================================================================


class TestHKTickerHandling:
    """Tests for .HK ticker handling in the HSI screener."""

    def test_display_symbol_stripped_from_hk(self):
        """_hsi_insufficient_data_row uses display_symbol from constituent."""
        from web.hsi_screener_service import _hsi_insufficient_data_row
        row = _hsi_insufficient_data_row({
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "Internet Content & Information",
        })
        assert row["symbol"] == "0700.HK"
        assert row["display_symbol"] == "0700"

    def test_display_symbol_fallback_strips_hk(self):
        """When display_symbol is missing, it is derived by stripping .HK."""
        from web.hsi_screener_service import _hsi_insufficient_data_row
        row = _hsi_insufficient_data_row({
            "symbol": "0005.HK",
            "security": "HSBC Holdings",
            "sector": "Financials",
        })
        assert row["symbol"] == "0005.HK"
        assert row["display_symbol"] == "0005"

    def test_leading_zeros_preserved_in_symbol(self):
        """Leading zeros must be preserved in both symbol and display_symbol."""
        from web.hsi_screener_service import _hsi_insufficient_data_row
        for sym, disp in [("0001.HK", "0001"), ("0066.HK", "0066"), ("0101.HK", "0101")]:
            row = _hsi_insufficient_data_row({
                "symbol": sym,
                "display_symbol": disp,
                "security": "Test Co",
                "sector": "Financials",
            })
            assert row["symbol"] == sym, f"symbol must preserve leading zeros: {sym}"
            assert row["display_symbol"] == disp, f"display_symbol must preserve leading zeros: {disp}"

    def test_hsi_insufficient_data_row_has_momentum_fields(self):
        """_hsi_insufficient_data_row should include momentum fields defaulted to null."""
        from web.hsi_screener_service import _hsi_insufficient_data_row
        row = _hsi_insufficient_data_row({
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
        })
        assert "momentum_confirmation" in row
        assert "momentum_label" in row
        assert "momentum_reasons" in row
        assert row["momentum_confirmation"] is None
        assert row["momentum_label"] is None
        assert row["momentum_reasons"] == []

    def test_scan_ticker_row_has_display_symbol(self):
        """_scan_ticker should include display_symbol in the row."""
        from web.hsi_screener_service import HSIScreenerService
        svc = HSIScreenerService()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "Internet Content & Information",
        }
        bars = _make_bars(60, 380.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert row["symbol"] == "0700.HK"
        assert row["display_symbol"] == "0700"

    def test_hk_ticker_matches_api_ticker_regex(self):
        """HKEX .HK tickers should pass the API-level ticker regex."""
        import re
        _TICKER_RE = re.compile(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$")
        for ticker in ("0700.HK", "9988.HK", "0005.HK", "1299.HK", "3690.HK"):
            assert _TICKER_RE.match(ticker), f"{ticker} should match the ticker regex"

    def test_hk_ticker_uppercase_preserved(self):
        """Uppercase .HK tickers should remain unchanged after .upper()."""
        for ticker in ("0700.HK", "9988.HK", "0005.HK"):
            assert ticker.upper() == ticker


# ==============================================================================
# Unit tests: HSIScreenerService
# ==============================================================================


class TestHSIScreenerService:
    """Tests for web.hsi_screener_service.HSIScreenerService."""

    def _make_service(self):
        from web.hsi_screener_service import HSIScreenerService
        return HSIScreenerService()

    def test_scan_ticker_returns_row_shape(self):
        """_scan_ticker should always return a dict with required keys."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "Internet Content & Information",
        }
        bars = _make_bars(60, 380.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        required_keys = [
            "symbol", "display_symbol", "company", "sector", "current_price",
            "range_52w_position_percentile", "bollinger_percent_b",
            "bollinger_status", "status_label", "status_rank",
            "quality_score", "quality_label", "quality_reasons", "quality_warnings",
            "momentum_confirmation", "momentum_label", "momentum_reasons",
            "last_updated",
        ]
        for key in required_keys:
            assert key in row, f"Missing key: {key}"

    def test_scan_ticker_technical_status_field(self):
        """_scan_ticker should populate bollinger_status and status_label."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "",
        }
        bars = _make_bars(60, 380.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        valid_statuses = {
            "below_lower_band", "near_lower_band", "within_bands",
            "near_upper_band", "above_upper_band", "insufficient_data",
        }
        assert row["bollinger_status"] in valid_statuses
        assert row["status_label"] in (
            "Oversold", "Near Oversold", "Neutral",
            "Near Overbought", "Overbought", "Insufficient Data",
        )

    def test_scan_ticker_dividend_fields_present(self):
        """_scan_ticker should include annual_dividend and dividend_yield fields."""
        svc = self._make_service()
        constituent = {
            "symbol": "0005.HK",
            "display_symbol": "0005",
            "security": "HSBC Holdings",
            "sector": "Financials",
            "sub_industry": "Banks",
        }
        bars = _make_bars(60, 60.0)
        fundamentals = {"dividend_rate": 3.0, "dividend_yield": 0.05}
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value=fundamentals):
                row = svc._scan_ticker(constituent)
        assert "annual_dividend" in row
        assert "dividend_yield" in row
        assert row["annual_dividend"] == 3.0
        assert row["dividend_yield"] == 0.05

    def test_scan_ticker_dividend_fields_null_when_missing(self):
        """_scan_ticker should return None for dividend fields when not available."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "",
        }
        bars = _make_bars(60, 380.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert row["annual_dividend"] is None
        assert row["dividend_yield"] is None

    def test_scan_ticker_failure_returns_insufficient_data(self):
        """If price fetch raises, the row should reflect insufficient_data."""
        svc = self._make_service()
        constituent = {
            "symbol": "BADFETCH.HK",
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
        assert row["symbol"] == "BADFETCH.HK"
        assert row["display_symbol"] == "BADFETCH"

    def test_scan_ticker_empty_bars_returns_insufficient_data(self):
        """Empty bar list → insufficient_data row."""
        svc = self._make_service()
        constituent = {
            "symbol": "EMPTY.HK",
            "display_symbol": "EMPTY",
            "security": "Empty Co",
            "sector": "X",
            "sub_industry": "",
        }
        with patch("data.fundamentals.fetch_price_history", return_value=[]):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert row["bollinger_status"] == "insufficient_data"
        assert row["momentum_confirmation"] is None
        assert row["momentum_label"] is None
        assert row["momentum_reasons"] == []

    def test_scan_ticker_neutral_stock_has_null_momentum(self):
        """A neutral (within_bands) HSI stock should have null momentum fields."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "",
        }
        # Deterministic bars designed to produce within_bands
        bars = [
            {
                "timestamp": f"2024-{i // 28 + 1:02d}-{(i % 28) + 1:02d}",
                "open": 380.0, "high": 381.0, "low": 379.0,
                "close": 370.0 if i % 2 == 0 else 390.0,
                "volume": 5_000_000,
            }
            for i in range(59)
        ]
        bars.append({
            "timestamp": "2024-03-01", "open": 380.0, "high": 381.0, "low": 379.0,
            "close": 380.0, "volume": 5_000_000,
        })

        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        assert row["bollinger_status"] == "within_bands"
        assert "momentum_confirmation" in row
        assert "momentum_label" in row
        assert "momentum_reasons" in row
        # Non-oversold → momentum fields must be null/empty
        assert row["momentum_confirmation"] is None
        assert row["momentum_label"] is None

    def test_scan_ticker_missing_fundamentals_is_graceful(self):
        """Fundamentals failure does not break the scan; quality shows Insufficient Data."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "",
        }
        bars = _make_bars(60, 380.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", side_effect=RuntimeError("no data")):
                row = svc._scan_ticker(constituent)
        assert row["current_price"] is not None
        assert row["quality_label"] == "Insufficient Data"

    def test_scan_ticker_quality_fields_present(self):
        """_scan_ticker should include quality_score, quality_label, quality_reasons, quality_warnings."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "",
        }
        bars = _make_bars(60, 380.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
        assert "quality_score" in row
        assert "quality_label" in row
        assert "quality_reasons" in row
        assert "quality_warnings" in row
        assert row["quality_label"] in ("Strong", "Moderate", "Weak", "Insufficient Data")

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
        """Multiple HK tickers are scanned concurrently; all appear in result."""
        svc = self._make_service()
        constituents = [
            {
                "symbol": f"0{i:03d}.HK",
                "display_symbol": f"0{i:03d}",
                "security": f"Corp {i}",
                "sector": "Financials",
                "sub_industry": "Banks",
            }
            for i in range(1, 11)
        ]
        bars = _make_bars(60, 100.0)

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
            {"symbol": "0700.HK", "display_symbol": "0700", "security": "Tencent", "sector": "Communication Services", "sub_industry": ""},
            {"symbol": "FAIL.HK", "display_symbol": "FAIL", "security": "Bad Corp", "sector": "Financials", "sub_industry": ""},
        ]
        bars = _make_bars(60, 380.0)

        def side_effect(symbol, **kwargs):
            if symbol == "FAIL.HK":
                raise RuntimeError("yfinance timeout")
            return bars

        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("data.fundamentals.fetch_price_history", side_effect=side_effect):
                with patch("data.fundamentals.get_fundamentals", return_value={}):
                    result = svc._scan()

        assert result["count"] == 2
        fail_row = next(r for r in result["rows"] if r["symbol"] == "FAIL.HK")
        good_row = next(r for r in result["rows"] if r["symbol"] == "0700.HK")
        assert fail_row["bollinger_status"] == "insufficient_data"
        assert good_row["current_price"] is not None

    def test_scan_result_has_display_symbol_in_all_rows(self):
        """Every row in the scan result should have a display_symbol field."""
        svc = self._make_service()
        constituents = [
            {"symbol": "0700.HK", "display_symbol": "0700", "security": "Tencent", "sector": "Communication Services", "sub_industry": ""},
            {"symbol": "0005.HK", "display_symbol": "0005", "security": "HSBC", "sector": "Financials", "sub_industry": ""},
        ]
        bars = _make_bars(60, 380.0)
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


class TestHSIScreenerAPI:
    """Integration tests for GET /api/stocks/hsi/screener."""

    def _mock_screener_data(self):
        """Return a minimal but valid HSI screener payload for mocking."""
        return {
            "as_of": "2026-01-01T00:00:00+00:00",
            "source": "hsi_constituents.csv",
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
                    "symbol": "0005.HK",
                    "display_symbol": "0005",
                    "company": "HSBC Holdings",
                    "sector": "Financials",
                    "current_price": 62.80,
                    "range_52w_position_percentile": 72.1,
                    "bollinger_percent_b": 0.81,
                    "bollinger_status": "near_upper_band",
                    "status_label": "Near Overbought",
                    "status_rank": 3,
                    "quality_score": 86,
                    "quality_label": "Strong",
                    "quality_reasons": ["Positive profit margin", "Positive return on equity"],
                    "quality_warnings": [],
                    "annual_dividend": 2.43,
                    "dividend_yield": 0.039,
                    "momentum_confirmation": None,
                    "momentum_label": None,
                    "momentum_reasons": [],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
                {
                    "symbol": "0941.HK",
                    "display_symbol": "0941",
                    "company": "China Mobile",
                    "sector": "Communication Services",
                    "current_price": 72.10,
                    "range_52w_position_percentile": 40.0,
                    "bollinger_percent_b": 0.5,
                    "bollinger_status": "within_bands",
                    "status_label": "Neutral",
                    "status_rank": 2,
                    "quality_score": 57,
                    "quality_label": "Moderate",
                    "quality_reasons": ["Positive profit margin"],
                    "quality_warnings": ["Revenue growth unavailable"],
                    "annual_dividend": 3.86,
                    "dividend_yield": 0.054,
                    "momentum_confirmation": None,
                    "momentum_label": None,
                    "momentum_reasons": [],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
                {
                    "symbol": "0700.HK",
                    "display_symbol": "0700",
                    "company": "Tencent Holdings",
                    "sector": "Communication Services",
                    "current_price": 370.0,
                    "range_52w_position_percentile": 20.0,
                    "bollinger_percent_b": -0.05,
                    "bollinger_status": "below_lower_band",
                    "status_label": "Oversold",
                    "status_rank": 0,
                    "quality_score": 78,
                    "quality_label": "Strong",
                    "quality_reasons": [],
                    "quality_warnings": ["Earnings growth unavailable"],
                    "annual_dividend": None,
                    "dividend_yield": None,
                    "momentum_confirmation": None,
                    "momentum_label": None,
                    "momentum_reasons": [],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
            ],
        }

    def test_screener_returns_200(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        assert resp.status_code == 200

    def test_screener_response_shape(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        data = resp.get_json()
        for key in ("as_of", "source", "count", "summary", "rows"):
            assert key in data, f"Missing key: {key}"
        assert "scan_duration_seconds" in data

    def test_screener_row_shape(self, client):
        """Each row in the HSI screener response must have required fields."""
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        data = resp.get_json()
        assert len(data["rows"]) > 0
        row = data["rows"][0]
        for key in (
            "symbol", "display_symbol", "company", "sector", "current_price",
            "bollinger_status", "status_label",
            "quality_score", "quality_label", "quality_reasons", "quality_warnings",
            "annual_dividend", "dividend_yield",
            "momentum_confirmation", "momentum_label", "momentum_reasons",
        ):
            assert key in row, f"Row missing key: {key}"

    def test_screener_row_symbol_has_hk_suffix(self, client):
        """Row symbols should have the .HK suffix for yfinance compatibility."""
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        data = resp.get_json()
        for row in data["rows"]:
            assert row["symbol"].endswith(".HK"), (
                f"symbol {row['symbol']} should end with .HK"
            )

    def test_screener_row_display_symbol_no_hk(self, client):
        """display_symbol should not have the .HK suffix."""
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        data = resp.get_json()
        for row in data["rows"]:
            assert not row["display_symbol"].endswith(".HK"), (
                f"display_symbol {row['display_symbol']} should not end with .HK"
            )

    def test_screener_row_display_symbol_has_leading_zeros(self, client):
        """display_symbol values should preserve leading zeros."""
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        data = resp.get_json()
        symbols_map = {r["symbol"]: r["display_symbol"] for r in data["rows"]}
        assert symbols_map.get("0005.HK") == "0005", "0005.HK display_symbol must be '0005' (with leading zero)"
        assert symbols_map.get("0700.HK") == "0700", "0700.HK display_symbol must be '0700' (with leading zero)"
        assert symbols_map.get("0941.HK") == "0941", "0941.HK display_symbol must be '0941' (with leading zero)"

    def test_screener_status_filter_oversold(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener?status=oversold")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "0700.HK"

    def test_screener_status_filter_all(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener?status=all")
        data = resp.get_json()
        assert data["count"] == 3

    def test_screener_sector_filter(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener?sector=financials")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "0005.HK"

    def test_screener_combined_filter(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener?status=neutral&sector=communication")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "0941.HK"

    def test_screener_summary_preserved(self, client):
        """Summary should reflect the full dataset regardless of filter."""
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/hsi/screener?status=oversold")
        data = resp.get_json()
        assert data["summary"]["near_overbought"] == 1
        assert data["summary"]["oversold"] == 1

    def test_screener_service_error_returns_500(self, client):
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            side_effect=RuntimeError("scan error"),
        ):
            resp = client.get("/api/stocks/hsi/screener")
        assert resp.status_code == 500

    def test_screener_refresh_param_forwarded(self, client):
        """?refresh=true should call get_screener_data(refresh=True)."""
        calls = {}

        def mock_get(refresh=False):
            calls["refresh"] = refresh
            return self._mock_screener_data()

        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            side_effect=mock_get,
        ):
            client.get("/api/stocks/hsi/screener?refresh=true")

        assert calls.get("refresh") is True

    def test_screener_missing_data_row_does_not_break(self, client):
        """A row with None price fields should not break the API response."""
        data = self._mock_screener_data()
        data["rows"].append({
            "symbol": "FAIL.HK",
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
            "annual_dividend": None,
            "dividend_yield": None,
            "momentum_confirmation": None,
            "momentum_label": None,
            "momentum_reasons": [],
            "last_updated": None,
        })
        data["count"] = len(data["rows"])
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=data,
        ):
            resp = client.get("/api/stocks/hsi/screener")
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["count"] == 4

    def test_screener_error_payload_propagated_to_response(self, client):
        """When get_screener_data returns a dict with 'error' key, the API
        includes it in the JSON response (covers the 'if error in data' branch)."""
        error_data = {
            "rows": [],
            "count": 0,
            "summary": {},
            "scan_duration_seconds": None,
            "error": "No constituents loaded",
        }
        with patch(
            "web.routes.api_hsi_screener.hsi_screener_service.get_screener_data",
            return_value=error_data,
        ):
            resp = client.get("/api/stocks/hsi/screener")
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["error"] == "No constituents loaded"


# ==============================================================================
# Integration tests: page route
# ==============================================================================


class TestHSIScreenerPageRoute:
    """Tests for the GET /stocks/hsi page."""

    def test_screener_page_returns_200(self, client):
        resp = client.get("/stocks/hsi")
        assert resp.status_code == 200

    def test_screener_page_contains_title(self, client):
        resp = client.get("/stocks/hsi")
        assert b"HSI Screener" in resp.data or b"Hong Kong HSI" in resp.data

    def test_screener_page_has_disclaimer(self, client):
        resp = client.get("/stocks/hsi")
        assert b"not financial advice" in resp.data

    def test_screener_page_has_hk_disclaimer(self, client):
        """Page should mention HKD and Hong Kong-specific caveats."""
        resp = client.get("/stocks/hsi")
        assert b"HKD" in resp.data or b"currency risk" in resp.data or b"Hong Kong" in resp.data

    def test_screener_page_links_back_to_dashboard(self, client):
        resp = client.get("/stocks/hsi")
        assert b"/stocks/analysis" in resp.data

    def test_screener_page_has_table_element(self, client):
        resp = client.get("/stocks/hsi")
        assert b"screenerTable" in resp.data or b"screener" in resp.data.lower()

    def test_screener_page_uses_hsi_api_endpoint(self, client):
        """Template should fetch from the HSI-specific API endpoint."""
        resp = client.get("/stocks/hsi")
        assert b"/api/stocks/hsi/screener" in resp.data

    def test_screener_page_has_company_name_filter(self, client):
        resp = client.get("/stocks/hsi")
        assert b"companyFilter" in resp.data
        assert b"e.g., Baidu, Li-Ning, JD.com" in resp.data


# ==============================================================================
# Integration tests: .HK ticker in single-stock analysis route
# ==============================================================================


class TestHKTickerInAnalysisRoute:
    """Tests that .HK tickers work in the single-stock analysis routes."""

    def test_stock_analysis_page_accepts_hk_ticker(self, client):
        """GET /stocks/0700.HK/analysis should return 200."""
        resp = client.get("/stocks/0700.HK/analysis")
        assert resp.status_code == 200

    def test_stock_analysis_page_accepts_hsbc_hk_ticker(self, client):
        """GET /stocks/0005.HK/analysis should return 200."""
        resp = client.get("/stocks/0005.HK/analysis")
        assert resp.status_code == 200

    def test_stock_analysis_page_accepts_china_mobile_hk_ticker(self, client):
        """GET /stocks/0941.HK/analysis should return 200."""
        resp = client.get("/stocks/0941.HK/analysis")
        assert resp.status_code == 200

    def test_api_analysis_accepts_hk_ticker(self, client):
        """GET /api/stocks/0700.HK/analysis should not return 400 (ticker validation)."""
        with patch("data.fundamentals.fetch_fundamentals", return_value={"error": "no data"}):
            with patch("data.fundamentals.fetch_price_history", return_value=[]):
                resp = client.get("/api/stocks/0700.HK/analysis")
        assert resp.status_code != 400, "0700.HK should be a valid ticker, not rejected as invalid"

    def test_us_ticker_still_works(self, client):
        """Existing US tickers without .HK should continue to work."""
        resp = client.get("/stocks/AAPL/analysis")
        assert resp.status_code == 200

    def test_si_ticker_still_works(self, client):
        """Existing .SI tickers should continue to work."""
        resp = client.get("/stocks/D05.SI/analysis")
        assert resp.status_code == 200


# ==============================================================================
# Integration tests: dashboard link
# ==============================================================================


class TestDashboardHSILink:
    """The Stock Analysis dashboard should link to the HSI screener."""

    def test_dashboard_has_hsi_screener_link(self, client):
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"/stocks/hsi" in resp.data

    def test_dashboard_still_has_sp500_link(self, client):
        """Adding the HSI link should not remove the existing S&P 500 link."""
        resp = client.get("/stocks/analysis")
        assert b"/stocks/sp500" in resp.data

    def test_dashboard_still_has_sti_link(self, client):
        """Adding the HSI link should not remove the existing STI link."""
        resp = client.get("/stocks/analysis")
        assert b"/stocks/sti" in resp.data


# ==============================================================================
# Additional branch coverage tests
# ==============================================================================


class TestHSIScreenerServiceAdditional:
    """Cover remaining branches in HSIScreenerService."""

    def _make_service(self):
        from web.hsi_screener_service import HSIScreenerService
        return HSIScreenerService()

    def test_scan_ticker_none_close_returns_insufficient(self):
        """Last bar with close=None triggers the None-check, returning an insufficient_data row."""
        svc = self._make_service()
        constituent = {
            "symbol": "0700.HK",
            "display_symbol": "0700",
            "security": "Tencent Holdings",
            "sector": "Communication Services",
            "sub_industry": "",
        }
        bars = [{"close": 380.0 + i, "open": 380.0, "high": 382.0, "low": 378.0} for i in range(30)]
        bars[-1]["close"] = None

        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            row = svc._scan_ticker(constituent)

        assert row["bollinger_status"] == "insufficient_data"
        assert row["current_price"] is None

    def test_scan_with_empty_constituents_returns_error_payload(self, tmp_path, monkeypatch):
        """_scan() when _load_constituents returns [] → error key in result."""
        import web.hsi_screener_service as mod
        monkeypatch.setattr(mod, "_CONSTITUENTS_PATH", tmp_path / "nonexistent.csv")
        svc = self._make_service()
        result = svc._scan()
        assert result["count"] == 0
        assert "error" in result

    def test_future_unexpected_exception_is_handled(self):
        """future.result() raising in as_completed loop → insufficient_data row."""
        svc = self._make_service()
        constituents = [
            {"symbol": "0700.HK", "display_symbol": "0700", "security": "Tencent", "sector": "Communication Services", "sub_industry": ""},
        ]

        boom_future = Future()
        boom_future.set_exception(RuntimeError("unexpected executor failure"))

        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("web.hsi_screener_service.ThreadPoolExecutor") as mock_executor_cls:
                mock_executor = MagicMock()
                mock_executor_cls.return_value.__enter__ = lambda s: mock_executor
                mock_executor_cls.return_value.__exit__ = MagicMock(return_value=False)
                mock_executor.submit.return_value = boom_future

                with patch("web.hsi_screener_service.as_completed", return_value=[boom_future]):
                    result = svc._scan()

        assert result["count"] == 1
        assert result["rows"][0]["bollinger_status"] == "insufficient_data"

    def test_concurrent_wait_while_scanning(self):
        """Second call during a running scan waits and then uses the cache result."""
        svc = self._make_service()
        scan_calls = [0]
        barrier = threading.Event()
        scan_started = threading.Event()

        def slow_scan():
            scan_calls[0] += 1
            scan_started.set()
            barrier.wait(timeout=5)
            return {"as_of": "x", "source": "x", "count": 1, "summary": {}, "rows": [{"status_rank": 0}]}

        svc._scan = slow_scan

        results = {}

        def call_service(key):
            results[key] = svc.get_screener_data(refresh=False)

        t1 = threading.Thread(target=call_service, args=("first",))
        t1.start()
        scan_started.wait(timeout=5)

        t2 = threading.Thread(target=call_service, args=("second",))
        t2.start()

        barrier.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert scan_calls[0] == 1, "Only one scan should have run"
        assert results["first"] is results["second"], "Both calls should return the same cached result"
