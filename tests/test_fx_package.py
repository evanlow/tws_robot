"""Tests for the web.fx modular package (Phase 2)."""

import pytest

from web.fx.config import (
    DEFAULT_FX_DATA_MODE,
    RESEARCH_ONLY_STATUS,
    VALID_FX_DATA_MODES,
    get_fx_data_mode,
    is_demo_mode,
    is_live_research_mode,
)
from web.fx.data_sources import (
    get_live_fx_market_data,
    get_live_mas_policy_data,
    get_live_signal_summary,
    get_live_sneer_proxy_data,
)
from web.fx.demo_data import get_demo_market_watch
from web.fx.indicators import pct_change, simple_moving_average, z_score
from web.fx.macro_sources import get_live_macro_pressure
from web.fx.signal_engine import classify_bias, confidence_from_score
from web.fx_signal_service import get_fx_dashboard_data


# ---------------------------------------------------------------------------
# web.fx.config
# ---------------------------------------------------------------------------


class TestFxConfig:
    """Tests for web.fx.config module."""

    def test_valid_modes_contains_expected(self):
        assert "not_configured" in VALID_FX_DATA_MODES
        assert "demo" in VALID_FX_DATA_MODES
        assert "live_research" in VALID_FX_DATA_MODES

    def test_default_mode_is_not_configured(self):
        assert DEFAULT_FX_DATA_MODE == "not_configured"

    def test_research_only_status_keys(self):
        assert RESEARCH_ONLY_STATUS["execution_status"] == "Disabled"
        assert RESEARCH_ONLY_STATUS["live_trading"] == "Disabled"
        assert RESEARCH_ONLY_STATUS["order_placement"] == "Disabled"

    def test_get_fx_data_mode_default(self, monkeypatch):
        monkeypatch.delenv("FX_DATA_MODE", raising=False)
        assert get_fx_data_mode() == "not_configured"

    def test_get_fx_data_mode_demo(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "demo")
        assert get_fx_data_mode() == "demo"

    def test_get_fx_data_mode_live_research(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "live_research")
        assert get_fx_data_mode() == "live_research"

    def test_get_fx_data_mode_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "INVALID_MODE")
        assert get_fx_data_mode() == "not_configured"

    def test_get_fx_data_mode_mixed_case_valid(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "DEMO")
        assert get_fx_data_mode() == "demo"

    def test_is_demo_mode_true(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "demo")
        assert is_demo_mode() is True

    def test_is_demo_mode_false_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("FX_DATA_MODE", raising=False)
        assert is_demo_mode() is False

    def test_is_live_research_mode_true(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "live_research")
        assert is_live_research_mode() is True

    def test_is_live_research_mode_false_when_demo(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "demo")
        assert is_live_research_mode() is False


# ---------------------------------------------------------------------------
# web.fx.indicators
# ---------------------------------------------------------------------------


class TestPctChange:
    """Tests for indicators.pct_change."""

    def test_positive_change(self):
        result = pct_change(110.0, 100.0)
        assert result == pytest.approx(10.0)

    def test_negative_change(self):
        result = pct_change(90.0, 100.0)
        assert result == pytest.approx(-10.0)

    def test_zero_change(self):
        result = pct_change(100.0, 100.0)
        assert result == pytest.approx(0.0)

    def test_zero_previous_returns_none(self):
        assert pct_change(10.0, 0.0) is None

    def test_both_zero_returns_none(self):
        assert pct_change(0.0, 0.0) is None


