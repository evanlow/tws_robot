from autonomous.technical_analysis_signal_provider import TechnicalAnalysisSignalProvider


def _row(symbol="AAA"):
    return {
        "symbol": symbol,
        "company": symbol + " Inc.",
        "sector": "Tech",
        "current_price": 105.0,
        "bollinger_status": "near_lower_band",
        "momentum_label": "Confirmed Rebound",
        "momentum_confirmation": "confirmed_rebound",
        "momentum_reasons": ["Price above 5-day MA"],
        "quality_label": "Strong",
        "quality_score": 80,
        "quality_reasons": ["Positive revenue growth"],
        "rsi_14": 45,
        "rsi_status": "rsi_neutral",
    }


class _StubScreener:
    def __init__(self, rows):
        self.rows = rows

    def get_screener_data(self, refresh=False):
        return {"rows": self.rows}


def _bars(symbol, period="60d", interval="1d"):
    return [
        {"low": 90, "high": 98, "close": 95},
        {"low": 94, "high": 101, "close": 99},
        {"low": 96, "high": 104, "close": 100},
        {"low": 97, "high": 107, "close": 102},
        {"low": 98, "high": 110, "close": 103},
        {"low": 99, "high": 108, "close": 104},
    ]


def test_provider_enriches_qualifying_signal_with_levels():
    provider = TechnicalAnalysisSignalProvider(
        screener_service=_StubScreener([_row("AAA")]),
        refresh_on_first_call=False,
        support_resistance_lookback_days=6,
        price_history_fetcher=_bars,
    )

    signal = provider.analyze("AAA")

    assert signal is not None
    assert signal.support_price == 99.0
    assert signal.resistance_price == 107.0
    assert signal.extras["levels_valid"] is True
    assert signal.extras["support_source"] == "nearest_recent_low_below_price"


def test_provider_prefers_levels_from_screener_row_without_fetching():
    calls = {"count": 0}

    def _fetcher(*args, **kwargs):
        calls["count"] += 1
        return []

    row = _row("AAA")
    row["support_price"] = 98.5
    row["resistance_price"] = 112.0
    provider = TechnicalAnalysisSignalProvider(
        screener_service=_StubScreener([row]),
        refresh_on_first_call=False,
        support_resistance_lookback_days=6,
        price_history_fetcher=_fetcher,
    )

    signal = provider.analyze("AAA")

    assert signal is not None
    assert signal.support_price == 98.5
    assert signal.resistance_price == 112.0
    assert signal.extras["levels_source"] == "screener_row"
    assert calls["count"] == 0


def test_provider_preserves_existing_screener_level_when_only_other_side_missing():
    row = _row("AAA")
    row["support_price"] = 98.5

    provider = TechnicalAnalysisSignalProvider(
        screener_service=_StubScreener([row]),
        refresh_on_first_call=False,
        support_resistance_lookback_days=6,
        price_history_fetcher=_bars,
    )

    signal = provider.analyze("AAA")

    assert signal is not None
    assert signal.support_price == 98.5
    assert signal.resistance_price == 107.0
