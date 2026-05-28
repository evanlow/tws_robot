"""Phase 3B: focused success-path tests for the yfinance FX provider.

Tests verify that the yfinance provider correctly transforms valid provider
data into FX Market Watch dashboard rows, computes percentage changes and
signal biases, handles partial/total failures gracefully, and preserves
research-only safety.

All yfinance calls are mocked so tests do not require internet access.
"""

from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import MagicMock

from web.fx.providers.yfinance_provider import fetch_fx_market_watch_items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history(prices: list[float]) -> pd.DataFrame:
    """Return a DataFrame mimicking a yfinance Ticker.history() result."""
    if len(prices) < 2:
        return pd.DataFrame()
    idx = pd.date_range(end="2026-01-10", periods=len(prices), freq="B", tz="UTC")
    return pd.DataFrame({"Close": prices}, index=idx)


class FakeTicker:
    """Fake Ticker that returns pre-configured price history."""

    def __init__(self, symbol: str, prices: list[float]) -> None:
        self._prices = prices

    def history(self, period: str = "7d", timeout: int = 10) -> pd.DataFrame:
        return _make_history(self._prices)


def _patch_ticker(monkeypatch, symbol_prices: dict[str, list[float]]) -> None:
    """Monkeypatch yf.Ticker to return controlled history per symbol."""

    def create_ticker(symbol: str) -> FakeTicker:
        return FakeTicker(symbol, symbol_prices.get(symbol, []))

    monkeypatch.setattr("web.fx.providers.yfinance_provider.yf.Ticker", create_ticker)
    monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", True)


# ---------------------------------------------------------------------------
# 1. Success-path: result shape and field presence
# ---------------------------------------------------------------------------