class TestSimpleMovingAverage:
    """Tests for indicators.simple_moving_average."""

    def test_basic_average(self):
        result = simple_moving_average([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result == pytest.approx(4.0)

    def test_full_list(self):
        result = simple_moving_average([10.0, 20.0, 30.0], 3)
        assert result == pytest.approx(20.0)

    def test_window_one(self):
        result = simple_moving_average([5.0, 10.0, 15.0], 1)
        assert result == pytest.approx(15.0)

    def test_insufficient_values_returns_none(self):
        assert simple_moving_average([1.0, 2.0], 5) is None

    def test_empty_list_returns_none(self):
        assert simple_moving_average([], 3) is None

    def test_zero_window_returns_none(self):
        assert simple_moving_average([1.0, 2.0, 3.0], 0) is None

    def test_negative_window_returns_none(self):
        assert simple_moving_average([1.0, 2.0, 3.0], -1) is None


class TestZScore:
    """Tests for indicators.z_score."""

    def test_positive_z_score(self):
        result = z_score(110.0, 100.0, 10.0)
        assert result == pytest.approx(1.0)

    def test_negative_z_score(self):
        result = z_score(90.0, 100.0, 10.0)
        assert result == pytest.approx(-1.0)

    def test_zero_deviation_at_mean(self):
        result = z_score(100.0, 100.0, 10.0)
        assert result == pytest.approx(0.0)

    def test_zero_std_dev_returns_none(self):
        assert z_score(100.0, 100.0, 0.0) is None

    def test_negative_std_dev_returns_none(self):
        assert z_score(100.0, 100.0, -1.0) is None


# ---------------------------------------------------------------------------
# web.fx.signal_engine
# ---------------------------------------------------------------------------


class TestConfidenceFromScore:
    """Tests for signal_engine.confidence_from_score."""

    def test_full_score(self):
        assert confidence_from_score(6, 6) == 100

    def test_zero_score(self):
        assert confidence_from_score(0, 6) == 0

    def test_half_score(self):
        assert confidence_from_score(3, 6) == 50

    def test_score_above_max_clamped(self):
        assert confidence_from_score(10, 6) == 100

    def test_negative_score_clamped_to_zero(self):
        assert confidence_from_score(-1, 6) == 0

    def test_zero_max_score_returns_zero(self):
        assert confidence_from_score(3, 0) == 0

    def test_negative_max_score_returns_zero(self):
        assert confidence_from_score(3, -1) == 0


class TestClassifyBias:
    """Tests for signal_engine.classify_bias."""

    def test_positive_score_is_bullish(self):
        assert classify_bias(3) == "Bullish"

    def test_negative_score_is_bearish(self):
        assert classify_bias(-2) == "Bearish"

    def test_zero_score_is_neutral(self):
        assert classify_bias(0) == "Neutral"


# ---------------------------------------------------------------------------
# web.fx.data_sources and web.fx.macro_sources
# ---------------------------------------------------------------------------


class TestDataSourcePlaceholders:
    """Tests for placeholder live data sources."""

    def test_live_fx_market_data_unavailable(self):
        result = get_live_fx_market_data()
        assert result["available"] is False
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_live_sneer_proxy_unavailable(self):
        result = get_live_sneer_proxy_data()
        assert result["available"] is False

    def test_live_mas_policy_unavailable(self):
        result = get_live_mas_policy_data()
        assert result["available"] is False

    def test_live_signal_summary_unavailable(self):
        result = get_live_signal_summary()
        assert result["available"] is False
        assert "items" in result

    def test_live_macro_pressure_unavailable(self):
        result = get_live_macro_pressure()
        assert result["available"] is False
        assert "items" in result


class TestDemoMarketWatch:
    """Tests for demo market watch data."""

    def test_signal_bias_uses_supported_labels(self):
        market_watch = get_demo_market_watch()
        allowed_labels = {"Long SGD", "Short SGD", "Neutral"}
        assert all(item["signal_bias"] in allowed_labels for item in market_watch["items"])


# ---------------------------------------------------------------------------
# live_research mode integration (via fx_signal_service)
# ---------------------------------------------------------------------------


class TestFxServiceLiveResearchMode:
    """Tests for safe fallback when FX_DATA_MODE=live_research."""

    @pytest.fixture(autouse=True)
    def set_live_research_mode(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "live_research")

    def test_does_not_crash(self):
        data = get_fx_dashboard_data()
        assert isinstance(data, dict)

    def test_returns_all_sections(self):
        data = get_fx_dashboard_data()
        for key in ("data_status", "market_watch", "sneer_proxy", "mas_policy", "macro_pressure", "signal_summary"):
            assert key in data

    def test_execution_statuses_disabled(self):
        data = get_fx_dashboard_data()
        status = data["data_status"]
        assert status["execution_status"] == "Disabled"
        assert status["live_trading"] == "Disabled"
        assert status["order_placement"] == "Disabled"

    def test_all_sections_show_unavailable(self):
        data = get_fx_dashboard_data()
        assert data["market_watch"]["available"] is False
        assert data["sneer_proxy"]["available"] is False
        assert data["mas_policy"]["available"] is False
        assert data["macro_pressure"]["available"] is False
        assert data["signal_summary"]["available"] is False


# ---------------------------------------------------------------------------
# Invalid FX_DATA_MODE safe fallback
# ---------------------------------------------------------------------------


class TestInvalidFxDataModeFallback:
    """Tests that an invalid FX_DATA_MODE safely falls back to not_configured."""

    @pytest.fixture(autouse=True)
    def set_invalid_mode(self, monkeypatch):
        monkeypatch.setenv("FX_DATA_MODE", "totally_invalid")

    def test_falls_back_to_not_configured(self):
        assert get_fx_data_mode() == "not_configured"

    def test_dashboard_does_not_crash(self):
        data = get_fx_dashboard_data()
        assert isinstance(data, dict)

    def test_execution_statuses_disabled(self):
        data = get_fx_dashboard_data()
        status = data["data_status"]
        assert status["execution_status"] == "Disabled"
        assert status["live_trading"] == "Disabled"
        assert status["order_placement"] == "Disabled"
