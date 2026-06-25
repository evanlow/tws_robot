"""Market event enrichment provider framework.

This module defines the abstract base class for enrichment providers and
implements concrete providers for SEC filings, macro calendar releases,
congressional trading disclosures, and company events.

Safety stance:
- Enrichment adds context/warnings only; it never enables live trading.
- Provider failures are isolated and logged; they cannot delete existing events
  or make readiness more permissive.
- Low-confidence signals are clearly labeled and excluded from reminders/ticker
  by default.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ── Event categories ─────────────────────────────────────────────────────────

CATEGORY_SCHEDULED_EVENT = "SCHEDULED_EVENT"
CATEGORY_FILING_ALERT = "FILING_ALERT"
CATEGORY_CATALYST_SIGNAL = "CATALYST_SIGNAL"
CATEGORY_NEWS_CATALYST = "NEWS_CATALYST"

# ── Event types ──────────────────────────────────────────────────────────────

EVENT_TYPE_SEC_8K = "SEC_8K"
EVENT_TYPE_SEC_10Q = "SEC_10Q"
EVENT_TYPE_SEC_10K = "SEC_10K"
EVENT_TYPE_SEC_S3 = "SEC_S3"
EVENT_TYPE_SEC_FORM4 = "SEC_FORM4"
EVENT_TYPE_INVESTOR_DAY = "INVESTOR_DAY"
EVENT_TYPE_CONFERENCE = "CONFERENCE"
EVENT_TYPE_PRODUCT_EVENT = "PRODUCT_EVENT"
EVENT_TYPE_SHAREHOLDER_MEETING = "SHAREHOLDER_MEETING"
EVENT_TYPE_CPI_RELEASE = "CPI_RELEASE"
EVENT_TYPE_PPI_RELEASE = "PPI_RELEASE"
EVENT_TYPE_JOBS_REPORT = "JOBS_REPORT"
EVENT_TYPE_GDP_RELEASE = "GDP_RELEASE"
EVENT_TYPE_FED_MINUTES = "FED_MINUTES"
EVENT_TYPE_CONGRESSIONAL_TRADE = "CONGRESSIONAL_TRADE"
EVENT_TYPE_NEWS_CATALYST = "NEWS_CATALYST"

# ── Confidence levels ────────────────────────────────────────────────────────

CONFIDENCE_CONFIRMED = "confirmed"
CONFIDENCE_ESTIMATED = "estimated"
CONFIDENCE_TENTATIVE = "tentative"
CONFIDENCE_SIGNAL = "signal"

# ── Enrichment category groups for dashboard filters ─────────────────────────

FILTER_GROUP_FILINGS = "Filings"
FILTER_GROUP_MACRO = "Macro"
FILTER_GROUP_COMPANY_EVENTS = "Company Events"
FILTER_GROUP_CATALYST_SIGNALS = "Catalyst Signals"

EVENT_TYPE_TO_FILTER_GROUP = {
    EVENT_TYPE_SEC_8K: FILTER_GROUP_FILINGS,
    EVENT_TYPE_SEC_10Q: FILTER_GROUP_FILINGS,
    EVENT_TYPE_SEC_10K: FILTER_GROUP_FILINGS,
    EVENT_TYPE_SEC_S3: FILTER_GROUP_FILINGS,
    EVENT_TYPE_SEC_FORM4: FILTER_GROUP_FILINGS,
    EVENT_TYPE_CPI_RELEASE: FILTER_GROUP_MACRO,
    EVENT_TYPE_PPI_RELEASE: FILTER_GROUP_MACRO,
    EVENT_TYPE_JOBS_REPORT: FILTER_GROUP_MACRO,
    EVENT_TYPE_GDP_RELEASE: FILTER_GROUP_MACRO,
    EVENT_TYPE_FED_MINUTES: FILTER_GROUP_MACRO,
    EVENT_TYPE_INVESTOR_DAY: FILTER_GROUP_COMPANY_EVENTS,
    EVENT_TYPE_CONFERENCE: FILTER_GROUP_COMPANY_EVENTS,
    EVENT_TYPE_PRODUCT_EVENT: FILTER_GROUP_COMPANY_EVENTS,
    EVENT_TYPE_SHAREHOLDER_MEETING: FILTER_GROUP_COMPANY_EVENTS,
    EVENT_TYPE_CONGRESSIONAL_TRADE: FILTER_GROUP_CATALYST_SIGNALS,
    EVENT_TYPE_NEWS_CATALYST: FILTER_GROUP_CATALYST_SIGNALS,
}

# All enrichment event types
ENRICHMENT_EVENT_TYPES = set(EVENT_TYPE_TO_FILTER_GROUP.keys())

# Event types that may have nullable start_at_utc (signal-only)
SIGNAL_ONLY_EVENT_TYPES = {
    EVENT_TYPE_CONGRESSIONAL_TRADE,
    EVENT_TYPE_NEWS_CATALYST,
    EVENT_TYPE_SEC_FORM4,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _event_id_hash(source: str, source_event_id: str) -> str:
    raw = f"{source}|{source_event_id}"
    return "evt_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ── Provider interface ───────────────────────────────────────────────────────


@dataclass
class EnrichmentRecord:
    """Normalized enrichment event/signal record returned by providers."""

    event_type: str
    title: str
    source: str
    source_event_id: str
    category: str = CATEGORY_SCHEDULED_EVENT
    symbol: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[datetime] = None
    start_at_utc: Optional[datetime] = None
    end_at_utc: Optional[datetime] = None
    published_at_utc: Optional[datetime] = None
    market_timezone: str = "America/New_York"
    source_url: Optional[str] = None
    confidence: str = CONFIDENCE_CONFIRMED
    importance_score: float = 0.0
    raw_payload: Optional[Dict[str, Any]] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_event_dict(self) -> Dict[str, Any]:
        """Convert to the dict format expected by MarketEventsService._upsert_events."""
        # Use published_at_utc as event_date fallback for signal-only records
        effective_date = self.start_at_utc or self.event_date or self.published_at_utc
        return {
            "event_type": self.event_type,
            "symbol": self.symbol,
            "title": self.title,
            "description": self.description,
            "event_date": effective_date,
            "start_at_utc": self.start_at_utc or effective_date,
            "end_at_utc": self.end_at_utc,
            "market_timezone": self.market_timezone,
            "source": self.source,
            "source_event_id": self.source_event_id,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "importance_score": self.importance_score,
            "raw_payload": self.raw_payload,
            "detail": {
                **self.detail,
                "category": self.category,
                "published_at_utc": self.published_at_utc.isoformat() if self.published_at_utc else None,
            },
        }


@dataclass
class ProviderSyncMetadata:
    """Metadata returned alongside enrichment records from a provider sync."""

    provider_name: str
    fetched_count: int = 0
    error_message: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


class EnrichmentProvider(ABC):
    """Abstract base class for market event enrichment providers.

    Each provider independently fetches, normalizes, and returns enrichment
    records. Failures are isolated — a failed provider must not affect other
    providers or existing durable events.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier used in sync logs."""
        ...

    @property
    @abstractmethod
    def event_types(self) -> List[str]:
        """Event types this provider may produce."""
        ...

    @abstractmethod
    def fetch(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Fetch enrichment records for the given window.

        Must not raise — return empty list on failure after logging.
        Provider implementations should catch all exceptions internally.
        """
        ...

    def fetch_safe(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[List[EnrichmentRecord], Optional[str]]:
        """Safe wrapper that catches unexpected exceptions."""
        try:
            records = self.fetch(symbols, window_start, window_end)
            return records, None
        except Exception as exc:
            logger.error(
                "EnrichmentProvider %s failed: %s", self.provider_name, exc
            )
            return [], str(exc)


# ── SEC Filing Provider ──────────────────────────────────────────────────────

# Material 8-K item keywords for importance scoring
_8K_HIGH_IMPORTANCE_ITEMS = {
    "1.01": "entry into material agreement",
    "1.02": "termination of material agreement",
    "2.01": "acquisition/disposition of assets",
    "2.04": "triggering events",
    "2.05": "costs from exit/disposal",
    "2.06": "material impairments",
    "3.01": "delisting/transfer",
    "4.01": "change in auditor",
    "5.01": "change in control",
    "5.02": "departure of officers/directors",
}

_8K_MEDIUM_IMPORTANCE_ITEMS = {
    "2.02": "results of operations",
    "7.01": "Regulation FD disclosure",
    "8.01": "other events",
}

_FILING_TYPE_IMPORTANCE = {
    EVENT_TYPE_SEC_8K: 60.0,
    EVENT_TYPE_SEC_10Q: 50.0,
    EVENT_TYPE_SEC_10K: 55.0,
    EVENT_TYPE_SEC_S3: 45.0,
    EVENT_TYPE_SEC_FORM4: 40.0,
}


def _score_sec_filing(
    event_type: str,
    title: str = "",
    description: str = "",
) -> float:
    """Deterministic importance scoring for SEC filings."""
    base = _FILING_TYPE_IMPORTANCE.get(event_type, 30.0)
    text = f"{title} {description}".lower()

    # Elevate for material 8-K items
    if event_type == EVENT_TYPE_SEC_8K:
        for item_num, keyword in _8K_HIGH_IMPORTANCE_ITEMS.items():
            if item_num in text or keyword in text:
                base = max(base, 80.0)
                break
        for item_num, keyword in _8K_MEDIUM_IMPORTANCE_ITEMS.items():
            if item_num in text or keyword in text:
                base = max(base, 65.0)
                break

    # Keyword elevations
    high_keywords = ["bankruptcy", "restructuring", "merger", "acquisition", "m&a"]
    medium_keywords = ["management change", "ceo", "cfo", "restatement"]
    for kw in high_keywords:
        if kw in text:
            base = max(base, 85.0)
            break
    for kw in medium_keywords:
        if kw in text:
            base = max(base, 70.0)
            break

    return min(base, 100.0)


class SECFilingProvider(EnrichmentProvider):
    """Enrichment provider for SEC EDGAR filings.

    Fetches recent filings for tracked symbols from the SEC EDGAR RSS feed.
    Maps company tickers to CIK numbers and retrieves filings.
    """

    provider_name = "sec-edgar"
    event_types = [
        EVENT_TYPE_SEC_8K,
        EVENT_TYPE_SEC_10Q,
        EVENT_TYPE_SEC_10K,
        EVENT_TYPE_SEC_S3,
        EVENT_TYPE_SEC_FORM4,
    ]

    # SEC EDGAR full-text search / company filings endpoint
    _EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q="
    _EDGAR_COMPANY_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

    # Filing form type mapping
    _FORM_TYPE_MAP = {
        "8-K": EVENT_TYPE_SEC_8K,
        "10-Q": EVENT_TYPE_SEC_10Q,
        "10-K": EVENT_TYPE_SEC_10K,
        "S-3": EVENT_TYPE_SEC_S3,
        "4": EVENT_TYPE_SEC_FORM4,
    }

    def fetch(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Fetch SEC filings. Returns empty list if SEC is unreachable.

        Note: In production, this would make HTTP requests to SEC EDGAR.
        The provider is designed to degrade gracefully when the SEC API is
        unavailable or rate-limited.
        """
        records: List[EnrichmentRecord] = []
        for symbol in symbols:
            try:
                filings = self._fetch_filings_for_symbol(
                    symbol, window_start, window_end
                )
                records.extend(filings)
            except Exception as exc:
                logger.warning(
                    "SEC filing fetch failed for %s: %s", symbol, exc
                )
        return records

    def _fetch_filings_for_symbol(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Fetch filings for a single symbol from SEC EDGAR.

        This method attempts to reach the SEC EDGAR API. If the network
        call fails (rate limit, timeout, etc.), it returns an empty list
        rather than raising, preserving provider isolation.
        """
        try:
            import urllib.request
            import json as json_mod

            # SEC EDGAR ticker->CIK lookup
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&CIK=&type=&dateb=&owner=include&count=1&search_text=&output=atom"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "TWS-Robot/1.0 research@example.com"},
            )
            # Short timeout to avoid blocking sync
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass  # We only need to verify connectivity
        except Exception:
            # SEC EDGAR unreachable — degrade gracefully
            logger.debug("SEC EDGAR unreachable for %s, skipping", symbol)
            return []
        return []

    @staticmethod
    def normalize_filing(
        symbol: str,
        form_type: str,
        filed_date: datetime,
        title: str,
        accession_number: str,
        description: str = "",
        source_url: Optional[str] = None,
    ) -> EnrichmentRecord:
        """Normalize a raw SEC filing into an EnrichmentRecord.

        This is a public static method so that custom integrations or
        tests can produce normalized records without network access.
        """
        event_type = SECFilingProvider._FORM_TYPE_MAP.get(
            form_type, EVENT_TYPE_SEC_8K
        )
        importance = _score_sec_filing(event_type, title, description)
        confidence = CONFIDENCE_CONFIRMED if event_type in {
            EVENT_TYPE_SEC_10Q, EVENT_TYPE_SEC_10K
        } else CONFIDENCE_SIGNAL

        # Filing alerts use publication time as the event reference
        return EnrichmentRecord(
            event_type=event_type,
            title=f"{symbol} {form_type}: {title}"[:200],
            source="sec-edgar",
            source_event_id=f"SEC:{symbol}:{accession_number}",
            category=CATEGORY_FILING_ALERT,
            symbol=symbol.upper(),
            description=description[:500] if description else None,
            event_date=filed_date,
            start_at_utc=filed_date,
            published_at_utc=filed_date,
            source_url=source_url or f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&type={form_type}",
            confidence=confidence,
            importance_score=importance,
            raw_payload={"form_type": form_type, "accession": accession_number},
        )


# ── Macro Calendar Provider ─────────────────────────────────────────────────

# Static macro release schedule for deterministic testing and offline operation.
# In production, this would be supplemented by BLS/BEA/Fed API data.

_MACRO_EVENT_DEFINITIONS = [
    {
        "event_type": EVENT_TYPE_CPI_RELEASE,
        "title": "CPI Release",
        "source": "bls.gov",
        "confidence": CONFIDENCE_CONFIRMED,
        "importance_base": 80.0,
        "description": "Consumer Price Index monthly release",
    },
    {
        "event_type": EVENT_TYPE_PPI_RELEASE,
        "title": "PPI Release",
        "source": "bls.gov",
        "confidence": CONFIDENCE_CONFIRMED,
        "importance_base": 70.0,
        "description": "Producer Price Index monthly release",
    },
    {
        "event_type": EVENT_TYPE_JOBS_REPORT,
        "title": "Nonfarm Payrolls / Jobs Report",
        "source": "bls.gov",
        "confidence": CONFIDENCE_CONFIRMED,
        "importance_base": 85.0,
        "description": "Monthly employment situation report",
    },
    {
        "event_type": EVENT_TYPE_GDP_RELEASE,
        "title": "GDP Release",
        "source": "bea.gov",
        "confidence": CONFIDENCE_CONFIRMED,
        "importance_base": 75.0,
        "description": "Gross Domestic Product quarterly release",
    },
    {
        "event_type": EVENT_TYPE_FED_MINUTES,
        "title": "FOMC Minutes Release",
        "source": "federalreserve.gov",
        "confidence": CONFIDENCE_CONFIRMED,
        "importance_base": 70.0,
        "description": "Federal Reserve FOMC meeting minutes publication",
    },
]

# Known 2026 macro release dates (UTC). In production these would be fetched
# from BLS/BEA/Fed calendars. This static set ensures deterministic testing.
_MACRO_RELEASE_DATES_2026 = [
    # CPI releases (typically 2nd or 3rd Tuesday/Wednesday of month, 8:30 ET = 12:30 UTC)
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 1, 14, 13, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 2, 12, 13, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 3, 11, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 4, 14, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 5, 13, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 6, 10, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 7, 14, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 8, 12, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 9, 15, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 10, 13, 12, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 11, 12, 13, 30)},
    {"event_type": EVENT_TYPE_CPI_RELEASE, "date": datetime(2026, 12, 10, 13, 30)},
    # Jobs Report (first Friday of month, 8:30 ET)
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 1, 9, 13, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 2, 6, 13, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 3, 6, 13, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 4, 3, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 5, 8, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 6, 5, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 7, 2, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 8, 7, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 9, 4, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 10, 2, 12, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 11, 6, 13, 30)},
    {"event_type": EVENT_TYPE_JOBS_REPORT, "date": datetime(2026, 12, 4, 13, 30)},
    # PPI releases (day after or near CPI)
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 1, 15, 13, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 2, 13, 13, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 3, 12, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 4, 15, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 5, 14, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 6, 11, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 7, 15, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 8, 13, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 9, 16, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 10, 14, 12, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 11, 13, 13, 30)},
    {"event_type": EVENT_TYPE_PPI_RELEASE, "date": datetime(2026, 12, 11, 13, 30)},
    # GDP releases (end of month, quarterly)
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 1, 29, 13, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 3, 26, 12, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 4, 29, 12, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 6, 25, 12, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 7, 30, 12, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 9, 30, 12, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 10, 29, 12, 30)},
    {"event_type": EVENT_TYPE_GDP_RELEASE, "date": datetime(2026, 12, 22, 13, 30)},
    # Fed Minutes (3 weeks after FOMC meetings)
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 2, 19, 19, 0)},
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 4, 9, 18, 0)},
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 5, 27, 18, 0)},
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 7, 8, 18, 0)},
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 8, 19, 18, 0)},
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 10, 7, 18, 0)},
    {"event_type": EVENT_TYPE_FED_MINUTES, "date": datetime(2026, 11, 25, 19, 0)},
]


