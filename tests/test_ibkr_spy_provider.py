"""Tests for the IBKR-first SPY price provider with yfinance fallback."""

import pytest
from unittest.mock import MagicMock, patch


def _make_bridge(connected=True, spy_quote=None):
    """Return a mock TWSBridge."""
    bridge = MagicMock()
    bridge.is_connected = connected
    bridge.subscribe_market_data = MagicMock()
    bridge.get_latest_market_data_quote = MagicMock(return_value=spy_quote)
    return bridge


def _yfinance_payload():
    return {
        "open": 500.0,
        "current": 501.0,
        "spy_open": 500.0,
        "spy_current": 501.0,
        "vix_open": 15.0,
        "vix_current": 14.5,
        "source": "yfinance",
    }


@pytest.fixture(autouse=True)
def _patch_yfinance(monkeypatch):
    """Patch spy_vix_price_from_yfinance so tests don't hit the network."""
    from web import vix_market_data
    monkeypatch.setattr(
        vix_market_data,
        "spy_vix_price_from_yfinance",
        lambda: _yfinance_payload(),
    )
    monkeypatch.setattr(
        vix_market_data,
        "_ticker_open_last_yfinance",
        lambda: (15.0, 14.5),
    )


@pytest.mark.unit
def test_uses_ibkr_when_connected_and_quote_complete():
    """When IBKR is connected and returns a full SPY quote, use it."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    spy_quote = {"open": 520.0, "last": 521.5, "market_data_type": "LIVE"}
    bridge = _make_bridge(connected=True, spy_quote=spy_quote)
    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: bridge)

    result = provider()

    assert result["open"] == 520.0
    assert result["current"] == 521.5
    assert result["source"] == "IBKR"
    assert result["market_data_type"] == "LIVE"
    # VIX should still come from yfinance fallback
    assert result["vix_open"] == 15.0
    assert result["vix_current"] == 14.5


@pytest.mark.unit
def test_falls_back_to_yfinance_when_not_connected():
    """When the bridge is not connected, fall back to yfinance."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    bridge = _make_bridge(connected=False)
    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: bridge)

    result = provider()

    assert result["source"] == "yfinance"
    assert result["open"] == 500.0
    assert result["current"] == 501.0


@pytest.mark.unit
def test_falls_back_to_yfinance_when_bridge_is_none():
    """When bridge_getter returns None, fall back to yfinance."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: None)
    result = provider()

    assert result["source"] == "yfinance"


@pytest.mark.unit
def test_falls_back_when_open_price_missing():
    """If IBKR quote has no open price, fall back to yfinance."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    spy_quote = {"open": None, "last": 521.5, "market_data_type": "LIVE"}
    bridge = _make_bridge(connected=True, spy_quote=spy_quote)
    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: bridge)

    result = provider()

    assert result["source"] == "yfinance"


@pytest.mark.unit
def test_falls_back_when_last_price_missing():
    """If IBKR quote has no last price, fall back to yfinance."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    spy_quote = {"open": 520.0, "last": None, "market_data_type": "LIVE"}
    bridge = _make_bridge(connected=True, spy_quote=spy_quote)
    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: bridge)

    result = provider()

    assert result["source"] == "yfinance"


@pytest.mark.unit
def test_falls_back_when_quote_is_none():
    """If get_latest_market_data_quote returns None, fall back to yfinance."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    bridge = _make_bridge(connected=True, spy_quote=None)
    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: bridge)

    result = provider()

    assert result["source"] == "yfinance"


@pytest.mark.unit
def test_falls_back_when_bridge_getter_raises():
    """If bridge_getter raises, fall back to yfinance gracefully."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    def _bad_getter():
        raise RuntimeError("bridge broken")

    provider = ibkr_with_yfinance_fallback_spy_provider(_bad_getter)
    result = provider()

    assert result["source"] == "yfinance"


@pytest.mark.unit
def test_subscribe_is_called_when_connected():
    """subscribe_market_data is called so SPY ticks start flowing."""
    from web.vix_market_data import ibkr_with_yfinance_fallback_spy_provider

    spy_quote = {"open": 520.0, "last": 521.5}
    bridge = _make_bridge(connected=True, spy_quote=spy_quote)
    provider = ibkr_with_yfinance_fallback_spy_provider(lambda: bridge)
    provider()

    bridge.subscribe_market_data.assert_called_once_with(["SPY"])
