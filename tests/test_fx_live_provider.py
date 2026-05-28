"""Tests for the Phase 3 FX live data ingestion: config provider, yfinance provider,
service integration, and route integration.

All yfinance calls are mocked so tests do not require internet access.
"""

from __future__ import annotations

import pandas as pd
import pytest

from web.fx.config import (
    DEFAULT_FX_PROVIDER,
    DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS,
    FX_MARKET_WATCH_PAIRS,
    VALID_FX_PROVIDERS,
    get_fx_provider,
    get_fx_provider_timeout_seconds,
)
from web.fx.data_sources import get_live_fx_market_data
from web.fx.providers.yfinance_provider import (
    _classify_generic_bias,
    _classify_sgd_bias,
    _compute_signal_bias,
    fetch_fx_market_watch_items,
)
from web.fx_signal_service import get_fx_dashboard_data

from web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history(prices: list[float]) -> pd.DataFrame:
    """Return a DataFrame mimicking a yfinance Ticker.history() result."""
    idx = pd.date_range(end="2026-01-10", periods=len(prices), freq="B", tz="UTC")
    return pd.DataFrame({"Close": prices}, index=idx)


def _mock_ticker_factory(symbol_prices: dict[str, list[float]]):
    """Return a callable that creates mock Ticker objects for the given symbols."""
    from unittest.mock import MagicMock

    def create_ticker(symbol):
        mock = MagicMock()
        prices = symbol_prices.get(symbol, [])
        mock.history.return_value = _make_history(prices) if len(prices) >= 2 else pd.DataFrame()
        return mock

    return create_ticker


# ---------------------------------------------------------------------------
# Config: provider helpers
# ---------------------------------------------------------------------------


