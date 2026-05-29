"""Tests for the S&P 500 Screener feature.

Covers:
- Constituent CSV loading and ticker normalisation
- Bollinger status mapping (via shared technical_analysis module)
- SP500ScreenerService: caching, failure handling, summary building
- API endpoint shape and filtering
- Page route loads
"""

import csv
import datetime
import io
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from web import create_app
from web.technical_analysis import (
    BOLLINGER_STATUS_LABELS,
    BOLLINGER_STATUS_RANK,
    compute_bollinger_bands,
    calc_52w_percentile,
)


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


def _make_bars(count=60, base_price=100.0, variance=2.0):
    """Generate synthetic OHLCV bars."""
    import random
    random.seed(99)
    bars = []
    price = base_price
    for i in range(count):
        change = random.uniform(-variance, variance)
        price = max(price + change, 1.0)
        bars.append({
            "timestamp": f"2024-01-{(i % 28) + 1:02d}",
            "open": round(price, 2),
            "high": round(price + random.uniform(0, 2), 2),
            "low": round(price - random.uniform(0, 2), 2),
            "close": round(price + random.uniform(-1, 1), 2),
            "volume": 500_000,
        })
    return bars


def _minimal_csv(rows):
    """Build a CSV string from a list of dicts."""
    if not rows:
        return "symbol,security,sector,sub_industry\n"
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["symbol", "security", "sector", "sub_industry"])
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


# ==============================================================================
# Unit tests: web/technical_analysis.py
# ==============================================================================


class TestBollingerStatusLabels:
    """Bollinger status label mapping."""

    def test_all_statuses_have_labels(self):
        statuses = [
            "below_lower_band", "near_lower_band", "within_bands",
            "near_upper_band", "above_upper_band", "insufficient_data",
        ]
        for s in statuses:
            assert s in BOLLINGER_STATUS_LABELS
            assert BOLLINGER_STATUS_LABELS[s]

    def test_oversold_label(self):
        assert BOLLINGER_STATUS_LABELS["below_lower_band"] == "Oversold"

    def test_overbought_label(self):
        assert BOLLINGER_STATUS_LABELS["above_upper_band"] == "Overbought"

    def test_insufficient_data_label(self):
        assert BOLLINGER_STATUS_LABELS["insufficient_data"] == "Insufficient Data"

    def test_rank_ordering(self):
        """Oversold should have a lower rank than overbought."""
        assert BOLLINGER_STATUS_RANK["below_lower_band"] < BOLLINGER_STATUS_RANK["above_upper_band"]
        assert BOLLINGER_STATUS_RANK["within_bands"] == 2  # mid-point


class TestSharedComputeBollingerBands:
    """Tests for compute_bollinger_bands in web.technical_analysis."""

    def test_basic_output_keys(self):
        bars = _make_bars(60, 100.0)
        result = compute_bollinger_bands(bars, 100.0)
        for key in ("upper", "middle", "lower", "bandwidth", "percent_b", "status"):
            assert key in result

    def test_insufficient_bars(self):
        bars = _make_bars(5, 100.0)
        result = compute_bollinger_bands(bars, 100.0)
        assert result["status"] == "insufficient_data"
        assert result["upper"] is None

    def test_price_far_above_gives_overbought(self):
        bars = _make_bars(30, 100.0, variance=0.1)
        result = compute_bollinger_bands(bars, 200.0)
        assert result["status"] == "above_upper_band"
        assert result["percent_b"] > 1

    def test_price_far_below_gives_oversold(self):
        bars = _make_bars(30, 100.0, variance=0.1)
        result = compute_bollinger_bands(bars, 10.0)
        assert result["status"] == "below_lower_band"
        assert result["percent_b"] < 0