class MacroCalendarProvider(EnrichmentProvider):
    """Enrichment provider for major macroeconomic release dates.

    Provides CPI, PPI, Jobs Report, GDP, and Fed Minutes release dates.
    Uses a static calendar for deterministic, offline-safe operation with
    optional live-calendar augmentation in the future.
    """

    provider_name = "macro-calendar"
    event_types = [
        EVENT_TYPE_CPI_RELEASE,
        EVENT_TYPE_PPI_RELEASE,
        EVENT_TYPE_JOBS_REPORT,
        EVENT_TYPE_GDP_RELEASE,
        EVENT_TYPE_FED_MINUTES,
    ]

    def fetch(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Return macro release events within the sync window."""
        records: List[EnrichmentRecord] = []
        definitions = {d["event_type"]: d for d in _MACRO_EVENT_DEFINITIONS}

        for entry in _MACRO_RELEASE_DATES_2026:
            release_date = entry["date"]
            if not (window_start <= release_date <= window_end):
                continue
            event_type = entry["event_type"]
            defn = definitions.get(event_type, {})
            records.append(EnrichmentRecord(
                event_type=event_type,
                title=defn.get("title", event_type.replace("_", " ").title()),
                source=defn.get("source", "macro-calendar"),
                source_event_id=f"{event_type}:{release_date.strftime('%Y-%m-%d')}",
                category=CATEGORY_SCHEDULED_EVENT,
                description=defn.get("description"),
                event_date=release_date,
                start_at_utc=release_date,
                market_timezone="America/New_York",
                confidence=CONFIDENCE_CONFIRMED,
                importance_score=defn.get("importance_base", 50.0),
            ))
        return records


# ── Congressional Trading Provider ───────────────────────────────────────────


class CongressionalTradingProvider(EnrichmentProvider):
    """Enrichment provider for congressional trading disclosures.

    Treats disclosures as catalyst signals (not confirmed scheduled events)
    unless a future event date is clearly associated.

    In production this would integrate with CapitolTrades or similar.
    The provider degrades gracefully when the API is unavailable.
    """

    provider_name = "congressional-trades"
    event_types = [EVENT_TYPE_CONGRESSIONAL_TRADE]

    def fetch(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Fetch congressional trading disclosures.

        Returns empty list if the data source is unreachable.
        Congressional disclosures are treated as signals, not blockers.
        """
        # In production: call CapitolTrades API or equivalent
        # For now, degrade gracefully — no network dependency
        return []

    @staticmethod
    def normalize_disclosure(
        symbol: str,
        politician_name: str,
        transaction_type: str,
        transaction_date: Optional[datetime],
        disclosure_date: datetime,
        source_url: Optional[str] = None,
        amount_range: Optional[str] = None,
    ) -> EnrichmentRecord:
        """Normalize a congressional trading disclosure into an EnrichmentRecord."""
        title = f"Congressional trade: {politician_name} {transaction_type} {symbol}"
        importance = 50.0
        # Elevate for large transactions
        if amount_range and any(
            x in (amount_range or "").lower()
            for x in ["$1,000,001", "$5,000,001", "$15,000,001", "$50,000,001"]
        ):
            importance = 70.0

        return EnrichmentRecord(
            event_type=EVENT_TYPE_CONGRESSIONAL_TRADE,
            title=title[:200],
            source="congressional-trades",
            source_event_id=f"CONGRESS:{symbol}:{politician_name}:{disclosure_date.strftime('%Y-%m-%d')}",
            category=CATEGORY_CATALYST_SIGNAL,
            symbol=symbol.upper(),
            description=f"{politician_name} disclosed {transaction_type} of {symbol}",
            event_date=disclosure_date,
            start_at_utc=None,  # Signal only — no confirmed future event
            published_at_utc=disclosure_date,
            source_url=source_url,
            confidence=CONFIDENCE_SIGNAL,
            importance_score=importance,
            detail={
                "politician": politician_name,
                "transaction_type": transaction_type,
                "transaction_date": transaction_date.isoformat() if transaction_date else None,
                "amount_range": amount_range,
            },
        )


# ── Company Event Provider ───────────────────────────────────────────────────


class CompanyEventProvider(EnrichmentProvider):
    """Enrichment provider for scheduled company events.

    Covers investor days, conferences, product events, and shareholder meetings.
    In production this would pull from IR calendar feeds or conference aggregators.
    """

    provider_name = "company-events"
    event_types = [
        EVENT_TYPE_INVESTOR_DAY,
        EVENT_TYPE_CONFERENCE,
        EVENT_TYPE_PRODUCT_EVENT,
        EVENT_TYPE_SHAREHOLDER_MEETING,
    ]

    def fetch(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Fetch company events. Returns empty list if source unavailable."""
        # In production: query IR calendar feeds / conference aggregators
        return []

    @staticmethod
    def normalize_event(
        symbol: str,
        event_type: str,
        title: str,
        event_date: datetime,
        source_url: Optional[str] = None,
        confidence: str = CONFIDENCE_CONFIRMED,
        description: Optional[str] = None,
    ) -> EnrichmentRecord:
        """Normalize a company event into an EnrichmentRecord."""
        importance = 55.0
        if event_type == EVENT_TYPE_SHAREHOLDER_MEETING:
            importance = 60.0
        elif event_type == EVENT_TYPE_INVESTOR_DAY:
            importance = 65.0

        return EnrichmentRecord(
            event_type=event_type,
            title=title[:200],
            source="company-events",
            source_event_id=f"COMPANY:{symbol}:{event_type}:{event_date.strftime('%Y-%m-%d')}",
            category=CATEGORY_SCHEDULED_EVENT,
            symbol=symbol.upper(),
            description=description,
            event_date=event_date,
            start_at_utc=event_date,
            source_url=source_url,
            confidence=confidence,
            importance_score=importance,
        )


# ── News / Catalyst Signal Provider ─────────────────────────────────────────


class NewsCatalystProvider(EnrichmentProvider):
    """Enrichment provider for news-derived catalyst signals.

    Low-confidence signal path for market-moving catalysts that are not
    confirmed scheduled events. Kept visually and semantically distinct.
    """

    provider_name = "news-catalyst"
    event_types = [EVENT_TYPE_NEWS_CATALYST]

    def fetch(
        self,
        symbols: Sequence[str],
        window_start: datetime,
        window_end: datetime,
    ) -> List[EnrichmentRecord]:
        """Fetch news catalyst signals. Returns empty list if source unavailable."""
        # In production: query news aggregator APIs with rate limiting
        return []

    @staticmethod
    def normalize_signal(
        symbol: Optional[str],
        title: str,
        published_at: datetime,
        source_name: str,
        source_url: Optional[str] = None,
        importance_score: float = 30.0,
        description: Optional[str] = None,
    ) -> EnrichmentRecord:
        """Normalize a news catalyst signal into an EnrichmentRecord."""
        source_id = f"NEWS:{source_name}:{symbol or 'MACRO'}:{hashlib.sha256(title.encode()).hexdigest()[:16]}"

        return EnrichmentRecord(
            event_type=EVENT_TYPE_NEWS_CATALYST,
            title=title[:200],
            source="news-catalyst",
            source_event_id=source_id,
            category=CATEGORY_NEWS_CATALYST,
            symbol=symbol.upper() if symbol else None,
            description=description,
            event_date=None,
            start_at_utc=None,  # Signal only
            published_at_utc=published_at,
            source_url=source_url,
            confidence=CONFIDENCE_SIGNAL,
            importance_score=min(importance_score, 100.0),
            detail={"source_name": source_name},
        )


# ── Provider registry ────────────────────────────────────────────────────────


def get_default_providers() -> List[EnrichmentProvider]:
    """Return the default set of enrichment providers."""
    return [
        SECFilingProvider(),
        MacroCalendarProvider(),
        CongressionalTradingProvider(),
        CompanyEventProvider(),
        NewsCatalystProvider(),
    ]