class TestFxProviderConfig:
    """Tests for get_fx_provider() and get_fx_provider_timeout_seconds()."""

    def test_default_provider_constant(self):
        assert DEFAULT_FX_PROVIDER == "yfinance"

    def test_valid_providers_contains_yfinance(self):
        assert "yfinance" in VALID_FX_PROVIDERS

    def test_get_fx_provider_default(self, monkeypatch):
        monkeypatch.delenv("FX_PROVIDER", raising=False)
        assert get_fx_provider() == "yfinance"

    def test_get_fx_provider_valid(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER", "yfinance")
        assert get_fx_provider() == "yfinance"

    def test_get_fx_provider_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER", "totally_unknown_provider")
        assert get_fx_provider() == DEFAULT_FX_PROVIDER

    def test_get_fx_provider_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER", "YFINANCE")
        assert get_fx_provider() == "yfinance"

    def test_get_fx_provider_whitespace_stripped(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER", "  yfinance  ")
        assert get_fx_provider() == "yfinance"

    def test_timeout_default(self, monkeypatch):
        monkeypatch.delenv("FX_PROVIDER_TIMEOUT_SECONDS", raising=False)
        assert get_fx_provider_timeout_seconds() == DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS

    def test_timeout_valid_integer(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER_TIMEOUT_SECONDS", "30")
        assert get_fx_provider_timeout_seconds() == 30

    def test_timeout_invalid_string_falls_back(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER_TIMEOUT_SECONDS", "not_a_number")
        assert get_fx_provider_timeout_seconds() == DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS

    def test_timeout_zero_falls_back(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER_TIMEOUT_SECONDS", "0")
        assert get_fx_provider_timeout_seconds() == DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS

    def test_timeout_negative_falls_back(self, monkeypatch):
        monkeypatch.setenv("FX_PROVIDER_TIMEOUT_SECONDS", "-5")
        assert get_fx_provider_timeout_seconds() == DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Config: FX_MARKET_WATCH_PAIRS
# ---------------------------------------------------------------------------


class TestFxMarketWatchPairsConfig:
    """Tests for the FX_MARKET_WATCH_PAIRS constant."""

    def test_contains_expected_pairs(self):
        pair_names = [p["pair"] for p in FX_MARKET_WATCH_PAIRS]
        for expected in ["USD/SGD", "EUR/SGD", "GBP/SGD", "JPY/SGD", "AUD/SGD", "USD/CNH", "USD/JPY", "EUR/USD"]:
            assert expected in pair_names

    def test_all_entries_have_pair_and_symbol(self):
        for entry in FX_MARKET_WATCH_PAIRS:
            assert "pair" in entry
            assert "symbol" in entry
            assert entry["symbol"]  # non-empty


# ---------------------------------------------------------------------------
# Provider: signal bias classification
# ---------------------------------------------------------------------------


class TestSignalBiasClassification:
    """Tests for _classify_sgd_bias, _classify_generic_bias, _compute_signal_bias."""

    # SGD bias
    def test_sgd_bias_strong_up_is_short_sgd(self):
        assert _classify_sgd_bias(1.0) == "Short SGD"

    def test_sgd_bias_exactly_at_threshold_up_is_neutral(self):
        # boundary: > 0.25 required for Short SGD
        assert _classify_sgd_bias(0.25) == "Neutral"

    def test_sgd_bias_above_threshold_up(self):
        assert _classify_sgd_bias(0.26) == "Short SGD"

    def test_sgd_bias_strong_down_is_long_sgd(self):
        assert _classify_sgd_bias(-1.0) == "Long SGD"

    def test_sgd_bias_below_threshold_down(self):
        assert _classify_sgd_bias(-0.26) == "Long SGD"

    def test_sgd_bias_small_change_is_neutral(self):
        assert _classify_sgd_bias(0.10) == "Neutral"

    def test_sgd_bias_zero_is_neutral(self):
        assert _classify_sgd_bias(0.0) == "Neutral"

    def test_sgd_bias_none_is_neutral(self):
        assert _classify_sgd_bias(None) == "Neutral"

    # Generic bias
    def test_generic_bias_up_is_bullish(self):
        assert _classify_generic_bias(0.5) == "Bullish"

    def test_generic_bias_down_is_bearish(self):
        assert _classify_generic_bias(-0.5) == "Bearish"

    def test_generic_bias_small_is_neutral(self):
        assert _classify_generic_bias(0.10) == "Neutral"

    def test_generic_bias_none_is_neutral(self):
        assert _classify_generic_bias(None) == "Neutral"

    # Dispatcher
    def test_compute_bias_uses_sgd_labels_for_sgd_pair(self):
        assert _compute_signal_bias("USD/SGD", 0.5) == "Short SGD"
        assert _compute_signal_bias("AUD/SGD", -0.5) == "Long SGD"
        assert _compute_signal_bias("EUR/SGD", 0.0) == "Neutral"

    def test_compute_bias_uses_generic_labels_for_non_sgd_pair(self):
        assert _compute_signal_bias("EUR/USD", 0.5) == "Bullish"
        assert _compute_signal_bias("USD/JPY", -0.5) == "Bearish"
        assert _compute_signal_bias("USD/CNH", 0.0) == "Neutral"


# ---------------------------------------------------------------------------
# Provider: fetch_fx_market_watch_items (mocked yfinance)
# ---------------------------------------------------------------------------


class TestFetchFxMarketWatchItems:
    """Tests for fetch_fx_market_watch_items with mocked yfinance."""

    PAIRS = [
        {"pair": "USD/SGD", "symbol": "USDSGD=X"},
        {"pair": "EUR/USD", "symbol": "EURUSD=X"},
    ]

    def _patch_ticker(self, monkeypatch, symbol_prices: dict[str, list[float]]):
        monkeypatch.setattr(
            "web.fx.providers.yfinance_provider.yf.Ticker",
            _mock_ticker_factory(symbol_prices),
        )

    def test_returns_available_true_with_usable_data(self, monkeypatch):
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is True
        assert len(result["items"]) == 2

    def test_maps_symbols_to_pair_names(self, monkeypatch):
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        pair_names = [item["pair"] for item in result["items"]]
        assert "USD/SGD" in pair_names
        assert "EUR/USD" in pair_names

    def test_computes_daily_change_pct(self, monkeypatch):
        # last=1.350, prev=1.340 → ~0.746%
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        usd_sgd = next(i for i in result["items"] if i["pair"] == "USD/SGD")
        # pct_change(1.350, 1.340) ≈ 0.7463
        assert usd_sgd["daily_change_pct"] == pytest.approx(0.7463, abs=0.001)

    def test_computes_weekly_change_pct_over_multiple_days(self, monkeypatch):
        # oldest=1.300, newest=1.340 → ~3.077%
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.300, 1.310, 1.320, 1.330, 1.340],
            "EURUSD=X": [1.070, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        usd_sgd = next(i for i in result["items"] if i["pair"] == "USD/SGD")
        # pct_change(1.340, 1.300) ≈ 3.077
        assert usd_sgd["weekly_change_pct"] == pytest.approx(3.077, abs=0.01)

    def test_item_contains_expected_fields(self, monkeypatch):
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        for item in result["items"]:
            for field in ("pair", "last_price", "daily_change_pct", "weekly_change_pct",
                          "signal_bias", "notes", "data_source", "as_of"):
                assert field in item, f"Missing field: {field}"

    def test_data_source_is_yfinance(self, monkeypatch):
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        for item in result["items"]:
            assert item["data_source"] == "yfinance"

    def test_sgd_pair_uses_sgd_bias_labels(self, monkeypatch):
        # 1.300 → 1.340: +3% weekly → Short SGD
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.300, 1.310, 1.320, 1.330, 1.340],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        usd_sgd = next(i for i in result["items"] if i["pair"] == "USD/SGD")
        assert usd_sgd["signal_bias"] in ("Long SGD", "Short SGD", "Neutral")
        assert usd_sgd["signal_bias"] == "Short SGD"

    def test_non_sgd_pair_uses_generic_bias_labels(self, monkeypatch):
        # 1.075 → 1.080: +0.47% → Bullish
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [1.075, 1.080],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        eur_usd = next(i for i in result["items"] if i["pair"] == "EUR/USD")
        assert eur_usd["signal_bias"] in ("Bullish", "Bearish", "Neutral")

    def test_handles_missing_pair_data_gracefully(self, monkeypatch):
        # EURUSD returns empty history → should be skipped, not crash
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            "EURUSD=X": [],  # empty → empty DataFrame → skipped
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is True
        pair_names = [item["pair"] for item in result["items"]]
        assert "USD/SGD" in pair_names
        assert "EUR/USD" not in pair_names

    def test_handles_provider_exception_gracefully(self, monkeypatch):
        from unittest.mock import MagicMock

        def failing_ticker(symbol):
            m = MagicMock()
            m.history.side_effect = RuntimeError("network error")
            return m

        monkeypatch.setattr("web.fx.providers.yfinance_provider.yf.Ticker", failing_ticker)
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is False
        assert result["items"] == []

    def test_returns_available_false_when_all_pairs_fail(self, monkeypatch):
        self._patch_ticker(monkeypatch, {})  # no prices for any symbol
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is False
        assert "unavailable" in result["message"].lower()

    def test_returns_available_false_when_yfinance_not_installed(self, monkeypatch):
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", False)
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is False
        assert result["items"] == []

    def test_partial_failure_still_returns_available(self, monkeypatch):
        """Dashboard stays available even when some pairs fail."""
        self._patch_ticker(monkeypatch, {
            "USDSGD=X": [1.340, 1.350],
            # EURUSD=X not in dict → empty history → skipped
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is True
        assert len(result["items"]) == 1
        assert result["items"][0]["pair"] == "USD/SGD"

    def test_fetches_pairs_concurrently(self, monkeypatch):
        import time

        def slow_fetch_pair_data(symbol, pair, timeout):
            time.sleep(0.2)
            return {
                "pair": pair,
                "last_price": 1.0,
                "daily_change_pct": 0.0,
                "weekly_change_pct": 0.0,
                "signal_bias": "Neutral",
                "notes": "Live/delayed research data from yfinance",
                "data_source": "yfinance",
                "as_of": "2026-01-10T00:00:00+00:00",
            }

        monkeypatch.setattr(
            "web.fx.providers.yfinance_provider._fetch_pair_data",
            slow_fetch_pair_data,
        )

        start = time.perf_counter()
        result = fetch_fx_market_watch_items(self.PAIRS)
        elapsed = time.perf_counter() - start

        assert result["available"] is True
        assert len(result["items"]) == 2
        assert elapsed < 0.35


# ---------------------------------------------------------------------------
# Service integration: FX_DATA_MODE=live_research with mocked provider
# ---------------------------------------------------------------------------


class TestFxServiceLiveResearchWithData:
    """Tests for get_fx_dashboard_data() with a mocked yfinance that returns data."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "live_research")
        monkeypatch.setenv("FX_PROVIDER", "yfinance")
        monkeypatch.setattr(
            "web.fx.providers.yfinance_provider.yf.Ticker",
            _mock_ticker_factory({
                symbol: [1.300 + i * 0.005, 1.310 + i * 0.005]
                for i, symbol in enumerate(p["symbol"] for p in FX_MARKET_WATCH_PAIRS)
            }),
        )

    def test_does_not_crash(self):
        data = get_fx_dashboard_data()
        assert isinstance(data, dict)

    def test_market_watch_is_available(self):
        data = get_fx_dashboard_data()
        assert data["market_watch"]["available"] is True

    def test_market_watch_items_have_required_fields(self):
        data = get_fx_dashboard_data()
        for item in data["market_watch"]["items"]:
            for field in ("pair", "last_price", "daily_change_pct", "weekly_change_pct",
                          "signal_bias", "notes", "data_source", "as_of"):
                assert field in item

    def test_other_sections_remain_unavailable_placeholders(self):
        data = get_fx_dashboard_data()
        assert data["sneer_proxy"]["available"] is False
        assert data["mas_policy"]["available"] is False
        assert data["macro_pressure"]["available"] is False
        assert data["signal_summary"]["available"] is False

    def test_execution_statuses_remain_disabled(self):
        data = get_fx_dashboard_data()
        status = data["data_status"]
        assert status["execution_status"] == "Disabled"
        assert status["live_trading"] == "Disabled"
        assert status["order_placement"] == "Disabled"

    def test_data_mode_label(self):
        data = get_fx_dashboard_data()
        assert data["data_status"]["data_mode"] == "Live Research"


# ---------------------------------------------------------------------------
# Route integration: /fx/ with mocked live data
# ---------------------------------------------------------------------------


class TestFxResearchRouteLiveResearchWithData:
    """Integration tests for /fx/ with live_research mode and mocked yfinance data."""

    @pytest.fixture
    def live_data_client(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "live_research")
        monkeypatch.setenv("FX_PROVIDER", "yfinance")
        monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
        monkeypatch.setattr(
            "web.fx.providers.yfinance_provider.yf.Ticker",
            _mock_ticker_factory({
                "USDSGD=X": [1.340, 1.350],
                "EURSGD=X": [1.460, 1.455],
                "GBPSGD=X": [1.720, 1.722],
                "JPYSGD=X": [0.0088, 0.0089],
                "AUDSGD=X": [0.880, 0.875],
                "USDCNH=X": [7.220, 7.230],
                "USDJPY=X": [151.0, 151.5],
                "EURUSD=X": [1.078, 1.082],
            }),
        )
        app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
        with app.test_client() as c:
            yield c

    def test_route_returns_200(self, live_data_client):
        resp = live_data_client.get("/fx/")
        assert resp.status_code == 200

    def test_rendered_html_includes_live_pairs(self, live_data_client):
        resp = live_data_client.get("/fx/")
        html = resp.data.decode()
        for pair in ["USD/SGD", "EUR/SGD", "GBP/SGD", "USD/JPY", "EUR/USD"]:
            assert pair in html

    def test_rendered_html_includes_data_source(self, live_data_client):
        resp = live_data_client.get("/fx/")
        html = resp.data.decode()
        assert "yfinance" in html

    def test_rendered_html_includes_live_research_label(self, live_data_client):
        resp = live_data_client.get("/fx/")
        html = resp.data.decode()
        assert "Live Research" in html

    def test_no_order_ui_elements(self, live_data_client):
        resp = live_data_client.get("/fx/")
        html = resp.data.decode()
        assert "/api/orders" not in html
        assert "cancelOrder(" not in html
        assert 'type="submit"' not in html.lower()

    def test_execution_status_disabled_in_html(self, live_data_client):
        resp = live_data_client.get("/fx/")
        html = resp.data.decode()
        assert "Disabled" in html