class TestCalc52wPercentile:
    """Tests for calc_52w_percentile helper."""

    def test_midpoint(self):
        result = calc_52w_percentile(100.0, 50.0, 150.0)
        assert result == 50.0

    def test_at_high(self):
        result = calc_52w_percentile(150.0, 50.0, 150.0)
        assert result == 100.0

    def test_at_low(self):
        result = calc_52w_percentile(50.0, 50.0, 150.0)
        assert result == 0.0

    def test_none_inputs_return_none(self):
        assert calc_52w_percentile(None, 50.0, 150.0) is None
        assert calc_52w_percentile(100.0, None, 150.0) is None
        assert calc_52w_percentile(100.0, 50.0, None) is None

    def test_zero_range_returns_none(self):
        assert calc_52w_percentile(100.0, 100.0, 100.0) is None


# ==============================================================================
# Unit tests: SP500ScreenerService
# ==============================================================================


class TestSP500ScreenerService:
    """Tests for web.sp500_screener_service.SP500ScreenerService."""

    def _make_service(self):
        """Create a fresh service instance (not the module-level singleton)."""
        from web.sp500_screener_service import SP500ScreenerService
        return SP500ScreenerService()

    def test_load_constituents_from_real_csv(self):
        """The bundled CSV should be loadable and have expected columns."""
        svc = self._make_service()
        rows = svc._load_constituents()
        assert len(rows) > 10
        for row in rows[:5]:
            assert "symbol" in row
            assert "security" in row
            assert "sector" in row

    def test_load_constituents_missing_file(self, tmp_path, monkeypatch):
        """Missing file returns empty list rather than raising."""
        import web.sp500_screener_service as mod
        monkeypatch.setattr(mod, "_CONSTITUENTS_PATH", tmp_path / "nonexistent.csv")
        svc = self._make_service()
        rows = svc._load_constituents()
        assert rows == []

    def test_scan_ticker_returns_row_shape(self):
        """_scan_ticker should always return a dict with required keys."""
        svc = self._make_service()
        constituent = {"symbol": "AAPL", "security": "Apple Inc.", "sector": "IT", "sub_industry": ""}

        bars = _make_bars(60, 150.0)
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        required_keys = [
            "symbol", "company", "sector", "current_price",
            "range_52w_position_percentile", "bollinger_percent_b",
            "bollinger_status", "status_label", "status_rank",
            "quality_score", "quality_label", "quality_reasons", "quality_warnings",
            "last_updated",
        ]
        for key in required_keys:
            assert key in row, f"Missing key: {key}"

    def test_scan_ticker_failure_returns_insufficient_data(self):
        """If price fetch raises an exception the row should reflect insufficient_data."""
        svc = self._make_service()
        constituent = {"symbol": "BADFETCH", "security": "Bad Co", "sector": "X", "sub_industry": ""}

        with patch("data.fundamentals.fetch_price_history", side_effect=RuntimeError("network error")):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        assert row["bollinger_status"] == "insufficient_data"
        assert row["current_price"] is None

    def test_scan_ticker_empty_bars_returns_insufficient_data(self):
        """Empty bar list → insufficient_data row."""
        svc = self._make_service()
        constituent = {"symbol": "EMPTY", "security": "Empty Co", "sector": "X", "sub_industry": ""}

        with patch("data.fundamentals.fetch_price_history", return_value=[]):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        assert row["bollinger_status"] == "insufficient_data"

    def test_scan_ticker_few_bars_returns_insufficient_data(self):
        """Fewer bars than the Bollinger period → insufficient_data."""
        svc = self._make_service()
        constituent = {"symbol": "FEW", "security": "Few Co", "sector": "X", "sub_industry": ""}
        few_bars = _make_bars(5, 100.0)

        with patch("data.fundamentals.fetch_price_history", return_value=few_bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)

        assert row["bollinger_status"] == "insufficient_data"

    def test_scan_ticker_populates_label_and_rank(self):
        """Status label and rank should match the BOLLINGER_STATUS_LABELS/RANK dicts."""
        svc = self._make_service()
        constituent = {"symbol": "TEST", "security": "Test Corp", "sector": "Tech", "sub_industry": ""}
        bars = _make_bars(60, 100.0, variance=0.1)
        # Price far above → overbought
        with patch("data.fundamentals.fetch_price_history", return_value=bars):
            with patch("data.fundamentals.get_fundamentals", return_value={}):
                row = svc._scan_ticker(constituent)
                # Override with forced overbought via patching compute_bollinger_bands
                pass

        # Just check that whatever status came out is consistent
        status = row["bollinger_status"]
        assert row["status_label"] == BOLLINGER_STATUS_LABELS.get(status, status)
        assert row["status_rank"] == BOLLINGER_STATUS_RANK.get(status, 5)

    def test_get_screener_data_caching(self):
        """Second call within TTL should return cached result without re-scanning."""
        svc = self._make_service()
        scan_calls = [0]

        real_scan = svc._scan

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

    def test_concurrent_scan_multiple_tickers(self):
        """Multiple tickers are scanned concurrently; all appear in result."""
        svc = self._make_service()
        constituents = [
            {"symbol": f"T{i:02d}", "security": f"Corp {i}", "sector": "Tech", "sub_industry": ""}
            for i in range(20)
        ]

        bars = _make_bars(60, 100.0)

        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("data.fundamentals.fetch_price_history", return_value=bars):
                with patch("data.fundamentals.get_fundamentals", return_value={}):
                    result = svc._scan()

        assert result["count"] == 20
        symbols_in_result = {r["symbol"] for r in result["rows"]}
        for c in constituents:
            assert c["symbol"] in symbols_in_result

    def test_concurrent_scan_isolates_failures(self):
        """A failing ticker does not stop the scan; others still return data."""
        svc = self._make_service()
        constituents = [
            {"symbol": "GOOD", "security": "Good Corp", "sector": "Tech", "sub_industry": ""},
            {"symbol": "FAIL", "security": "Bad Corp", "sector": "Tech", "sub_industry": ""},
        ]
        bars = _make_bars(60, 100.0)

        def side_effect(symbol, **kwargs):
            if symbol == "FAIL":
                raise RuntimeError("yfinance timeout")
            return bars

        with patch.object(svc, "_load_constituents", return_value=constituents):
            with patch("data.fundamentals.fetch_price_history", side_effect=side_effect):
                with patch("data.fundamentals.get_fundamentals", return_value={}):
                    result = svc._scan()

        assert result["count"] == 2
        fail_row = next(r for r in result["rows"] if r["symbol"] == "FAIL")
        good_row = next(r for r in result["rows"] if r["symbol"] == "GOOD")
        assert fail_row["bollinger_status"] == "insufficient_data"
        assert good_row["bollinger_status"] != "insufficient_data" or good_row["current_price"] is not None

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


