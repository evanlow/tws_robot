from autonomous.market_data_provider import MarketDataQuote


def test_market_data_quote_from_mapping_preserves_explicit_false_feed_health():
    quote = MarketDataQuote.from_mapping(
        {
            "symbol": "AAPL",
            "feed_healthy": False,
            "market_data_feed_healthy": True,
        }
    )

    assert quote.feed_healthy is False


def test_market_data_quote_from_mapping_uses_legacy_feed_health_when_primary_missing():
    quote = MarketDataQuote.from_mapping(
        {
            "symbol": "AAPL",
            "market_data_feed_healthy": False,
        }
    )

    assert quote.feed_healthy is False
