"""Tests for market event enrichment providers and integration.

Covers:
- Provider interface and normalization
- SEC filing scoring
- Macro calendar enrichment
- Congressional trading signal handling
- Nullable start_at_utc for catalyst signals
- Provider failure isolation
- Ticker/reminder filtering of low-confidence signals
- Readiness behavior (signals cannot be blockers)
- Dedupe/upsert for enrichment records
- Sync log recording for enrichment providers
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from data.database import Database
from data.enrichment_providers import (
    CATEGORY_CATALYST_SIGNAL,
    CATEGORY_FILING_ALERT,
    CATEGORY_NEWS_CATALYST,
    CATEGORY_SCHEDULED_EVENT,
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_SIGNAL,
    EVENT_TYPE_CPI_RELEASE,
    EVENT_TYPE_CONGRESSIONAL_TRADE,
    EVENT_TYPE_FED_MINUTES,
    EVENT_TYPE_GDP_RELEASE,
    EVENT_TYPE_JOBS_REPORT,
    EVENT_TYPE_NEWS_CATALYST,
    EVENT_TYPE_PPI_RELEASE,
    EVENT_TYPE_SEC_8K,
    EVENT_TYPE_SEC_10K,
    EVENT_TYPE_SEC_10Q,
    EVENT_TYPE_SEC_FORM4,
    FILTER_GROUP_FILINGS,
    FILTER_GROUP_MACRO,
    FILTER_GROUP_CATALYST_SIGNALS,
    CompanyEventProvider,
    CongressionalTradingProvider,
    EnrichmentProvider,
    EnrichmentRecord,
    MacroCalendarProvider,
    NewsCatalystProvider,
    SECFilingProvider,
    _score_sec_filing,
    get_default_providers,
)
from data.market_events import (
    CONFIRMED,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    MarketEventsService,
    _normalize_event,
    _severity_for_event,
)
from data.models import MarketEvent


def _memory_service():
    db = Database("sqlite:///:memory:")
    db.create_tables()
    return MarketEventsService(database=db), db


def _utc_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Provider interface tests ─────────────────────────────────────────────────


class TestEnrichmentProviderInterface:
    """Verify the provider interface contract."""

    def test_all_default_providers_have_required_attributes(self):
        providers = get_default_providers()
        assert len(providers) == 5
        for p in providers:
            assert isinstance(p, EnrichmentProvider)
            assert p.provider_name
            assert isinstance(p.event_types, list)
            assert len(p.event_types) > 0

    def test_provider_fetch_safe_catches_exceptions(self):
        """A provider that raises should return empty list + error message."""

        class FailingProvider(EnrichmentProvider):
            provider_name = "failing-test"
            event_types = ["TEST_FAIL"]

            def fetch(self, symbols, window_start, window_end):
                raise RuntimeError("Simulated failure")

        provider = FailingProvider()
        records, error = provider.fetch_safe(["AAPL"], _utc_naive(), _utc_naive() + timedelta(days=7))
        assert records == []
        assert "Simulated failure" in error

    def test_enrichment_record_to_event_dict(self):
        """Verify EnrichmentRecord produces valid event dict for upsert."""
        now = _utc_naive()
        record = EnrichmentRecord(
            event_type=EVENT_TYPE_CPI_RELEASE,
            title="CPI Release",
            source="bls.gov",
            source_event_id="CPI:2026-07-14",
            category=CATEGORY_SCHEDULED_EVENT,
            event_date=now + timedelta(days=3),
            start_at_utc=now + timedelta(days=3),
            confidence=CONFIDENCE_CONFIRMED,
            importance_score=80.0,
        )
        d = record.to_event_dict()
        assert d["event_type"] == EVENT_TYPE_CPI_RELEASE
        assert d["start_at_utc"] == now + timedelta(days=3)
        assert d["confidence"] == CONFIDENCE_CONFIRMED
        assert d["importance_score"] == 80.0
        assert d["detail"]["category"] == CATEGORY_SCHEDULED_EVENT


# ── SEC filing scoring tests ─────────────────────────────────────────────────


class TestSECFilingScoring:
    """Verify deterministic importance scoring for SEC filings."""

    def test_8k_base_score(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_8K)
        assert score == 60.0

    def test_8k_material_item_elevates_score(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_8K, title="Item 1.01 - Entry into material agreement")
        assert score >= 80.0

    def test_8k_bankruptcy_keyword_elevates_score(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_8K, description="Company files for bankruptcy protection")
        assert score >= 85.0

    def test_10k_base_score(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_10K)
        assert score == 55.0

    def test_10q_base_score(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_10Q)
        assert score == 50.0

    def test_form4_base_score(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_FORM4)
        assert score == 40.0

    def test_8k_merger_keyword(self):
        score = _score_sec_filing(EVENT_TYPE_SEC_8K, description="merger agreement signed")
        assert score >= 85.0

    def test_sec_normalize_filing(self):
        record = SECFilingProvider.normalize_filing(
            symbol="AAPL",
            form_type="8-K",
            filed_date=datetime(2026, 7, 1, 12, 0),
            title="Entry into Material Agreement",
            accession_number="0001234567-26-000123",
            description="Item 1.01 material agreement",
        )
        assert record.event_type == EVENT_TYPE_SEC_8K
        assert record.category == CATEGORY_FILING_ALERT
        assert record.importance_score >= 80.0
        assert record.confidence == CONFIDENCE_SIGNAL
        assert "AAPL" in record.title
        assert "company=AAPL" in record.source_url


# ── Macro calendar tests ─────────────────────────────────────────────────────


class TestMacroCalendarProvider:
    """Verify macro calendar enrichment."""

    def test_fetches_events_in_window(self):
        provider = MacroCalendarProvider()
        # Window covering July 2026
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 31)
        records = provider.fetch([], start, end)
        assert len(records) > 0
        types_found = {r.event_type for r in records}
        # Should find CPI, Jobs, PPI, GDP or Fed Minutes in July
        assert EVENT_TYPE_CPI_RELEASE in types_found or EVENT_TYPE_JOBS_REPORT in types_found

    def test_all_records_have_confirmed_confidence(self):
        provider = MacroCalendarProvider()
        records = provider.fetch([], datetime(2026, 1, 1), datetime(2026, 12, 31))
        for r in records:
            assert r.confidence == CONFIDENCE_CONFIRMED

    def test_events_outside_window_excluded(self):
        provider = MacroCalendarProvider()
        # Very narrow window
        records = provider.fetch([], datetime(2026, 1, 1), datetime(2026, 1, 2))
        # Should be empty or only events on Jan 1
        for r in records:
            assert datetime(2026, 1, 1) <= r.start_at_utc <= datetime(2026, 1, 2)

    def test_macro_event_to_dict_format(self):
        provider = MacroCalendarProvider()
        records = provider.fetch([], datetime(2026, 7, 1), datetime(2026, 7, 31))
        if records:
            d = records[0].to_event_dict()
            assert "event_type" in d
            assert "start_at_utc" in d
            assert d["confidence"] == CONFIDENCE_CONFIRMED


# ── Congressional trading provider tests ─────────────────────────────────────


class TestCongressionalTradingProvider:
    """Verify congressional trading signal handling."""

    def test_normalize_disclosure_produces_signal(self):
        record = CongressionalTradingProvider.normalize_disclosure(
            symbol="NVDA",
            politician_name="Test Senator",
            transaction_type="Purchase",
            transaction_date=datetime(2026, 6, 15),
            disclosure_date=datetime(2026, 6, 20),
            amount_range="$1,000,001 - $5,000,000",
        )
        assert record.event_type == EVENT_TYPE_CONGRESSIONAL_TRADE
        assert record.confidence == CONFIDENCE_SIGNAL
        assert record.category == CATEGORY_CATALYST_SIGNAL
        assert record.start_at_utc is None  # Signal only
        assert record.importance_score >= 70.0  # Elevated for large transaction

    def test_small_transaction_lower_importance(self):
        record = CongressionalTradingProvider.normalize_disclosure(
            symbol="AAPL",
            politician_name="Test Rep",
            transaction_type="Sale",
            transaction_date=datetime(2026, 6, 10),
            disclosure_date=datetime(2026, 6, 15),
            amount_range="$1,001 - $15,000",
        )
        assert record.importance_score == 50.0

    def test_disclosure_to_event_dict_has_published_at(self):
        disclosure_date = datetime(2026, 6, 20)
        record = CongressionalTradingProvider.normalize_disclosure(
            symbol="MSFT",
            politician_name="Test Senator",
            transaction_type="Purchase",
            transaction_date=None,
            disclosure_date=disclosure_date,
        )
        d = record.to_event_dict()
        assert d["detail"]["published_at_utc"] == disclosure_date.isoformat()
        # Signal events use published_at as event_date fallback
        assert d["event_date"] == disclosure_date


# ── Nullable start_at_utc tests ──────────────────────────────────────────────


class TestNullableStartAtUTC:
    """Verify that signal-confidence events can have nullable start_at_utc."""

    def test_normalize_event_allows_null_start_for_signal(self):
        """Signal-confidence events should not raise on missing start_at_utc."""
        published = _utc_naive()
        event = {
            "event_type": "CONGRESSIONAL_TRADE",
            "title": "Congressional trade: Test Senator Purchase NVDA",
            "source": "congressional-trades",
            "source_event_id": "CONGRESS:NVDA:Test:2026-06-20",
            "confidence": "signal",
            "published_at_utc": published,
        }
        normalized = _normalize_event(event)
        # Should use published_at_utc as fallback
        assert normalized["start_at_utc"] == published
        assert normalized["confidence"] == "signal"

    def test_normalize_event_lowercases_signal_confidence_and_normalizes_timezone(self):
        published = datetime(2026, 6, 20, 15, 30, tzinfo=timezone(timedelta(hours=8)))
        event = {
            "event_type": "CONGRESSIONAL_TRADE",
            "title": "Congressional trade: Test Senator Purchase NVDA",
            "source": "congressional-trades",
            "source_event_id": "CONGRESS:NVDA:Test:2026-06-20",
            "confidence": "Signal",
            "published_at_utc": published,
        }

        normalized = _normalize_event(event)

        assert normalized["confidence"] == "signal"
        assert normalized["start_at_utc"] == datetime(2026, 6, 20, 7, 30)
        assert normalized["start_at_utc"].tzinfo is None

    def test_normalize_event_raises_for_non_signal_without_date(self):
        """Non-signal events must have a parseable datetime."""
        event = {
            "event_type": "EARNINGS",
            "title": "Test Earnings",
            "source": "test",
            "source_event_id": "TEST:1",
            "confidence": "confirmed",
        }
        with pytest.raises(ValueError, match="no parseable datetime"):
            _normalize_event(event)

    def test_signal_event_upserts_successfully(self):
        """Signal events with nullable start should upsert without error."""
        svc, db = _memory_service()
        now = _utc_naive()
        event = {
            "event_type": "NEWS_CATALYST",
            "title": "Market catalyst signal",
            "source": "news-catalyst",
            "source_event_id": "NEWS:test:1",
            "confidence": "signal",
            "published_at_utc": now,
            "importance_score": 30.0,
        }
        svc._upsert_events(
            [event],
            portfolio_symbols=set(),
            window_start=now - timedelta(days=1),
            window_end=now + timedelta(days=28),
        )
        with db.session_scope() as session:
            rows = session.query(MarketEvent).all()
            assert len(rows) == 1
            assert rows[0].confidence == "signal"


# ── Severity scoring with enrichment events ──────────────────────────────────


class TestEnrichmentSeverityScoring:
    """Verify severity scoring handles new enrichment types correctly."""

    def test_cpi_release_within_1_day_is_high(self):
        severity = _severity_for_event({
            "event_type": "CPI_RELEASE",
            "days_away": 1,
            "importance_score": 80.0,
            "confidence": "confirmed",
        })
        assert severity == SEVERITY_HIGH

    def test_cpi_release_3_days_is_medium(self):
        severity = _severity_for_event({
            "event_type": "CPI_RELEASE",
            "days_away": 3,
            "importance_score": 80.0,
            "confidence": "confirmed",
        })
        assert severity == SEVERITY_MEDIUM

    def test_cpi_release_signal_within_1_day_is_capped_at_medium(self):
        severity = _severity_for_event({
            "event_type": "CPI_RELEASE",
            "days_away": 1,
            "importance_score": 80.0,
            "confidence": "signal",
        })
        assert severity == SEVERITY_MEDIUM

    def test_jobs_report_tomorrow_is_high(self):
        severity = _severity_for_event({
            "event_type": "JOBS_REPORT",
            "days_away": 0,
            "importance_score": 85.0,
            "confidence": "confirmed",
        })
        assert severity == SEVERITY_HIGH

    def test_sec_8k_high_importance_signal_capped_at_medium(self):
        """Signal-confidence SEC filings should not exceed medium severity."""
        severity = _severity_for_event({
            "event_type": "SEC_8K",
            "days_away": 0,
            "importance_score": 90.0,
            "confidence": "signal",
        })
        assert severity == SEVERITY_MEDIUM

    def test_sec_8k_high_importance_confirmed_is_high(self):
        severity = _severity_for_event({
            "event_type": "SEC_8K",
            "days_away": 0,
            "importance_score": 90.0,
            "confidence": "confirmed",
        })
        assert severity == SEVERITY_HIGH

    def test_congressional_trade_signal_low_importance_is_info(self):
        severity = _severity_for_event({
            "event_type": "CONGRESSIONAL_TRADE",
            "days_away": 0,
            "importance_score": 50.0,
            "confidence": "signal",
        })
        assert severity == SEVERITY_INFO

    def test_congressional_trade_signal_high_importance_is_medium(self):
        severity = _severity_for_event({
            "event_type": "CONGRESSIONAL_TRADE",
            "days_away": 0,
            "importance_score": 85.0,
            "confidence": "signal",
        })
        assert severity == SEVERITY_MEDIUM

    def test_news_catalyst_signal_stays_info(self):
        severity = _severity_for_event({
            "event_type": "NEWS_CATALYST",
            "days_away": 0,
            "importance_score": 40.0,
            "confidence": "signal",
        })
        assert severity == SEVERITY_INFO


# ── Ticker and reminder filtering ────────────────────────────────────────────


class TestTickerAndReminderFiltering:
    """Verify ticker and reminders exclude low-confidence signals."""

    def test_ticker_excludes_low_importance_signals(self):
        svc, db = _memory_service()
        now = _utc_naive()
        # Insert a confirmed event and a low-importance signal
        svc._upsert_events([
            {
                "event_type": "CPI_RELEASE",
                "title": "CPI Release",
                "event_date": now + timedelta(days=1),
                "source": "macro-calendar",
                "source_event_id": "CPI:2026-07-14",
                "confidence": "confirmed",
                "importance_score": 80.0,
            },
            {
                "event_type": "NEWS_CATALYST",
                "title": "Some news signal",
                "event_date": now + timedelta(days=1),
                "source": "news-catalyst",
                "source_event_id": "NEWS:test:low",
                "confidence": "signal",
                "importance_score": 30.0,
            },
        ], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=28))

        items = svc.get_ticker_items(days_ahead=7)
        # CPI should appear, low-importance signal should not
        assert any(i["event_type"] == "CPI_RELEASE" for i in items)
        assert not any(i["event_type"] == "NEWS_CATALYST" for i in items)

    def test_ticker_includes_high_importance_signals(self):
        svc, db = _memory_service()
        now = _utc_naive()
        svc._upsert_events([{
            "event_type": "CONGRESSIONAL_TRADE",
            "title": "Large congressional trade",
            "event_date": now + timedelta(days=1),
            "source": "congressional-trades",
            "source_event_id": "CONGRESS:TEST:1",
            "confidence": "signal",
            "importance_score": 75.0,
        }], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=28))

        items = svc.get_ticker_items(days_ahead=7)
        assert any(i["event_type"] == "CONGRESSIONAL_TRADE" for i in items)

    def test_reminders_exclude_signals_in_high_only_mode(self):
        svc, db = _memory_service()
        now = _utc_naive()
        svc._upsert_events([{
            "event_type": "SEC_8K",
            "title": "Material 8-K filing",
            "event_date": now + timedelta(days=1),
            "source": "sec-edgar",
            "source_event_id": "SEC:TEST:1",
            "confidence": "signal",
            "importance_score": 90.0,
        }], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=28))

        reminders = svc.get_reminders(days_ahead=7, mode="high_only")
        # Signal events excluded from reminders in non-"all" modes
        assert len(reminders) == 0

    def test_reminders_include_signals_in_all_mode(self):
        svc, db = _memory_service()
        now = _utc_naive()
        svc._upsert_events([{
            "event_type": "SEC_8K",
            "title": "Material 8-K filing",
            "event_date": now + timedelta(days=1),
            "source": "sec-edgar",
            "source_event_id": "SEC:TEST:2",
            "confidence": "signal",
            "importance_score": 90.0,
        }], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=28))

        reminders = svc.get_reminders(days_ahead=7, mode="all")
        # In "all" mode, signal events with sufficient severity are shown
        assert len(reminders) >= 1
        assert reminders[0]["confidence"] == "signal"


# ── Readiness behavior ───────────────────────────────────────────────────────


class TestReadinessBehavior:
    """Verify that signal-confidence events cannot become blockers."""

    def test_signal_events_cannot_be_blockers(self):
        svc, db = _memory_service()
        now = _utc_naive()
        # Insert a signal with critical-level importance but signal confidence
        svc._upsert_events([{
            "event_type": "SEC_8K",
            "title": "Critical SEC filing signal",
            "event_date": now + timedelta(hours=2),
            "source": "sec-edgar",
            "source_event_id": "SEC:CRITICAL:1",
            "confidence": "signal",
            "importance_score": 95.0,
        }], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=7))

        risk = svc.evaluate_event_risk(days_ahead=7)
        # Signals must NOT appear in blockers
        assert len(risk["blockers"]) == 0
        # But may appear in warnings if severity is medium+
        # (SEC_8K signal capped at medium severity)
        assert any(
            w["event_type"] == "SEC_8K" for w in risk["warnings"]
        )

    def test_confirmed_macro_events_are_warnings(self):
        svc, db = _memory_service()
        now = _utc_naive()
        svc._upsert_events([{
            "event_type": "CPI_RELEASE",
            "title": "CPI Release",
            "event_date": now + timedelta(days=2),
            "source": "macro-calendar",
            "source_event_id": "CPI:2026-test",
            "confidence": "confirmed",
            "importance_score": 80.0,
        }], portfolio_symbols=set(), window_start=now, window_end=now + timedelta(days=7))

        risk = svc.evaluate_event_risk(days_ahead=7)
        assert len(risk["warnings"]) == 1
        assert risk["warnings"][0]["event_type"] == "CPI_RELEASE"


# ── Provider failure isolation ───────────────────────────────────────────────


class TestProviderFailureIsolation:
    """Verify that enrichment provider failures are isolated."""

    def test_failing_provider_does_not_affect_others(self):
        """If one enrichment provider fails, others still sync."""
        svc, db = _memory_service()
        now = _utc_naive()

        # Patch get_default_providers to include a failing one
        from data.enrichment_providers import EnrichmentProvider as EP

        class FailProvider(EP):
            provider_name = "fail-test"
            event_types = ["FAIL_TYPE"]

            def fetch(self, symbols, window_start, window_end):
                raise RuntimeError("Provider crash")

        class SuccessProvider(EP):
            provider_name = "success-test"
            event_types = ["SUCCESS_TYPE"]

            def fetch(self, symbols, window_start, window_end):
                return [EnrichmentRecord(
                    event_type="CPI_RELEASE",
                    title="Test CPI",
                    source="success-test",
                    source_event_id="CPI:TEST:ISO",
                    event_date=window_start + timedelta(days=5),
                    start_at_utc=window_start + timedelta(days=5),
                    importance_score=80.0,
                )]

        with patch("data.enrichment_providers.get_default_providers",
                   return_value=[FailProvider(), SuccessProvider()]):
            results = svc._sync_enrichment_providers(
                symbols=["AAPL"],
                force=True,
                window_start=now,
                window_end=now + timedelta(days=28),
            )

        assert len(results) == 2
        fail_result = next(r for r in results if r.provider == "fail-test")
        success_result = next(r for r in results if r.provider == "success-test")
        assert fail_result.status == "failed"
        assert "Provider crash" in fail_result.error_message
        assert success_result.status == "success"
        assert success_result.fetched_count == 1

    def test_enrichment_sync_records_sync_logs(self):
        """Enrichment provider syncs should appear in sync logs."""
        svc, db = _memory_service()
        now = _utc_naive()

        # Use default providers (they return empty but still log)
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value = object()
            results = svc._sync_enrichment_providers(
                symbols=["AAPL"],
                force=True,
                window_start=now,
                window_end=now + timedelta(days=28),
            )

        logs = svc.get_sync_logs(limit=50)
        enrichment_logs = [
            log for log in logs
            if log.get("provider") in {p.provider_name for p in get_default_providers()}
        ]
        assert len(enrichment_logs) >= 1


# ── Dedupe for enrichment records ────────────────────────────────────────────


class TestEnrichmentDedupe:
    """Verify dedupe/upsert works correctly for enrichment records."""

    def test_enrichment_record_deduplicates_on_source_event_id(self):
        svc, db = _memory_service()
        now = _utc_naive()
        event = {
            "event_type": "CPI_RELEASE",
            "title": "CPI Release v1",
            "event_date": now + timedelta(days=5),
            "source": "macro-calendar",
            "source_event_id": "CPI:2026-07-14",
            "confidence": "confirmed",
            "importance_score": 80.0,
        }
        svc._upsert_events([event], portfolio_symbols=set(),
                           window_start=now, window_end=now + timedelta(days=28))

        # Upsert again with updated title
        event["title"] = "CPI Release v2"
        svc._upsert_events([event], portfolio_symbols=set(),
                           window_start=now, window_end=now + timedelta(days=28))

        with db.session_scope() as session:
            rows = session.query(MarketEvent).filter_by(
                event_type="CPI_RELEASE"
            ).all()
            assert len(rows) == 1
            assert rows[0].title == "CPI Release v2"