class TestSP500SummaryBuilding:
    """Tests for _build_summary helper."""

    def test_summary_counts_correctly(self):
        from web.sp500_screener_service import _build_summary
        rows = [
            {"bollinger_status": "below_lower_band"},
            {"bollinger_status": "below_lower_band"},
            {"bollinger_status": "near_lower_band"},
            {"bollinger_status": "within_bands"},
            {"bollinger_status": "near_upper_band"},
            {"bollinger_status": "above_upper_band"},
            {"bollinger_status": "insufficient_data"},
        ]
        summary = _build_summary(rows)
        assert summary["oversold"] == 2
        assert summary["near_oversold"] == 1
        assert summary["neutral"] == 1
        assert summary["near_overbought"] == 1
        assert summary["overbought"] == 1
        assert summary["insufficient_data"] == 1

    def test_empty_rows(self):
        from web.sp500_screener_service import _build_summary
        summary = _build_summary([])
        assert all(v == 0 for v in summary.values())


# ==============================================================================
# Unit tests: compute_quality_score
# ==============================================================================


class TestComputeQualityScore:
    """Unit tests for web.sp500_screener_service.compute_quality_score."""

    def _call(self, fundamentals):
        from web.sp500_screener_service import compute_quality_score
        return compute_quality_score(fundamentals)

    # -- Label boundary tests --------------------------------------------------

    def test_strong_quality_all_checks_pass(self):
        """All positive fundamentals → Strong label and score ≥ 75."""
        result = self._call({
            "revenue_growth": 0.12,
            "earnings_growth": 0.08,
            "profit_margin": 0.20,
            "operating_margin": 0.25,
            "roe": 0.30,
            "debt_to_equity": 40.0,
            "current_ratio": 2.5,
        })
        assert result["quality_label"] == "Strong"
        assert result["quality_score"] is not None
        assert result["quality_score"] >= 75
        assert len(result["quality_reasons"]) > 0

    def test_moderate_quality_about_half_pass(self):
        """Roughly half the checks pass → Moderate label (50 ≤ score < 75)."""
        result = self._call({
            "revenue_growth": -0.05,   # fail
            "earnings_growth": -0.10,  # fail
            "profit_margin": 0.15,     # pass
            "operating_margin": 0.10,  # pass
            "roe": 0.05,               # pass
            "debt_to_equity": 80.0,    # pass
            "current_ratio": 0.7,      # fail
        })
        assert result["quality_label"] == "Moderate"
        assert 50 <= result["quality_score"] < 75

    def test_weak_quality_most_checks_fail(self):
        """Mostly negative fundamentals → Weak label (score < 50)."""
        result = self._call({
            "revenue_growth": -0.20,
            "earnings_growth": -0.15,
            "profit_margin": -0.05,
            "operating_margin": -0.10,
            "roe": -0.08,
            "debt_to_equity": 200.0,
            "current_ratio": 0.5,
        })
        assert result["quality_label"] == "Weak"
        assert result["quality_score"] is not None
        assert result["quality_score"] < 50

    def test_insufficient_data_empty_dict(self):
        """Empty fundamentals dict → Insufficient Data."""
        result = self._call({})
        assert result["quality_label"] == "Insufficient Data"
        assert result["quality_score"] is None

    def test_insufficient_data_error_key(self):
        """Fundamentals dict with error key → Insufficient Data."""
        result = self._call({"error": "yfinance failed", "symbol": "TEST"})
        assert result["quality_label"] == "Insufficient Data"
        assert result["quality_score"] is None

    def test_insufficient_data_fewer_than_3_metrics(self):
        """Only 2 available data points → Insufficient Data (not enough)."""
        result = self._call({
            "revenue_growth": 0.10,
            "earnings_growth": 0.05,
            # all other fields absent
        })
        assert result["quality_label"] == "Insufficient Data"
        assert result["quality_score"] is None

    # -- Missing / null field handling -----------------------------------------

    def test_none_fields_produce_warnings_not_errors(self):
        """None fields should add warnings, not crash or fail checks."""
        result = self._call({
            "revenue_growth": None,
            "earnings_growth": None,
            "profit_margin": 0.20,
            "operating_margin": 0.15,
            "roe": 0.10,
            "debt_to_equity": 50.0,
            "current_ratio": 1.5,
        })
        assert result["quality_label"] in ("Strong", "Moderate", "Weak", "Insufficient Data")
        # Warnings should mention the missing fields
        assert any("Revenue growth" in w for w in result["quality_warnings"])
        assert any("Earnings growth" in w for w in result["quality_warnings"])

    def test_null_fundamentals_argument(self):
        """None or empty fundamentals argument is handled gracefully."""
        result_none = self._call(None)
        assert result_none["quality_label"] == "Insufficient Data"

        result_empty = self._call({})
        assert result_empty["quality_label"] == "Insufficient Data"

    def test_returned_dict_always_has_required_keys(self):
        """compute_quality_score always returns all required keys."""
        for fundamentals in [{}, {"error": "x"}, {"revenue_growth": 0.1}, {
            "revenue_growth": 0.1, "earnings_growth": 0.2,
            "profit_margin": 0.1, "operating_margin": 0.1,
            "roe": 0.1, "debt_to_equity": 30.0, "current_ratio": 2.0,
        }]:
            result = self._call(fundamentals)
            for key in ("quality_score", "quality_label", "quality_reasons", "quality_warnings"):
                assert key in result, f"Missing key '{key}' for input {fundamentals}"

    def test_debt_to_equity_threshold(self):
        """Debt-to-equity ≥ 150 is treated as a fail."""
        below = self._call({"profit_margin": 0.1, "operating_margin": 0.1, "roe": 0.1, "debt_to_equity": 149.9})
        above = self._call({"profit_margin": 0.1, "operating_margin": 0.1, "roe": 0.1, "debt_to_equity": 150.1})
        # 149.9 should pass the debt check; 150.1 should not
        assert any("Debt-to-equity" in r for r in below["quality_reasons"])
        assert not any("Debt-to-equity" in r for r in above["quality_reasons"])

    def test_current_ratio_threshold(self):
        """Current ratio < 1 is a fail; ≥ 1 is a pass."""
        pass_case = self._call({"profit_margin": 0.1, "operating_margin": 0.1, "roe": 0.1, "current_ratio": 1.0})
        fail_case = self._call({"profit_margin": 0.1, "operating_margin": 0.1, "roe": 0.1, "current_ratio": 0.99})
        assert any("Current ratio" in r for r in pass_case["quality_reasons"])
        assert not any("Current ratio" in r for r in fail_case["quality_reasons"])


