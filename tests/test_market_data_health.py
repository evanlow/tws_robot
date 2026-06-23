from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autonomous import AutonomousMode
from autonomous.market_data_health import MarketDataHealthGuard
from autonomous.market_data_provider import (
    IBKR_MARKET_DATA_TYPE_DELAYED,
    IBKR_MARKET_DATA_TYPE_FROZEN,
    IBKR_MARKET_DATA_TYPE_LIVE,
    IBKR_SOURCE,
    YAHOO_SOURCE,
)


def test_market_data_health_allows_fresh_quote():
    now = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)

    decision = MarketDataHealthGuard().evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        bid=99.95,
        ask=100.05,
        last=100.0,
        quote_timestamp=now - timedelta(seconds=5),
        source=IBKR_SOURCE,
        market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
        feed_healthy=True,
        market_open=True,
        now=now,
    )

    assert decision.allowed is True
    assert decision.quote_age_seconds == 5.0
    assert decision.spread_pct is not None
    assert decision.warnings == []


def test_market_data_health_blocks_stale_live_quote():
    now = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)

    decision = MarketDataHealthGuard(max_quote_age_seconds=30).evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        bid=99.95,
        ask=100.05,
        last=100.0,
        source=IBKR_SOURCE,
        market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
        quote_timestamp=now - timedelta(seconds=90),
        now=now,
    )

    assert decision.allowed is False
    assert "quote age" in decision.reason


def test_market_data_health_warns_on_stale_recommend_only_quote():
    now = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)

    decision = MarketDataHealthGuard(max_quote_age_seconds=30).evaluate(
        symbol="AAA",
        mode=AutonomousMode.RECOMMEND_ONLY,
        bid=99.95,
        ask=100.05,
        last=100.0,
        quote_timestamp=now - timedelta(seconds=90),
        source=YAHOO_SOURCE,
        now=now,
    )

    assert decision.allowed is True
    assert any("quote age" in warning for warning in decision.warnings)
    assert any("Yahoo Finance" in warning for warning in decision.warnings)


def test_market_data_health_can_block_missing_bid_ask_in_live_mode():
    decision = MarketDataHealthGuard(block_missing_bid_ask_live=True).evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        last=100.0,
        source=IBKR_SOURCE,
        market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
    )

    assert decision.allowed is False
    assert "bid/ask unavailable" in decision.reason


def test_market_data_health_blocks_unhealthy_feed_and_closed_market_in_live_mode():
    decision = MarketDataHealthGuard().evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        bid=99.95,
        ask=100.05,
        last=100.0,
        source=IBKR_SOURCE,
        market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
        feed_status="degraded",
        market_open=False,
    )

    assert decision.allowed is False
    assert "market-data feed unhealthy" in decision.reason
    assert "market is closed" in decision.reason


def test_market_data_health_blocks_delayed_and_frozen_ibkr_live_quotes():
    now = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    guard = MarketDataHealthGuard()

    delayed = guard.evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        bid=99.95,
        ask=100.05,
        last=100.0,
        quote_timestamp=now,
        source=IBKR_SOURCE,
        market_data_type=IBKR_MARKET_DATA_TYPE_DELAYED,
        now=now,
    )
    frozen = guard.evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        bid=99.95,
        ask=100.05,
        last=100.0,
        quote_timestamp=now,
        source=IBKR_SOURCE,
        market_data_type=IBKR_MARKET_DATA_TYPE_FROZEN,
        now=now,
    )

    assert delayed.allowed is False
    assert "not LIVE" in delayed.reason
    assert frozen.allowed is False
    assert "not LIVE" in frozen.reason


def test_market_data_health_blocks_yahoo_live_quote_source():
    now = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)

    decision = MarketDataHealthGuard().evaluate(
        symbol="AAA",
        mode=AutonomousMode.ASSISTED_LIVE,
        bid=99.95,
        ask=100.05,
        last=100.0,
        quote_timestamp=now,
        source=YAHOO_SOURCE,
        now=now,
    )

    assert decision.allowed is False
    assert "Yahoo Finance" in decision.reason
