"""Targeted tests for market events parsing/model behavior."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from data.database import Database
from data.market_events import (
    EVENT_STATUS_STALE,
    MarketEventsService,
    _fetch_fomc_dates,
    _fetch_market_holidays,
    _normalize_event,
    _parse_fomc_date_range,
)
from data.models import MarketEvent


def _memory_service():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return MarketEventsService(database=db), db


def _utc_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        assert "start_at_utc" in data
        assert "status" in data

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


class TestMarketEventNormalizationAndSync:
    """Validate richer event normalization, upsert, stale, and reminders."""

    def test_normalize_event_converts_market_time_to_utc(self):
        event = _normalize_event({
            "event_type": "FOMC",
            "title": "FOMC Meeting",
            "event_date": datetime(2026, 7, 29),
            "event_time": "14:00 ET",
            "source": "federalreserve.gov",
            "source_event_id": "FOMC:2026-07-29",
        })

        assert event["start_at_utc"] == datetime(2026, 7, 29, 18, 0)
        assert event["event_id"].startswith("evt_")
        assert event["confidence"] == "confirmed"

    def test_upsert_deduplicates_by_source_event_id(self):
        svc, db = _memory_service()
        event = {
            "event_type": "EARNINGS",
            "symbol": "AAPL",
            "title": "Apple Earnings",
            "event_date": _utc_naive() + timedelta(days=3),
            "event_time": "AMC",
            "source": "test-provider",
            "source_event_id": "AAPL-Q1",
        }

        svc._upsert_events([event], portfolio_symbols={"AAPL"}, window_start=_utc_naive(), window_end=_utc_naive() + timedelta(days=28))
        event["title"] = "Apple Inc. Earnings"
        svc._upsert_events([event], portfolio_symbols={"AAPL"}, window_start=_utc_naive(), window_end=_utc_naive() + timedelta(days=28))

        with db.session_scope() as session:
            rows = session.query(MarketEvent).all()
            assert len(rows) == 1
            assert rows[0].title == "Apple Inc. Earnings"

    def test_missing_future_event_is_marked_stale(self):
        svc, db = _memory_service()
        now = _utc_naive()
        old_event = {
            "event_type": "EARNINGS",
            "symbol": "AAPL",
            "title": "Old Earnings",
            "event_date": now + timedelta(days=4),
            "event_time": "AMC",
            "source": "test-provider",
            "source_event_id": "old-event",
        }
        svc._upsert_events([old_event], portfolio_symbols={"AAPL"}, window_start=now, window_end=now + timedelta(days=28))

        stale_count = svc._mark_missing_future_events_stale(
            source="test-provider",
            event_types=["EARNINGS"],
            seen_event_ids=set(),
            window_start=now,
            window_end=now + timedelta(days=28),
            symbols={"AAPL"},
        )

        with db.session_scope() as session:
            row = session.query(MarketEvent).one()
            assert stale_count == 1
            assert row.status == EVENT_STATUS_STALE

    def test_sync_symbol_provider_only_stales_symbols_fetched_this_run(self):
        svc, db = _memory_service()
        now = _utc_naive()
        window_end = now + timedelta(days=28)

        svc._upsert_events([
            {
                "event_type": "EARNINGS",
                "symbol": "AAPL",
                "title": "Old AAPL Earnings",
                "event_date": now + timedelta(days=4),
                "event_time": "AMC",
                "source": "test-provider",
                "source_event_id": "old-aapl-event",
            },
            {
                "event_type": "EARNINGS",
                "symbol": "MSFT",
                "title": "Old MSFT Earnings",
                "event_date": now + timedelta(days=5),
                "event_time": "AMC",
                "source": "test-provider",
                "source_event_id": "old-msft-event",
            },
        ], portfolio_symbols={"AAPL", "MSFT"}, window_start=now, window_end=window_end)
        svc._last_fetched["EARNINGS:MSFT"] = datetime.now()

        result = svc._sync_symbol_provider(
            provider="test-provider",
            event_type="EARNINGS",
            symbols=["AAPL", "MSFT"],
            fetcher=lambda _symbol: None,
            ttl_hours=24,
            force=False,
            window_start=now,
            window_end=window_end,
        )

        with db.session_scope() as session:
            rows = {
                row.symbol: row.status
                for row in session.query(MarketEvent).filter_by(source="test-provider").all()
            }

        assert result.stale_count == 1
        assert rows["AAPL"] == EVENT_STATUS_STALE
        assert rows["MSFT"] != EVENT_STATUS_STALE

    def test_sync_static_provider_ttl_skip_does_not_mark_events_stale(self):
        svc, db = _memory_service()
        now = _utc_naive()
        window_end = now + timedelta(days=28)
        svc._upsert_events([{
            "event_type": "FOMC",
            "title": "FOMC Meeting",
            "event_date": now + timedelta(days=3),
            "event_time": "14:00 ET",
            "source": "test-provider",
            "source_event_id": "fomc-existing",
        }], portfolio_symbols=set(), window_start=now, window_end=window_end)
        svc._last_fetched["FOMC"] = datetime.now()

        result = svc._sync_static_provider(
            provider="test-provider",
            event_type="FOMC",
            events_fetcher=lambda: [{"unexpected": "call"}],
            ttl_key="FOMC",
            ttl_hours=24,
            force=False,
            window_start=now,
            window_end=window_end,
        )

        with db.session_scope() as session:
            status = session.query(MarketEvent).filter_by(source="test-provider").one().status

        assert result.fetched_count == 0
        assert result.stale_count == 0
        assert status != EVENT_STATUS_STALE

    def test_builtin_market_calendar_includes_july_2026_holiday(self):
        events = _fetch_market_holidays(
            datetime(2026, 7, 1),
            datetime(2026, 7, 7),
        )

        assert any(event["event_type"] == "MARKET_HOLIDAY" for event in events)
        assert any("Independence Day" in event["title"] for event in events)

    def test_sync_logs_provider_results_without_network(self):
        svc, _db = _memory_service()
        with patch("data.market_events._fetch_fomc_dates", return_value=[]):
            summary = svc.sync_market_events(portfolio_symbols=[], force=True, days_ahead=28)

        logs = svc.get_sync_logs()
        assert summary["status"] == "success"
        assert len(logs) >= 2
        assert {row["provider"] for row in logs} >= {"federalreserve.gov", "builtin-us-market-calendar"}

    def test_reminders_surface_high_impact_fomc(self):
        svc, _db = _memory_service()
        now = _utc_naive()
        svc._upsert_events([{
            "event_type": "FOMC",
            "title": "FOMC Meeting",
            "event_date": now + timedelta(days=1),
            "event_time": "14:00 ET",
            "source": "test-provider",
            "source_event_id": "fomc-tomorrow",
            "importance_score": 90.0,
        }], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=7))

        reminders = svc.get_reminders(days_ahead=7, mode="high_only")

        assert len(reminders) == 1
        assert reminders[0]["severity"] == "high"


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

        event_dates = {event["event_date"] for event in events}
        assert datetime(yr, 1, 28) in event_dates
        assert datetime(yr, 3, 18) in event_dates

    def test_parses_split_month_and_day_spans(self):
        """Fed page uses separate spans for month and day range."""
        yr = self._year()
        html = f"""
        <html><body>
        <h4 id="{yr}">{yr} FOMC Meetings</h4>
        <div class="fomc-meeting__row">
          <span class="fomc-meeting__month">January</span>
          <span class="fomc-meeting__day">28-29</span>
        </div>
        <div class="fomc-meeting__row">
          <span class="fomc-meeting__month">March</span>
          <span class="fomc-meeting__day">18-19</span>
        </div>
        <div class="fomc-meeting__row">
          <span class="fomc-meeting__month">April</span>
          <span class="fomc-meeting__day">29-30</span>
        </div>
        <div class="fomc-meeting__row">
          <span class="fomc-meeting__month">June</span>
          <span class="fomc-meeting__day">17-18</span>
        </div>
        </body></html>
        """

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = self._mock_urlopen(html)
            events = _fetch_fomc_dates()

        assert len(events) == 4
        assert events[0]["event_date"] == datetime(yr, 1, 29)
        assert events[1]["event_date"] == datetime(yr, 3, 19)
        assert events[2]["event_date"] == datetime(yr, 4, 30)
        assert events[3]["event_date"] == datetime(yr, 6, 18)

    def test_network_error_returns_empty_list(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            events = _fetch_fomc_dates()
        assert events == []