class TestSuccessPath:
    """Provider returns well-formed items when yfinance returns usable data."""

    PAIRS = [
        {"pair": "USD/SGD", "symbol": "USDSGD=X"},
        {"pair": "EUR/USD", "symbol": "EURUSD=X"},
    ]

    def test_available_true_when_data_returned(self, monkeypatch):
        _patch_ticker(monkeypatch, {
            "USDSGD=X": [1.3400, 1.3420, 1.3450, 1.3480, 1.3500],
            "EURUSD=X": [1.0780, 1.0790, 1.0800, 1.0810, 1.0812],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is True

    def test_items_count_matches_valid_pairs(self, monkeypatch):
        _patch_ticker(monkeypatch, {
            "USDSGD=X": [1.3400, 1.3420, 1.3450, 1.3480, 1.3500],
            "EURUSD=X": [1.0780, 1.0790, 1.0800, 1.0810, 1.0812],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert len(result["items"]) == 2

    def test_each_item_has_all_required_fields(self, monkeypatch):
        _patch_ticker(monkeypatch, {
            "USDSGD=X": [1.3400, 1.3420, 1.3450, 1.3480, 1.3500],
            "EURUSD=X": [1.0780, 1.0790, 1.0800, 1.0810, 1.0812],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        for item in result["items"]:
            for field in ("pair", "last_price", "daily_change_pct", "weekly_change_pct",
                          "signal_bias", "notes", "data_source", "as_of"):
                assert field in item, f"Missing field: {field}"

    def test_last_price_matches_final_close(self, monkeypatch):
        _patch_ticker(monkeypatch, {
            "USDSGD=X": [1.3400, 1.3420, 1.3450, 1.3480, 1.3500],
            "EURUSD=X": [1.0780, 1.0790, 1.0800, 1.0810, 1.0812],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        usd_sgd = next(i for i in result["items"] if i["pair"] == "USD/SGD")
        assert usd_sgd["last_price"] == pytest.approx(1.3500, abs=1e-5)

    def test_data_source_is_yfinance(self, monkeypatch):
        _patch_ticker(monkeypatch, {
            "USDSGD=X": [1.3400, 1.3420, 1.3450, 1.3480, 1.3500],
            "EURUSD=X": [1.0780, 1.0790, 1.0800, 1.0810, 1.0812],
        })
        result = fetch_fx_market_watch_items(self.PAIRS)
        for item in result["items"]:
            assert item["data_source"] == "yfinance"


# ---------------------------------------------------------------------------
# 2. Percentage calculations
# ---------------------------------------------------------------------------


class TestPercentageCalculations:
    """Provider computes daily and weekly percentage changes correctly."""

    PAIR = [{"pair": "USD/SGD", "symbol": "USDSGD=X"}]

    # Issue spec prices:
    #   first_close    = 1.3400
    #   previous_close = 1.3480
    #   last_close     = 1.3500
    SPEC_PRICES = [1.3400, 1.3420, 1.3450, 1.3480, 1.3500]

    def test_daily_change_pct_spec_values(self, monkeypatch):
        """daily_change_pct = (1.3500 - 1.3480) / 1.3480 * 100 ≈ 0.1484%."""
        _patch_ticker(monkeypatch, {"USDSGD=X": self.SPEC_PRICES})
        result = fetch_fx_market_watch_items(self.PAIR)
        item = result["items"][0]
        expected = ((1.3500 - 1.3480) / 1.3480) * 100
        assert item["daily_change_pct"] == pytest.approx(expected, abs=0.001)

    def test_weekly_change_pct_spec_values(self, monkeypatch):
        """weekly_change_pct = (1.3500 - 1.3400) / 1.3400 * 100 ≈ 0.7463%."""
        _patch_ticker(monkeypatch, {"USDSGD=X": self.SPEC_PRICES})
        result = fetch_fx_market_watch_items(self.PAIR)
        item = result["items"][0]
        expected = ((1.3500 - 1.3400) / 1.3400) * 100
        assert item["weekly_change_pct"] == pytest.approx(expected, abs=0.001)

    def test_daily_and_weekly_differ_with_five_prices(self, monkeypatch):
        """With 5 prices the daily and weekly calculations diverge."""
        _patch_ticker(monkeypatch, {"USDSGD=X": self.SPEC_PRICES})
        result = fetch_fx_market_watch_items(self.PAIR)
        item = result["items"][0]
        assert item["daily_change_pct"] != item["weekly_change_pct"]


# ---------------------------------------------------------------------------
# 3. Signal bias classification via the public API
# ---------------------------------------------------------------------------


class TestSignalBiasViaPublicAPI:
    """Signal bias rules verified through fetch_fx_market_watch_items() output.

    SGD pairs:
        weekly_change_pct > +0.25%  -> Short SGD
        weekly_change_pct < -0.25%  -> Long SGD
        otherwise                   -> Neutral

    Non-SGD pairs:
        weekly_change_pct > +0.25%  -> Bullish
        weekly_change_pct < -0.25%  -> Bearish
        otherwise                   -> Neutral
    """

    # USD/SGD – prices that yield weekly > +0.25%
    # first=1.3400, last=1.3440 → (0.004/1.3400)*100 ≈ +0.2985%
    _USD_SGD_SHORT = [1.3400, 1.3410, 1.3420, 1.3430, 1.3440]

    # USD/SGD – prices that yield weekly < -0.25%
    # first=1.3440, last=1.3400 → (-0.004/1.3440)*100 ≈ -0.2976%
    _USD_SGD_LONG = [1.3440, 1.3430, 1.3420, 1.3410, 1.3400]

    # USD/SGD – small move (stays within ±0.25%)
    _USD_SGD_NEUTRAL = [1.3400, 1.3400, 1.3400, 1.3400, 1.3401]

    # EUR/USD – prices that yield weekly > +0.25%
    # first=1.0780, last=1.0812 → (0.0032/1.0780)*100 ≈ +0.2969%
    _EUR_USD_BULLISH = [1.0780, 1.0790, 1.0800, 1.0810, 1.0812]

    # EUR/USD – prices that yield weekly < -0.25%
    # first=1.0812, last=1.0780 → (-0.0032/1.0812)*100 ≈ -0.2960%
    _EUR_USD_BEARISH = [1.0812, 1.0810, 1.0800, 1.0790, 1.0780]

    # EUR/USD – small move
    _EUR_USD_NEUTRAL = [1.0780, 1.0780, 1.0780, 1.0780, 1.0781]

    def _fetch_bias(self, monkeypatch, pair: str, symbol: str, prices: list[float]) -> str:
        _patch_ticker(monkeypatch, {symbol: prices})
        result = fetch_fx_market_watch_items([{"pair": pair, "symbol": symbol}])
        assert result["available"] is True
        return result["items"][0]["signal_bias"]

    def test_usd_sgd_weekly_positive_is_short_sgd(self, monkeypatch):
        bias = self._fetch_bias(monkeypatch, "USD/SGD", "USDSGD=X", self._USD_SGD_SHORT)
        assert bias == "Short SGD"

    def test_usd_sgd_weekly_negative_is_long_sgd(self, monkeypatch):
        bias = self._fetch_bias(monkeypatch, "USD/SGD", "USDSGD=X", self._USD_SGD_LONG)
        assert bias == "Long SGD"

    def test_usd_sgd_small_move_is_neutral(self, monkeypatch):
        bias = self._fetch_bias(monkeypatch, "USD/SGD", "USDSGD=X", self._USD_SGD_NEUTRAL)
        assert bias == "Neutral"

    def test_eur_usd_weekly_positive_is_bullish(self, monkeypatch):
        bias = self._fetch_bias(monkeypatch, "EUR/USD", "EURUSD=X", self._EUR_USD_BULLISH)
        assert bias == "Bullish"

    def test_eur_usd_weekly_negative_is_bearish(self, monkeypatch):
        bias = self._fetch_bias(monkeypatch, "EUR/USD", "EURUSD=X", self._EUR_USD_BEARISH)
        assert bias == "Bearish"

    def test_eur_usd_small_move_is_neutral(self, monkeypatch):
        bias = self._fetch_bias(monkeypatch, "EUR/USD", "EURUSD=X", self._EUR_USD_NEUTRAL)
        assert bias == "Neutral"


# ---------------------------------------------------------------------------
# 4. Partial pair failure
# ---------------------------------------------------------------------------


class TestPartialPairFailure:
    """Dashboard stays available when some pairs fail; valid pairs are kept."""

    PAIRS = [
        {"pair": "USD/SGD", "symbol": "USDSGD=X"},   # valid
        {"pair": "EUR/USD", "symbol": "EURUSD=X"},   # empty DataFrame
        {"pair": "GBP/USD", "symbol": "GBPUSD=X"},   # raises exception
    ]

    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        """Patch yf.Ticker so each symbol has a different failure mode."""

        def create_ticker(symbol):
            if symbol == "USDSGD=X":
                return FakeTicker(symbol, [1.3400, 1.3420, 1.3450, 1.3480, 1.3500])
            if symbol == "EURUSD=X":
                # empty DataFrame → skipped
                return FakeTicker(symbol, [])
            # GBPUSD=X raises an exception
            mock = MagicMock()
            mock.history.side_effect = RuntimeError("network error")
            return mock

        monkeypatch.setattr("web.fx.providers.yfinance_provider.yf.Ticker", create_ticker)
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", True)

    def test_result_is_available(self):
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is True

    def test_only_valid_pair_is_returned(self):
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert len(result["items"]) == 1

    def test_valid_pair_identity(self):
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["items"][0]["pair"] == "USD/SGD"

    def test_failed_pairs_not_in_items(self):
        result = fetch_fx_market_watch_items(self.PAIRS)
        pair_names = [i["pair"] for i in result["items"]]
        assert "EUR/USD" not in pair_names
        assert "GBP/USD" not in pair_names

    def test_order_preserved_when_multiple_valid_pairs(self, monkeypatch):
        """Items are returned in the original configured order."""

        def create_ticker(symbol):
            prices = {
                "USDSGD=X": [1.3400, 1.3500],
                "EURUSD=X": [1.0780, 1.0812],
            }.get(symbol, [])
            return FakeTicker(symbol, prices)

        monkeypatch.setattr("web.fx.providers.yfinance_provider.yf.Ticker", create_ticker)
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", True)

        pairs = [
            {"pair": "USD/SGD", "symbol": "USDSGD=X"},
            {"pair": "EUR/USD", "symbol": "EURUSD=X"},
        ]
        result = fetch_fx_market_watch_items(pairs)
        assert result["available"] is True
        assert result["items"][0]["pair"] == "USD/SGD"
        assert result["items"][1]["pair"] == "EUR/USD"


# ---------------------------------------------------------------------------
# 5. Total provider failure
# ---------------------------------------------------------------------------


class TestTotalProviderFailure:
    """When all pairs fail the provider returns a safe unavailable response."""

    PAIRS = [
        {"pair": "USD/SGD", "symbol": "USDSGD=X"},
        {"pair": "EUR/USD", "symbol": "EURUSD=X"},
    ]

    def test_available_false_when_all_empty(self, monkeypatch):
        _patch_ticker(monkeypatch, {})  # every symbol → empty DataFrame
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is False

    def test_items_empty_on_total_failure(self, monkeypatch):
        _patch_ticker(monkeypatch, {})
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["items"] == []

    def test_message_contains_no_usable_data(self, monkeypatch):
        _patch_ticker(monkeypatch, {})
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert "no usable data" in result["message"].lower()

    def test_available_false_when_all_raise_exceptions(self, monkeypatch):
        def failing_ticker(symbol):
            mock = MagicMock()
            mock.history.side_effect = RuntimeError("timeout")
            return mock

        monkeypatch.setattr("web.fx.providers.yfinance_provider.yf.Ticker", failing_ticker)
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", True)

        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is False
        assert result["items"] == []


# ---------------------------------------------------------------------------
# 6. yfinance package unavailable
# ---------------------------------------------------------------------------


class TestYfinanceUnavailable:
    """When yfinance is not installed the provider returns a safe response."""

    PAIRS = [{"pair": "USD/SGD", "symbol": "USDSGD=X"}]

    def test_available_false(self, monkeypatch):
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", False)
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["available"] is False

    def test_items_empty(self, monkeypatch):
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", False)
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert result["items"] == []

    def test_message_mentions_package_not_installed(self, monkeypatch):
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", False)
        result = fetch_fx_market_watch_items(self.PAIRS)
        assert "yfinance package is not installed" in result["message"]


# ---------------------------------------------------------------------------
# 7 & 8. Route rendering with mocked live data + research-only safety
# ---------------------------------------------------------------------------


class TestFxRouteWithMockedLiveData:
    """Route /fx/ renders correctly with mocked live yfinance data."""

    @pytest.fixture
    def live_client(self, monkeypatch):
        from web import create_app

        monkeypatch.setenv("FX_DATA_MODE", "live_research")
        monkeypatch.setenv("FX_PROVIDER", "yfinance")
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh", lambda self: None
        )
        monkeypatch.setattr(
            "web.fx.providers.yfinance_provider.yf.Ticker",
            lambda symbol: FakeTicker(symbol, {
                "USDSGD=X": [1.3400, 1.3420, 1.3450, 1.3480, 1.3500],
                "EURSGD=X": [1.4600, 1.4580, 1.4570, 1.4560, 1.4550],
                "GBPSGD=X": [1.7200, 1.7210, 1.7220, 1.7215, 1.7220],
                "JPYSGD=X": [0.0088, 0.0088, 0.0089, 0.0089, 0.0089],
                "AUDSGD=X": [0.8800, 0.8790, 0.8780, 0.8760, 0.8750],
                "USDCNH=X": [7.2200, 7.2250, 7.2280, 7.2290, 7.2300],
                "USDJPY=X": [151.00, 151.20, 151.40, 151.30, 151.50],
                "EURUSD=X": [1.0780, 1.0790, 1.0800, 1.0810, 1.0812],
            }.get(symbol, [1.0000, 1.0010])),
        )
        monkeypatch.setattr("web.fx.providers.yfinance_provider._YFINANCE_AVAILABLE", True)
        app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
        with app.test_client() as c:
            yield c

    def test_route_returns_200(self, live_client):
        resp = live_client.get("/fx/")
        assert resp.status_code == 200

    def test_html_contains_live_pair_usd_sgd(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert "USD/SGD" in html

    def test_html_contains_data_source_yfinance(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert "yfinance" in html

    def test_html_contains_live_research_label(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert "Live Research" in html

    def test_no_order_submission_endpoint_in_html(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert "/api/orders" not in html

    def test_no_cancel_order_call_in_html(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert "cancelOrder(" not in html

    def test_no_submit_button_in_html(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert 'type="submit"' not in html.lower()

    def test_execution_status_disabled(self, live_client):
        html = live_client.get("/fx/").data.decode()
        assert "Disabled" in html

    def test_live_trading_disabled(self, live_client):
        from web.fx_signal_service import get_fx_dashboard_data

        # Verify at service level that execution fields are always Disabled
        data = get_fx_dashboard_data()
        status = data["data_status"]
        assert status["execution_status"] == "Disabled"
        assert status["live_trading"] == "Disabled"
        assert status["order_placement"] == "Disabled"