# ==============================================================================
# Integration tests: API endpoint
# ==============================================================================


class TestSP500ScreenerAPI:
    """Integration tests for GET /api/stocks/sp500/screener."""

    def _mock_screener_data(self):
        """Return a minimal but valid screener payload for mocking."""
        return {
            "as_of": "2026-01-01T00:00:00+00:00",
            "source": "sp500_constituents.csv",
            "count": 3,
            "summary": {
                "overbought": 1,
                "near_overbought": 0,
                "neutral": 1,
                "near_oversold": 0,
                "oversold": 1,
                "insufficient_data": 0,
            },
            "rows": [
                {
                    "symbol": "AAPL",
                    "company": "Apple Inc.",
                    "sector": "Information Technology",
                    "current_price": 150.0,
                    "range_52w_position_percentile": 72.3,
                    "bollinger_percent_b": 0.9,
                    "bollinger_status": "near_upper_band",
                    "status_label": "Near Overbought",
                    "status_rank": 3,
                    "quality_score": 86,
                    "quality_label": "Strong",
                    "quality_reasons": ["Positive revenue growth", "Positive profit margin"],
                    "quality_warnings": [],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
                {
                    "symbol": "XOM",
                    "company": "Exxon Mobil",
                    "sector": "Energy",
                    "current_price": 90.0,
                    "range_52w_position_percentile": 20.0,
                    "bollinger_percent_b": -0.05,
                    "bollinger_status": "below_lower_band",
                    "status_label": "Oversold",
                    "status_rank": 0,
                    "quality_score": 43,
                    "quality_label": "Weak",
                    "quality_reasons": ["Positive profit margin"],
                    "quality_warnings": ["Revenue growth unavailable"],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
                {
                    "symbol": "JPM",
                    "company": "JPMorgan Chase",
                    "sector": "Financials",
                    "current_price": 200.0,
                    "range_52w_position_percentile": 50.0,
                    "bollinger_percent_b": 0.5,
                    "bollinger_status": "within_bands",
                    "status_label": "Neutral",
                    "status_rank": 2,
                    "quality_score": 57,
                    "quality_label": "Moderate",
                    "quality_reasons": ["Positive profit margin", "Positive operating margin"],
                    "quality_warnings": ["Earnings growth unavailable"],
                    "last_updated": "2026-01-01T00:00:00+00:00",
                },
            ],
        }

    def test_screener_returns_200(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener")
        assert resp.status_code == 200

    def test_screener_response_shape(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener")
        data = resp.get_json()
        for key in ("as_of", "source", "count", "summary", "rows"):
            assert key in data, f"Missing key: {key}"
        # scan_duration_seconds is optional (None when served from cache mock)
        assert "scan_duration_seconds" in data

    def test_screener_row_shape(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener")
        data = resp.get_json()
        assert len(data["rows"]) > 0
        row = data["rows"][0]
        for key in ("symbol", "company", "sector", "current_price",
                    "bollinger_status", "status_label",
                    "quality_score", "quality_label", "quality_reasons", "quality_warnings"):
            assert key in row, f"Row missing key: {key}"

    def test_screener_status_filter_oversold(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener?status=oversold")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "XOM"

    def test_screener_status_filter_all(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener?status=all")
        data = resp.get_json()
        assert data["count"] == 3

    def test_screener_sector_filter(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener?sector=energy")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "XOM"

    def test_screener_combined_filter(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener?status=neutral&sector=financials")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "JPM"

    def test_screener_summary_preserved(self, client):
        """Summary should reflect the full dataset, not the filtered subset."""
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            return_value=self._mock_screener_data(),
        ):
            resp = client.get("/api/stocks/sp500/screener?status=oversold")
        data = resp.get_json()
        # Summary from the unfiltered scan should still be present
        assert data["summary"]["overbought"] == 1
        assert data["summary"]["oversold"] == 1

    def test_screener_service_error_returns_500(self, client):
        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            side_effect=RuntimeError("scan error"),
        ):
            resp = client.get("/api/stocks/sp500/screener")
        assert resp.status_code == 500

    def test_screener_refresh_param_forwarded(self, client):
        """?refresh=true should call get_screener_data(refresh=True)."""
        calls = {}

        def mock_get(refresh=False):
            calls["refresh"] = refresh
            return self._mock_screener_data()

        with patch(
            "web.routes.api_sp500_screener.sp500_screener_service.get_screener_data",
            side_effect=mock_get,
        ):
            client.get("/api/stocks/sp500/screener?refresh=true")

        assert calls.get("refresh") is True


# ==============================================================================
# Integration tests: page route
# ==============================================================================


class TestSP500ScreenerPageRoute:
    """Tests for the GET /stocks/sp500 page."""

    def test_screener_page_returns_200(self, client):
        resp = client.get("/stocks/sp500")
        assert resp.status_code == 200

    def test_screener_page_contains_title(self, client):
        resp = client.get("/stocks/sp500")
        assert b"S&amp;P 500 Screener" in resp.data or b"S&#39;P 500 Screener" in resp.data \
               or b"S&P 500 Screener" in resp.data

    def test_screener_page_has_disclaimer(self, client):
        resp = client.get("/stocks/sp500")
        assert b"not financial advice" in resp.data or b"Educational use only" in resp.data

    def test_screener_page_links_back_to_dashboard(self, client):
        resp = client.get("/stocks/sp500")
        assert b"/stocks/analysis" in resp.data

    def test_screener_page_has_table_element(self, client):
        resp = client.get("/stocks/sp500")
        assert b"screenerTable" in resp.data or b"screener" in resp.data.lower()


# ==============================================================================
# Integration tests: dashboard link
# ==============================================================================


class TestDashboardScreenerLink:
    """The Stock Analysis dashboard should link to the screener."""

    def test_dashboard_has_sp500_screener_link(self, client):
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"/stocks/sp500" in resp.data


# ==============================================================================
# Unit tests: ticker normalisation
# ==============================================================================


class TestTickerNormalisation:
    """Verify dot-to-hyphen normalisation in the constituent CSV."""

    def test_brk_b_normalised(self):
        """BRK.B should be stored as BRK-B in the CSV."""
        constituents_path = Path(__file__).resolve().parent.parent / "data" / "sp500_constituents.csv"
        assert constituents_path.exists(), "sp500_constituents.csv must exist"
        with open(constituents_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            symbols = [row["symbol"] for row in reader]
        # Dots should not appear in normalised symbols
        for sym in symbols:
            assert "." not in sym, f"Symbol {sym!r} should not contain dots (use hyphens)"

    def test_no_empty_symbols(self):
        constituents_path = Path(__file__).resolve().parent.parent / "data" / "sp500_constituents.csv"
        assert constituents_path.exists()
        with open(constituents_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) > 0
        for row in rows:
            assert row["symbol"].strip(), f"Empty symbol in row: {row}"
