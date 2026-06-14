"""Targeted tests for market events parsing/model behavior."""

from datetime import datetime, timedelta
from unittest.mock import patch

from data.market_events import MarketEventsService, _parse_fomc_date_range, _fetch_fomc_dates
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


class TestFetchFomcDates:
    """Validate _fetch_fomc_dates correctly parses realistic Fed page HTML."""

    def _mock_urlopen(self, html_text):
        """Create a mock urlopen context manager returning html_text."""
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.read.return_value = html_text.encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        return mock_resp

    def _year(self):
        return datetime.now().year

    def test_parses_fomc_meeting_date_class(self):
        yr = self._year()
        html = f"""
        <html><body>
        <h4 id="{yr}">{yr} FOMC Meetings</h4>
        <div class="panel panel-default">
          <span class="fomc-meeting__date">January 27-28</span>
        </div>
        <div class="panel panel-default">
          <span class="fomc-meeting__date">March 17-18</span>
        </div>
        <div class="panel panel-default">
          <span class="fomc-meeting__date">April 28-29 *</span>
        </div>
        </body></html>
        """

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_urlopen(html)
            events = _fetch_fomc_dates()

        assert len(events) == 3
        assert events[0]["event_date"] == datetime(yr, 1, 28)
        assert events[1]["event_date"] == datetime(yr, 3, 18)
        assert events[2]["event_date"] == datetime(yr, 4, 29)

    def test_parses_panel_title_format(self):
        yr = self._year()
        html = f"""
        <html><body>
        <h4 id="{yr}">{yr} FOMC Meetings</h4>
        <div class="panel panel-default">
          <h5 class="panel-title">January 27-28, {yr}: FOMC Meeting</h5>
        </div>
        <div class="panel panel-default">
          <h5 class="panel-title">March 17-18, {yr}: FOMC Meeting</h5>
        </div>
        </body></html>
        """

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_urlopen(html)
            events = _fetch_fomc_dates()

        assert len(events) == 2
        assert events[0]["event_date"] == datetime(yr, 1, 28)
        assert events[1]["event_date"] == datetime(yr, 3, 18)

    def test_falls_back_to_raw_date_extraction(self):
        yr = self._year()
        html = f"""
        <html><body>
        <h4 id="{yr}">{yr} FOMC Meetings</h4>
        <p>Next meeting: January 27-28 and March 17-18</p>
        </body></html>
        """

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_urlopen(html)
            events = _fetch_fomc_dates()

        assert len(events) >= 1

    def test_network_error_returns_empty_list(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            events = _fetch_fomc_dates()
        assert events == []
