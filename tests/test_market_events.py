"""Targeted tests for market events parsing/model behavior."""

from datetime import datetime, timedelta

from data.market_events import MarketEventsService, _parse_fomc_date_range
from data.models import MarketEvent


class TestFomcDateParsing:
    """Validate FOMC date-range parsing helper across common formats."""

    def test_parse_cross_month_range_uses_end_day(self):
        dt = _parse_fomc_date_range("April 30-May 1", 2026)
        assert dt == datetime(2026, 5, 1)

    def test_parse_same_month_range_uses_end_day(self):
        dt = _parse_fomc_date_range("March 18-19", 2026)
        assert dt == datetime(2026, 3, 19)

    def test_parse_single_date(self):
        dt = _parse_fomc_date_range("June 12", 2026)
        assert dt == datetime(2026, 6, 12)

    def test_parse_invalid_string_returns_none(self):
        assert _parse_fomc_date_range("Not a date", 2026) is None


class TestMarketEventModel:
    """Validate MarketEvent serialization behavior."""

    def test_to_dict_parses_detail_json(self):
        row = MarketEvent(
            event_type="EARNINGS",
            symbol="AAPL",
            title="AAPL Earnings",
            event_date=datetime(2026, 5, 20),
            event_time="AMC",
            source="yfinance",
            detail_json='{"eps_estimate": 1.23}',
            is_portfolio_relevant=True,
            fetched_at=datetime(2026, 5, 10, 12, 0, 0),
        )

        data = row.to_dict()

        assert data["event_type"] == "EARNINGS"
        assert data["symbol"] == "AAPL"
        assert data["detail"]["eps_estimate"] == 1.23
        assert data["is_portfolio_relevant"] is True

    def test_to_dict_keeps_non_json_detail_as_string(self):
        row = MarketEvent(
            event_type="FOMC",
            symbol=None,
            title="FOMC Meeting",
            event_date=datetime(2026, 6, 17),
            detail_json="not-json",
            fetched_at=datetime(2026, 5, 10, 12, 0, 0),
        )

        data = row.to_dict()

        assert data["detail"] == "not-json"


class TestMarketEventsServiceStaleness:
    """Validate staleness checks that drive refresh scheduling."""

    def test_is_stale_true_when_never_fetched(self):
        svc = MarketEventsService(database=object())
        assert svc.is_stale("FOMC") is True

    def test_is_stale_false_within_ttl(self):
        svc = MarketEventsService(database=object())
        svc._last_fetched["FOMC"] = datetime.now() - timedelta(hours=1)
        assert svc.is_stale("FOMC") is False

    def test_is_stale_true_after_ttl(self):
        svc = MarketEventsService(database=object())
        svc._last_fetched["FOMC"] = datetime.now() - timedelta(hours=25)
        assert svc.is_stale("FOMC") is True
