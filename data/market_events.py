"""Market event sync, storage, reminders, and readiness helpers.

The service stores scheduled or market-moving events locally and keeps the
default posture conservative: provider failures are logged, stale future
events are marked stale rather than deleted, and event-risk output is advisory
or blocking only where market access is clearly unsafe.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

EVENT_STATUS_ACTIVE = "active"
EVENT_STATUS_UPDATED = "updated"
EVENT_STATUS_CANCELLED = "cancelled"
EVENT_STATUS_STALE = "stale"

CONFIRMED = "confirmed"
ESTIMATED = "estimated"
TENTATIVE = "tentative"
SIGNAL = "signal"

SEVERITY_INFO = "info"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

_EARNINGS_TTL_HOURS = 6
_FOMC_TTL_HOURS = 24
_DIVIDEND_TTL_HOURS = 6

_DEFAULT_DAYS_AHEAD = 14
_SYNC_DAYS_AHEAD = 28
_MARKET_TZ = "America/New_York"
_FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


@dataclass
class ProviderSyncResult:
    provider: str
    event_type: str
    status: str = "success"
    fetched_count: int = 0
    upserted_count: int = 0
    stale_count: int = 0
    error_count: int = 0
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: _utcnow())
    finished_at: Optional[datetime] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "event_type": self.event_type,
            "status": self.status,
            "fetched_count": self.fetched_count,
            "upserted_count": self.upserted_count,
            "stale_count": self.stale_count,
            "error_count": self.error_count,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "detail": dict(self.detail),
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(payload: Any) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _squash(text_value: str) -> str:
    return re.sub(r"\s+", " ", str(text_value or "").strip())


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _to_utc_naive(dt: datetime, tz_name: str = _MARKET_TZ) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _time_hint_to_time(event_time: Optional[str]) -> time:
    hint = str(event_time or "").strip().upper()
    if hint == "BMO":
        return time(8, 0)
    if hint == "AMC":
        return time(16, 0)
    if hint == "TBD" or not hint:
        return time(0, 0)
    match = re.search(r"(\d{1,2}):(\d{2})", hint)
    if match:
        hour = max(0, min(23, int(match.group(1))))
        minute = max(0, min(59, int(match.group(2))))
        return time(hour, minute)
    return time(0, 0)


def _market_datetime_to_utc(
    event_date: Any,
    event_time: Optional[str],
    tz_name: str = _MARKET_TZ,
) -> Optional[datetime]:
    dt = _coerce_datetime(event_date)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return _to_utc_naive(dt, tz_name)
    hint = str(event_time or "").strip()
    if hint or (dt.hour == 0 and dt.minute == 0 and dt.second == 0):
        dt = datetime.combine(dt.date(), _time_hint_to_time(event_time))
    return _to_utc_naive(dt, tz_name)


def _event_source_id(event: Dict[str, Any], start_at_utc: datetime) -> str:
    explicit = event.get("source_event_id")
    if explicit:
        return str(explicit)
    fallback = "|".join([
        str(event.get("event_type") or "").upper(),
        str(event.get("symbol") or "").upper(),
        start_at_utc.isoformat(),
        _squash(str(event.get("title") or "")).lower(),
    ])
    return "fallback:" + hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]


def _event_id(source: str, source_event_id: str) -> str:
    raw = f"{source}|{source_event_id}"
    return "evt_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _normalize_event(event: Dict[str, Any], portfolio_symbols: Optional[Set[str]] = None) -> Dict[str, Any]:
    source = str(event.get("source") or "unknown")
    event_type = str(event["event_type"]).upper()
    symbol = event.get("symbol")
    symbol = str(symbol).upper() if symbol else None
    market_tz = str(event.get("market_timezone") or _MARKET_TZ)

    start_at_utc = _coerce_datetime(event.get("start_at_utc"))
    if start_at_utc is not None and start_at_utc.tzinfo is not None:
        start_at_utc = start_at_utc.astimezone(timezone.utc).replace(tzinfo=None)
    if start_at_utc is None:
        start_at_utc = _market_datetime_to_utc(
            event.get("event_date"),
            event.get("event_time"),
            market_tz,
        )
    if start_at_utc is None:
        # Allow nullable start_at_utc for signal-only enrichment events
        confidence = str(event.get("confidence") or CONFIRMED)
        if confidence == SIGNAL:
            # Use published_at_utc or current time as event_date fallback
            published = _coerce_datetime(event.get("published_at_utc"))
            start_at_utc = published or _utcnow()
        else:
            raise ValueError(f"Event has no parseable datetime: {event}")

    end_at_utc = _coerce_datetime(event.get("end_at_utc"))
    if end_at_utc is not None and end_at_utc.tzinfo is not None:
        end_at_utc = end_at_utc.astimezone(timezone.utc).replace(tzinfo=None)

    detail = event.get("detail") or {}
    raw_payload = event.get("raw_payload") or event
    raw_hash = event.get("raw_payload_hash") or _payload_hash(raw_payload)
    source_event_id = _event_source_id(event, start_at_utc)
    portfolio_set = {s.upper() for s in (portfolio_symbols or set())}

    normalized = {
        "event_id": event.get("event_id") or _event_id(source, source_event_id),
        "source": source,
        "source_event_id": source_event_id,
        "event_type": event_type,
        "symbol": symbol,
        "title": _squash(str(event.get("title") or event_type.title())),
        "description": _squash(str(event.get("description") or "")) or None,
        "event_date": start_at_utc,
        "event_time": event.get("event_time"),
        "start_at_utc": start_at_utc,
        "end_at_utc": end_at_utc,
        "market_timezone": market_tz,
        "confidence": str(event.get("confidence") or CONFIRMED),
        "importance_score": float(event.get("importance_score") or 0.0),
        "source_url": event.get("source_url"),
        "detail": detail,
        "raw_payload": raw_payload,
        "raw_payload_hash": raw_hash,
        "status": event.get("status") or EVENT_STATUS_ACTIVE,
        "is_portfolio_relevant": bool(symbol and symbol in portfolio_set),
    }
    return normalized


def _fetch_earnings_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the next earnings event dict for *symbol*, or None."""
    try:
        import yfinance as yf

        symbol = symbol.upper()
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return None

        earnings_dates = cal.get("Earnings Date") or cal.get("earningsDate") or []
        if not earnings_dates:
            return None

        now = datetime.now()
        future_dates = []
        for item in earnings_dates:
            dt = _coerce_datetime(item.to_pydatetime() if hasattr(item, "to_pydatetime") else item)
            if dt is None:
                continue
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            if dt.date() >= now.date():
                future_dates.append(dt)
        if not future_dates:
            return None

        event_dt = min(future_dates)
        eps_est = _safe_float(cal.get("EPS Estimate") or cal.get("epsEstimate"))
        rev_est = _safe_float(cal.get("Revenue Estimate") or cal.get("revenueEstimate"))

        if event_dt.hour == 0 and event_dt.minute == 0:
            event_time = "TBD"
        elif event_dt.hour < 9:
            event_time = "BMO"
        elif event_dt.hour >= 16:
            event_time = "AMC"
        else:
            event_time = f"{event_dt.strftime('%H:%M')} ET"

        short_name = symbol
        try:
            info = ticker.fast_info
            short_name = getattr(info, "shortName", None) or symbol
        except Exception:
            pass

        detail: Dict[str, Any] = {}
        if eps_est is not None:
            detail["eps_estimate"] = eps_est
        if rev_est is not None:
            detail["revenue_estimate"] = rev_est

        return {
            "event_type": "EARNINGS",
            "symbol": symbol,
            "title": f"{short_name} Earnings",
            "description": "Company earnings date from yfinance calendar.",
            "event_date": event_dt,
            "event_time": event_time,
            "source": "yfinance",
            "source_event_id": f"EARNINGS:{symbol}:{event_dt.date().isoformat()}",
            "confidence": ESTIMATED if event_time == "TBD" else CONFIRMED,
            "importance_score": 75.0,
            "detail": detail,
            "raw_payload": {"calendar": dict(cal), "symbol": symbol},
        }
    except Exception as exc:
        logger.warning("Earnings fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_dividend_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the next ex-dividend event dict for *symbol*, or None."""
    try:
        import yfinance as yf

        symbol = symbol.upper()
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        ex_div_ts = info.get("exDividendDate")
        if not ex_div_ts:
            return None

        try:
            ex_div_dt = datetime.fromtimestamp(int(ex_div_ts), timezone.utc)
        except (TypeError, ValueError):
            return None
        if ex_div_dt.date() < datetime.now(timezone.utc).date():
            return None

        detail: Dict[str, Any] = {}
        for src_key, dst_key in (
            ("dividendRate", "dividend_rate"),
            ("lastDividendValue", "last_dividend_value"),
            ("dividendYield", "dividend_yield"),
        ):
            val = _safe_float(info.get(src_key))
            if val is not None:
                detail[dst_key] = val
        short_name = info.get("shortName") or symbol

        return {
            "event_type": "DIVIDEND",
            "symbol": symbol,
            "title": f"{short_name} Ex-Dividend",
            "description": "Upcoming ex-dividend date from yfinance.",
            "start_at_utc": ex_div_dt,
            "event_time": None,
            "source": "yfinance",
            "source_event_id": f"DIVIDEND:{symbol}:{ex_div_dt.date().isoformat()}",
            "confidence": CONFIRMED,
            "importance_score": 35.0,
            "detail": detail,
            "raw_payload": {"info": info, "symbol": symbol},
        }
    except Exception as exc:
        logger.warning("Dividend fetch failed for %s: %s", symbol, exc)
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_fomc_dates() -> List[Dict[str, Any]]:
    """Parse the Federal Reserve's public FOMC calendar page."""
    events: List[Dict[str, Any]] = []
    try:
        import urllib.request

        req = urllib.request.Request(_FED_URL, headers={"User-Agent": "tws_robot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_text = resp.read().decode("utf-8", errors="replace")

        current_year = datetime.now().year
        year_sections = re.split(r'<h[34][^>]*>\s*(\d{4})\b[^<]{0,100}</h[34]>', html_text)
        for i in range(1, len(year_sections) - 1, 2):
            try:
                section_year = int(year_sections[i])
            except ValueError:
                continue
            if section_year < current_year or section_year > current_year + 1:
                continue

            block = year_sections[i + 1]
            date_matches = re.findall(
                r'<[^>]+class="[^"]*fomc-meeting__date[^"]*"[^>]*>\s*([^<]+?)\s*</[^>]+>',
                block,
            )
            if not date_matches:
                months = re.findall(
                    r'<[^>]+class="[^"]*fomc-meeting__month[^"]*"[^>]*>\s*([^<]+?)\s*</[^>]+>',
                    block,
                )
                days = re.findall(
                    r'<[^>]+class="[^"]*fomc-meeting__day[^"]*"[^>]*>\s*([^<]+?)\s*</[^>]+>',
                    block,
                )
                if months and days and len(months) == len(days):
                    date_matches = [f"{m.strip()} {d.strip()}" for m, d in zip(months, days)]
            if not date_matches:
                date_matches = re.findall(
                    r'<[^>]+class="[^"]*panel-title[^"]*"[^>]*>\s*([^<]+?)\s*</[^>]+>',
                    block,
                )
                date_matches = [
                    re.sub(r'[,:]?\s*\d{4}\b[^<]{0,50}', '', d).strip()
                    for d in date_matches
                ]
            if not date_matches:
                date_matches = re.findall(
                    r'(?:January|February|March|April|May|June|July|August|'
                    r'September|October|November|December)\s+\d[\d\-\s,]*',
                    block,
                )

            for raw_date in date_matches:
                event_dt = _parse_fomc_date_range(raw_date.strip().strip("*").strip(), section_year)
                if event_dt is None:
                    continue
                events.append({
                    "event_type": "FOMC",
                    "symbol": None,
                    "title": "FOMC Meeting",
                    "description": "Federal Open Market Committee scheduled decision day.",
                    "event_date": event_dt,
                    "event_time": "14:00 ET",
                    "source": "federalreserve.gov",
                    "source_event_id": f"FOMC:{event_dt.date().isoformat()}",
                    "source_url": _FED_URL,
                    "confidence": CONFIRMED,
                    "importance_score": 90.0,
                    "detail": {},
                    "raw_payload": {"raw_date": raw_date, "year": section_year},
                })
    except Exception as exc:
        logger.warning("FOMC fetch failed: %s", exc)

    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for ev in events:
        key = str(ev.get("source_event_id"))
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    logger.info("Fetched %d FOMC dates from federalreserve.gov", len(unique))
    return unique


_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _parse_fomc_date_range(raw: str, year: int) -> Optional[datetime]:
    """Parse a raw FOMC date string and return the end/decision day."""
    raw = raw.strip().strip("*").strip()
    month_names = "|".join(_MONTH_MAP.keys())
    match = re.match(
        rf"({month_names})\s+(\d+)\s*[-–]\s*({month_names})\s+(\d+)",
        raw,
        re.IGNORECASE,
    )
    if match:
        return _safe_date(year, _MONTH_MAP[match.group(3).lower()], int(match.group(4)))
    match = re.match(rf"({month_names})\s+(\d+)\s*[-–]\s*(\d+)", raw, re.IGNORECASE)
    if match:
        return _safe_date(year, _MONTH_MAP[match.group(1).lower()], int(match.group(3)))
    match = re.match(rf"({month_names})\s+(\d+)", raw, re.IGNORECASE)
    if match:
        return _safe_date(year, _MONTH_MAP[match.group(1).lower()], int(match.group(2)))
    return None


def _safe_date(year: int, month: int, day: int) -> Optional[datetime]:
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    raw = date(year, month, day)
    if raw.weekday() == 5:
        return raw - timedelta(days=1)
    if raw.weekday() == 6:
        return raw + timedelta(days=1)
    return raw


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (nth - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cur = date(year, 12, 31)
    else:
        cur = date(year, month + 1, 1) - timedelta(days=1)
    while cur.weekday() != weekday:
        cur -= timedelta(days=1)
    return cur


def _easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _market_holiday_dates(year: int) -> List[tuple[date, str]]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    return [
        (_observed_fixed_holiday(year, 1, 1), "New Year's Day"),
        (_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
        (_nth_weekday(year, 2, 0, 3), "Washington's Birthday"),
        (_easter_date(year) - timedelta(days=2), "Good Friday"),
        (_last_weekday(year, 5, 0), "Memorial Day"),
        (_observed_fixed_holiday(year, 6, 19), "Juneteenth National Independence Day"),
        (_observed_fixed_holiday(year, 7, 4), "Independence Day"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day"),
        (thanksgiving, "Thanksgiving Day"),
        (_observed_fixed_holiday(year, 12, 25), "Christmas Day"),
    ]


def _market_early_close_dates(year: int) -> List[tuple[date, str]]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    candidates = [
        (thanksgiving + timedelta(days=1), "Day After Thanksgiving Early Close"),
        (date(year, 12, 24), "Christmas Eve Early Close"),
    ]
    july3 = date(year, 7, 3)
    if july3.weekday() < 5 and _observed_fixed_holiday(year, 7, 4) != july3:
        candidates.append((july3, "Independence Day Early Close"))
    return [(d, name) for d, name in candidates if d.weekday() < 5]


def _fetch_market_holidays(window_start: datetime, window_end: datetime) -> List[Dict[str, Any]]:
    """Return deterministic NYSE/Nasdaq full holidays and early closes."""
    events: List[Dict[str, Any]] = []
    start_date = window_start.date()
    end_date = window_end.date()
    for year in range(start_date.year, end_date.year + 1):
        for day, name in _market_holiday_dates(year):
            if start_date <= day <= end_date:
                events.append({
                    "event_type": "MARKET_HOLIDAY",
                    "symbol": None,
                    "title": f"NYSE/Nasdaq Closed: {name}",
                    "description": "US equity markets are closed.",
                    "event_date": datetime.combine(day, time.min),
                    "event_time": "All day",
                    "source": "builtin-us-market-calendar",
                    "source_event_id": f"US_MARKET_HOLIDAY:{day.isoformat()}",
                    "confidence": CONFIRMED,
                    "importance_score": 100.0,
                    "detail": {"holiday_name": name, "market": "NYSE/Nasdaq"},
                })
        for day, name in _market_early_close_dates(year):
            if start_date <= day <= end_date:
                events.append({
                    "event_type": "MARKET_EARLY_CLOSE",
                    "symbol": None,
                    "title": f"NYSE/Nasdaq Early Close: {name}",
                    "description": "US equity markets are scheduled to close early.",
                    "event_date": datetime.combine(day, time(13, 0)),
                    "event_time": "13:00 ET",
                    "source": "builtin-us-market-calendar",
                    "source_event_id": f"US_MARKET_EARLY_CLOSE:{day.isoformat()}",
                    "confidence": CONFIRMED,
                    "importance_score": 85.0,
                    "detail": {"holiday_name": name, "market": "NYSE/Nasdaq"},
                })
    return events


class MarketEventsService:
    """Manages market event data with DB persistence and TTL refreshing."""

    def __init__(self, database=None):
        self._lock = threading.Lock()
        self._db = database
        self._refreshing = False
        self._last_fetched: Dict[str, datetime] = {}
        self._schema_checked = False
        self._last_sync_summary: Optional[Dict[str, Any]] = None

    def _get_db(self):
        if self._db is None:
            from data.database import get_database

            self._db = get_database()
        self._db.create_tables()
        self._ensure_schema()
        return self._db

    def _ensure_schema(self) -> None:
        if self._schema_checked or self._db is None or not hasattr(self._db, "engine"):
            return
        engine = self._db.engine
        inspector = inspect(engine)
        if "market_events" not in inspector.get_table_names():
            self._schema_checked = True
            return
        existing = {col["name"] for col in inspector.get_columns("market_events")}
        datetime_type = "TIMESTAMP" if engine.dialect.name.startswith("postgres") else "DATETIME"
        type_map = {
            "event_id": "VARCHAR(128)",
            "description": "TEXT",
            "start_at_utc": datetime_type,
            "end_at_utc": datetime_type,
            "market_timezone": "VARCHAR(64)",
            "source_event_id": "VARCHAR(200)",
            "source_url": "TEXT",
            "raw_payload_json": "TEXT",
            "raw_payload_hash": "VARCHAR(64)",
            "confidence": "VARCHAR(20)",
            "importance_score": "FLOAT",
            "status": "VARCHAR(20)",
            "last_seen_at": datetime_type,
            "updated_at": datetime_type,
        }
        missing = set(type_map) - existing
        if missing:
            with engine.begin() as conn:
                for column in sorted(missing):
                    conn.execute(text(f"ALTER TABLE market_events ADD COLUMN {column} {type_map[column]}"))
        with engine.begin() as conn:
            conn.execute(text("UPDATE market_events SET status = 'active' WHERE status IS NULL"))
            conn.execute(text("UPDATE market_events SET start_at_utc = event_date WHERE start_at_utc IS NULL"))
            conn.execute(text("UPDATE market_events SET last_seen_at = fetched_at WHERE last_seen_at IS NULL"))
            conn.execute(text("UPDATE market_events SET updated_at = fetched_at WHERE updated_at IS NULL"))
        self._schema_checked = True

    def get_upcoming_events(
        self,
        days_ahead: int = _DEFAULT_DAYS_AHEAD,
        portfolio_symbols: Optional[List[str]] = None,
        event_types: Optional[Sequence[str]] = None,
        symbols: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return events occurring within the next *days_ahead* calendar days."""
        try:
            from data.models import MarketEvent

            db = self._get_db()
            now = _utcnow()
            cutoff = now + timedelta(days=days_ahead)
            portfolio_set = {s.upper() for s in (portfolio_symbols or [])}
            type_filter = {s.upper() for s in (event_types or []) if s}
            symbol_filter = {s.upper() for s in (symbols or []) if s}
            status_filter = {s.lower() for s in (statuses or []) if s} or {
                EVENT_STATUS_ACTIVE,
                EVENT_STATUS_UPDATED,
            }

            with db.session_scope() as session:
                query = session.query(MarketEvent).filter(
                    MarketEvent.event_date >= now,
                    MarketEvent.event_date <= cutoff,
                )
                if type_filter:
                    query = query.filter(MarketEvent.event_type.in_(sorted(type_filter)))
                if symbol_filter:
                    query = query.filter(MarketEvent.symbol.in_(sorted(symbol_filter)))
                if status_filter:
                    query = query.filter(MarketEvent.status.in_(sorted(status_filter)))
                rows = query.order_by(MarketEvent.event_date.asc()).all()

                result = []
                for row in rows:
                    item = row.to_dict()
                    if portfolio_set:
                        item["is_portfolio_relevant"] = (
                            row.symbol is not None and row.symbol.upper() in portfolio_set
                        )
                    item["days_away"] = _days_away(row.event_date, now)
                    item["severity"] = _severity_for_event(item, now=now)
                    result.append(item)
                return result
        except Exception as exc:
            logger.error("get_upcoming_events failed: %s", exc)
            return []

    def refresh(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        force: bool = False,
        days_ahead: int = _SYNC_DAYS_AHEAD,
    ) -> Dict[str, Any]:
        """Fetch fresh event data from external sources and persist to DB."""
        with self._lock:
            if self._refreshing:
                return {
                    "status": "already_refreshing",
                    "provider_results": [],
                    "days_ahead": days_ahead,
                }
            self._refreshing = True
        try:
            summary = self.sync_market_events(
                portfolio_symbols=portfolio_symbols,
                force=force,
                days_ahead=days_ahead,
            )
            self._last_sync_summary = summary
            return summary
        except Exception as exc:
            logger.error("MarketEventsService.refresh failed: %s", exc)
            summary = {"status": "failed", "error": str(exc), "provider_results": []}
            self._last_sync_summary = summary
            return summary
        finally:
            with self._lock:
                self._refreshing = False

    def refresh_async(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        force: bool = False,
        days_ahead: int = _SYNC_DAYS_AHEAD,
    ) -> None:
        with self._lock:
            if self._refreshing:
                return
        thread = threading.Thread(
            target=self.refresh,
            kwargs={
                "portfolio_symbols": portfolio_symbols,
                "force": force,
                "days_ahead": days_ahead,
            },
            daemon=True,
        )
        thread.start()

    def sync_market_events(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        force: bool = False,
        days_ahead: int = _SYNC_DAYS_AHEAD,
    ) -> Dict[str, Any]:
        symbols = sorted({s.upper() for s in (portfolio_symbols or []) if s})
        window_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(days=days_ahead)
        provider_results: List[ProviderSyncResult] = []

        if symbols:
            provider_results.append(
                self._sync_symbol_provider(
                    provider="yfinance",
                    event_type="EARNINGS",
                    symbols=symbols,
                    fetcher=_fetch_earnings_for_symbol,
                    ttl_hours=_EARNINGS_TTL_HOURS,
                    force=force,
                    window_start=window_start,
                    window_end=window_end,
                )
            )
            provider_results.append(
                self._sync_symbol_provider(
                    provider="yfinance",
                    event_type="DIVIDEND",
                    symbols=symbols,
                    fetcher=_fetch_dividend_for_symbol,
                    ttl_hours=_DIVIDEND_TTL_HOURS,
                    force=force,
                    window_start=window_start,
                    window_end=window_end,
                )
            )

        provider_results.append(
            self._sync_static_provider(
                provider="federalreserve.gov",
                event_type="FOMC",
                events_fetcher=_fetch_fomc_dates,
                ttl_key="FOMC",
                ttl_hours=_FOMC_TTL_HOURS,
                force=force,
                window_start=window_start,
                window_end=window_end,
            )
        )
        provider_results.append(
            self._sync_static_provider(
                provider="builtin-us-market-calendar",
                event_type="MARKET_HOLIDAY",
                events_fetcher=lambda: _fetch_market_holidays(window_start, window_end),
                ttl_key="MARKET_CALENDAR",
                ttl_hours=_FOMC_TTL_HOURS,
                force=force,
                window_start=window_start,
                window_end=window_end,
                stale_event_types=["MARKET_HOLIDAY", "MARKET_EARLY_CLOSE"],
            )
        )

        # ── Enrichment providers ─────────────────────────────────────────
        provider_results.extend(
            self._sync_enrichment_providers(
                symbols=symbols,
                force=force,
                window_start=window_start,
                window_end=window_end,
            )
        )

        status = "success"
        if any(r.status == "failed" for r in provider_results):
            status = "partial_failure"
        summary = {
            "status": status,
            "days_ahead": days_ahead,
            "window_start_utc": window_start.isoformat(),
            "window_end_utc": window_end.isoformat(),
            "portfolio_symbols": symbols,
            "provider_results": [r.to_dict() for r in provider_results],
            "total_fetched": sum(r.fetched_count for r in provider_results),
            "total_upserted": sum(r.upserted_count for r in provider_results),
            "total_stale": sum(r.stale_count for r in provider_results),
            "total_errors": sum(r.error_count for r in provider_results),
        }
        self._last_sync_summary = summary
        return summary

    def _sync_symbol_provider(
        self,
        *,
        provider: str,
        event_type: str,
        symbols: Sequence[str],
        fetcher,
        ttl_hours: int,
        force: bool,
        window_start: datetime,
        window_end: datetime,
    ) -> ProviderSyncResult:
        result = ProviderSyncResult(provider=provider, event_type=event_type)
        events = []
        fetched_symbols: Set[str] = set()
        try:
            for symbol in symbols:
                key = f"{event_type}:{symbol}"
                if not force and self._ttl_ok(key, ttl_hours):
                    continue
                fetched_symbols.add(symbol)
                event = fetcher(symbol)
                if event is not None:
                    events.append(event)
                with self._lock:
                    self._last_fetched[key] = datetime.now()
            result.fetched_count = len(events)
            result.upserted_count, seen_ids = self._upsert_events(
                events,
                portfolio_symbols=set(symbols),
                window_start=window_start,
                window_end=window_end,
            )
            if fetched_symbols:
                result.stale_count = self._mark_missing_future_events_stale(
                    source=provider,
                    event_types=[event_type],
                    seen_event_ids=seen_ids,
                    window_start=window_start,
                    window_end=window_end,
                    symbols=fetched_symbols,
                )
        except Exception as exc:
            result.status = "failed"
            result.error_count += 1
            result.error_message = str(exc)
            logger.warning("%s %s sync failed: %s", provider, event_type, exc)
        finally:
            result.finished_at = _utcnow()
            self._record_sync_log(result, window_start, window_end, {"symbols": list(symbols)})
        return result

    def _sync_static_provider(
        self,
        *,
        provider: str,
        event_type: str,
        events_fetcher,
        ttl_key: str,
        ttl_hours: int,
        force: bool,
        window_start: datetime,
        window_end: datetime,
        stale_event_types: Optional[Sequence[str]] = None,
    ) -> ProviderSyncResult:
        result = ProviderSyncResult(provider=provider, event_type=event_type)
        try:
            if not force and self._ttl_ok(ttl_key, ttl_hours):
                events: List[Dict[str, Any]] = []
                fetched = False
            else:
                events = list(events_fetcher() or [])
                fetched = True
                with self._lock:
                    self._last_fetched[ttl_key] = datetime.now()
            result.fetched_count = len(events)
            result.upserted_count, seen_ids = self._upsert_events(
                events,
                portfolio_symbols=set(),
                window_start=window_start,
                window_end=window_end,
            )
            if fetched:
                result.stale_count = self._mark_missing_future_events_stale(
                    source=provider,
                    event_types=stale_event_types or [event_type],
                    seen_event_ids=seen_ids,
                    window_start=window_start,
                    window_end=window_end,
                    symbols=None,
                )
        except Exception as exc:
            result.status = "failed"
            result.error_count += 1
            result.error_message = str(exc)
            logger.warning("%s %s sync failed: %s", provider, event_type, exc)
        finally:
            result.finished_at = _utcnow()
            self._record_sync_log(result, window_start, window_end, {})
        return result

    def _sync_enrichment_providers(
        self,
        *,
        symbols: List[str],
        force: bool,
        window_start: datetime,
        window_end: datetime,
    ) -> List[ProviderSyncResult]:
        """Run all enrichment providers and return their sync results.

        Each provider is isolated: a failure in one provider does not affect
        others or existing durable events.
        """
        from data.enrichment_providers import get_default_providers

        results: List[ProviderSyncResult] = []
        ttl_hours = 12  # Enrichment providers refresh every 12 hours

        for provider in get_default_providers():
            ttl_key = f"enrichment:{provider.provider_name}"
            if not force and self._ttl_ok(ttl_key, ttl_hours):
                continue

            result = ProviderSyncResult(
                provider=provider.provider_name,
                event_type=",".join(provider.event_types),
            )
            try:
                records, error = provider.fetch_safe(symbols, window_start, window_end)
                if error:
                    result.error_count = 1
                    result.error_message = error
                    result.status = "failed"
                else:
                    event_dicts = [r.to_event_dict() for r in records]
                    result.fetched_count = len(event_dicts)
                    result.upserted_count, seen_ids = self._upsert_events(
                        event_dicts,
                        portfolio_symbols=set(symbols),
                        window_start=window_start,
                        window_end=window_end,
                    )
                    with self._lock:
                        self._last_fetched[ttl_key] = datetime.now()
            except Exception as exc:
                result.status = "failed"
                result.error_count += 1
                result.error_message = str(exc)
                logger.warning(
                    "Enrichment provider %s failed: %s",
                    provider.provider_name,
                    exc,
                )
            finally:
                result.finished_at = _utcnow()
                self._record_sync_log(result, window_start, window_end, {
                    "provider_type": "enrichment",
                })
            results.append(result)
        return results

    def _upsert_events(
        self,
        events: Iterable[Dict[str, Any]],
        *,
        portfolio_symbols: Set[str],
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[int, Set[str]]:
        count = 0
        seen_ids: Set[str] = set()
        for event in events:
            normalized = _normalize_event(event, portfolio_symbols=portfolio_symbols)
            if not (window_start <= normalized["start_at_utc"] <= window_end):
                continue
            self._upsert_event(normalized)
            seen_ids.add(normalized["event_id"])
            count += 1
        return count, seen_ids

    def _upsert_event(self, event: Dict[str, Any]) -> None:
        from data.models import MarketEvent

        db = self._get_db()
        now = _utcnow()
        detail_json = _json_dumps(event.get("detail"))
        raw_json = _json_dumps(event.get("raw_payload"))

        with db.session_scope() as session:
            existing = None
            if event.get("event_id"):
                existing = session.query(MarketEvent).filter_by(event_id=event["event_id"]).first()
            if existing is None:
                existing = (
                    session.query(MarketEvent)
                    .filter_by(
                        event_type=event["event_type"],
                        symbol=event.get("symbol"),
                        event_date=event["event_date"],
                    )
                    .first()
                )
            if existing:
                existing.event_id = event["event_id"]
                existing.source_event_id = event["source_event_id"]
                existing.title = event["title"]
                existing.description = event.get("description")
                existing.event_time = event.get("event_time")
                existing.start_at_utc = event["start_at_utc"]
                existing.end_at_utc = event.get("end_at_utc")
                existing.market_timezone = event.get("market_timezone")
                existing.source = event.get("source")
                existing.source_url = event.get("source_url")
                existing.detail_json = detail_json
                existing.raw_payload_json = raw_json
                existing.raw_payload_hash = event.get("raw_payload_hash")
                existing.is_portfolio_relevant = event.get("is_portfolio_relevant", False)
                existing.confidence = event.get("confidence")
                existing.importance_score = event.get("importance_score")
                existing.status = EVENT_STATUS_UPDATED
                existing.last_seen_at = now
                existing.fetched_at = now
                existing.updated_at = now
            else:
                session.add(MarketEvent(
                    event_id=event["event_id"],
                    event_type=event["event_type"],
                    symbol=event.get("symbol"),
                    title=event["title"],
                    description=event.get("description"),
                    event_date=event["event_date"],
                    event_time=event.get("event_time"),
                    start_at_utc=event["start_at_utc"],
                    end_at_utc=event.get("end_at_utc"),
                    market_timezone=event.get("market_timezone"),
                    source=event.get("source"),
                    source_event_id=event.get("source_event_id"),
                    source_url=event.get("source_url"),
                    detail_json=detail_json,
                    raw_payload_json=raw_json,
                    raw_payload_hash=event.get("raw_payload_hash"),
                    is_portfolio_relevant=event.get("is_portfolio_relevant", False),
                    confidence=event.get("confidence"),
                    importance_score=event.get("importance_score"),
                    status=EVENT_STATUS_ACTIVE,
                    last_seen_at=now,
                    fetched_at=now,
                    created_at=now,
                    updated_at=now,
                ))

    def _mark_missing_future_events_stale(
        self,
        *,
        source: str,
        event_types: Sequence[str],
        seen_event_ids: Set[str],
        window_start: datetime,
        window_end: datetime,
        symbols: Optional[Set[str]],
    ) -> int:
        from data.models import MarketEvent

        db = self._get_db()
        now = _utcnow()
        with db.session_scope() as session:
            query = session.query(MarketEvent).filter(
                MarketEvent.source == source,
                MarketEvent.event_type.in_([et.upper() for et in event_types]),
                MarketEvent.event_date >= window_start,
                MarketEvent.event_date <= window_end,
                MarketEvent.status.in_([EVENT_STATUS_ACTIVE, EVENT_STATUS_UPDATED]),
            )
            if symbols is not None:
                if not symbols:
                    return 0
                query = query.filter(MarketEvent.symbol.in_(sorted(symbols)))
            rows = query.all()
            stale_count = 0
            for row in rows:
                if row.event_id and row.event_id in seen_event_ids:
                    continue
                row.status = EVENT_STATUS_STALE
                row.updated_at = now
                stale_count += 1
            return stale_count

    def _record_sync_log(
        self,
        result: ProviderSyncResult,
        window_start: datetime,
        window_end: datetime,
        detail: Dict[str, Any],
    ) -> None:
        try:
            from data.models import MarketEventSyncLog

            db = self._get_db()
            payload = {**detail, **result.detail}
            with db.session_scope() as session:
                session.add(MarketEventSyncLog(
                    provider=result.provider,
                    event_type=result.event_type,
                    sync_started_at=result.started_at,
                    sync_finished_at=result.finished_at,
                    window_start_utc=window_start,
                    window_end_utc=window_end,
                    status=result.status,
                    fetched_count=result.fetched_count,
                    upserted_count=result.upserted_count,
                    stale_count=result.stale_count,
                    error_count=result.error_count,
                    error_message=result.error_message,
                    detail_json=_json_dumps(payload),
                ))
        except Exception:
            logger.exception("Failed to record market event sync log")

    def get_sync_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            from data.models import MarketEventSyncLog

            db = self._get_db()
            with db.session_scope() as session:
                rows = (
                    session.query(MarketEventSyncLog)
                    .order_by(MarketEventSyncLog.sync_started_at.desc())
                    .limit(max(1, min(int(limit), 100)))
                    .all()
                )
                return [row.to_dict() for row in rows]
        except Exception as exc:
            logger.warning("get_sync_logs failed: %s", exc)
            return []

    def get_last_sync_summary(self) -> Optional[Dict[str, Any]]:
        return self._last_sync_summary

    def get_ticker_items(
        self,
        days_ahead: int = 28,
        portfolio_symbols: Optional[List[str]] = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        events = self.get_upcoming_events(days_ahead=days_ahead, portfolio_symbols=portfolio_symbols)
        # Exclude low-confidence signals from ticker unless high importance
        filtered = []
        for event in events:
            confidence = str(event.get("confidence") or CONFIRMED).lower()
            importance = float(event.get("importance_score") or 0.0)
            if confidence == SIGNAL and importance < 70:
                continue
            filtered.append(event)
        return [
            {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "symbol": event.get("symbol"),
                "title": event.get("title"),
                "days_away": event.get("days_away"),
                "severity": event.get("severity"),
                "confidence": event.get("confidence"),
                "text": _ticker_text(event),
            }
            for event in filtered[: max(1, min(limit, 20))]
        ]

    def get_reminders(
        self,
        days_ahead: int = 7,
        portfolio_symbols: Optional[List[str]] = None,
        mode: str = "high_only",
    ) -> List[Dict[str, Any]]:
        events = self.get_upcoming_events(days_ahead=days_ahead, portfolio_symbols=portfolio_symbols)
        reminders = []
        mode = (mode or "high_only").lower()
        for event in events:
            severity = event.get("severity") or SEVERITY_INFO
            confidence = str(event.get("confidence") or CONFIRMED).lower()
            # Exclude low-confidence signals from reminders unless mode is "all"
            if confidence == SIGNAL and mode != "all":
                continue
            if mode == "off":
                continue
            if mode == "high_only" and severity not in {SEVERITY_HIGH, SEVERITY_CRITICAL}:
                continue
            if mode == "medium_high" and severity == SEVERITY_INFO:
                continue
            reminders.append({
                "event_id": event.get("event_id"),
                "severity": severity,
                "confidence": confidence,
                "event": event,
                "message": _reminder_message(event),
                "recommended_action": _recommended_action(event),
            })
        return reminders

    def evaluate_event_risk(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        days_ahead: int = 7,
    ) -> Dict[str, Any]:
        events = self.get_upcoming_events(days_ahead=days_ahead, portfolio_symbols=portfolio_symbols)
        warnings = []
        blockers = []
        for event in events:
            severity = event.get("severity")
            confidence = str(event.get("confidence") or CONFIRMED).lower()
            item = {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "symbol": event.get("symbol"),
                "title": event.get("title"),
                "days_away": event.get("days_away"),
                "severity": severity,
                "confidence": confidence,
                "message": _reminder_message(event),
            }
            # Signal-confidence events can only produce warnings, never blockers.
            # This ensures enrichment sources cannot make readiness more permissive
            # or accidentally block trading from unconfirmed signals.
            if confidence == SIGNAL:
                if severity in {SEVERITY_MEDIUM, SEVERITY_HIGH}:
                    warnings.append(item)
                continue
            if severity == SEVERITY_CRITICAL:
                blockers.append(item)
            elif severity in {SEVERITY_MEDIUM, SEVERITY_HIGH}:
                warnings.append(item)
        return {
            "enabled": True,
            "checked_days": days_ahead,
            "portfolio_symbols": sorted({s.upper() for s in (portfolio_symbols or [])}),
            "blockers": blockers,
            "warnings": warnings,
            "events_considered": len(events),
            "max_severity": _max_severity([e.get("severity") for e in events]),
        }

    def is_stale(self, event_type: str = "FOMC") -> bool:
        with self._lock:
            last = self._last_fetched.get(event_type)
        if last is None:
            return True
        ttl_hours = _FOMC_TTL_HOURS if event_type == "FOMC" else _EARNINGS_TTL_HOURS
        return (datetime.now() - last).total_seconds() > ttl_hours * 3600

    def _ttl_ok(self, key: str, ttl_hours: int) -> bool:
        last = self._last_fetched.get(key)
        if last is None:
            return False
        return (datetime.now() - last).total_seconds() < ttl_hours * 3600

    def _refresh_earnings(self, symbols: List[str], force: bool = False) -> None:
        self._sync_symbol_provider(
            provider="yfinance",
            event_type="EARNINGS",
            symbols=symbols,
            fetcher=_fetch_earnings_for_symbol,
            ttl_hours=_EARNINGS_TTL_HOURS,
            force=force,
            window_start=_utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            window_end=_utcnow() + timedelta(days=_SYNC_DAYS_AHEAD),
        )

    def _refresh_dividends(self, symbols: List[str], force: bool = False) -> None:
        self._sync_symbol_provider(
            provider="yfinance",
            event_type="DIVIDEND",
            symbols=symbols,
            fetcher=_fetch_dividend_for_symbol,
            ttl_hours=_DIVIDEND_TTL_HOURS,
            force=force,
            window_start=_utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            window_end=_utcnow() + timedelta(days=_SYNC_DAYS_AHEAD),
        )

    def _refresh_fomc(self, force: bool = False) -> None:
        window_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        self._sync_static_provider(
            provider="federalreserve.gov",
            event_type="FOMC",
            events_fetcher=_fetch_fomc_dates,
            ttl_key="FOMC",
            ttl_hours=_FOMC_TTL_HOURS,
            force=force,
            window_start=window_start,
            window_end=window_start + timedelta(days=365),
        )


def _days_away(event_dt: Optional[datetime], now: datetime) -> Optional[int]:
    try:
        if event_dt is None:
            return None
        return max(0, (event_dt.date() - now.date()).days)
    except Exception:
        return None


def _severity_for_event(event: Dict[str, Any], now: Optional[datetime] = None) -> str:
    now = now or _utcnow()
    days = event.get("days_away")
    if days is None:
        days = _days_away(_coerce_datetime(event.get("event_date")), now)
    event_type = str(event.get("event_type") or "").upper()
    relevant = bool(event.get("is_portfolio_relevant"))
    importance = float(event.get("importance_score") or 0.0)
    confidence = str(event.get("confidence") or CONFIRMED).lower()

    # Signal-only events (low confidence) are capped at medium severity
    # to avoid false alarms from unconfirmed catalysts
    is_signal = confidence == SIGNAL

    if event_type == "MARKET_HOLIDAY" and days == 0:
        return SEVERITY_CRITICAL
    if event_type == "MARKET_EARLY_CLOSE" and days == 0:
        return SEVERITY_CRITICAL
    if event_type in {"FOMC", "CPI", "PPI", "JOBS_REPORT", "GDP",
                      "CPI_RELEASE", "PPI_RELEASE", "GDP_RELEASE",
                      "FED_MINUTES"} and days is not None:
        if days <= 1:
            return SEVERITY_HIGH
        if days <= 3:
            return SEVERITY_MEDIUM
    if event_type == "EARNINGS" and days is not None:
        if days <= 1:
            return SEVERITY_HIGH
        if days <= 3 or relevant:
            return SEVERITY_MEDIUM
    if event_type == "DIVIDEND" and days is not None:
        if relevant and days <= 1:
            return SEVERITY_MEDIUM
        return SEVERITY_INFO
    # SEC filings with high importance
    if event_type.startswith("SEC_") and days is not None:
        if is_signal:
            if importance >= 80 and days <= 1:
                return SEVERITY_MEDIUM
            return SEVERITY_INFO
        if importance >= 80 and days <= 1:
            return SEVERITY_HIGH
        if importance >= 60 and days <= 3:
            return SEVERITY_MEDIUM
    # Congressional trades and news catalysts: warn-only by default
    if event_type in {"CONGRESSIONAL_TRADE", "NEWS_CATALYST"}:
        if is_signal:
            if importance >= 80:
                return SEVERITY_MEDIUM
            return SEVERITY_INFO
        return SEVERITY_INFO
    if importance >= 90 and days is not None and days <= 1:
        return SEVERITY_HIGH if not is_signal else SEVERITY_MEDIUM
    if importance >= 70 and days is not None and days <= 3:
        return SEVERITY_MEDIUM
    return SEVERITY_INFO


def _max_severity(severities: Iterable[Optional[str]]) -> str:
    order = {
        SEVERITY_INFO: 0,
        SEVERITY_MEDIUM: 1,
        SEVERITY_HIGH: 2,
        SEVERITY_CRITICAL: 3,
    }
    best = SEVERITY_INFO
    for severity in severities:
        if order.get(severity or SEVERITY_INFO, 0) > order[best]:
            best = severity or SEVERITY_INFO
    return best


def _ticker_text(event: Dict[str, Any]) -> str:
    days = event.get("days_away")
    if days == 0:
        when = "today"
    elif days == 1:
        when = "tomorrow"
    elif days is None:
        when = "upcoming"
    else:
        when = f"in {days} days"
    symbol = f"{event.get('symbol')} " if event.get("symbol") else ""
    return f"{symbol}{event.get('title')} {when}"


def _reminder_message(event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").upper()
    title = event.get("title") or "Market event"
    days = event.get("days_away")
    if days == 0:
        when = "today"
    elif days == 1:
        when = "tomorrow"
    elif days is None:
        when = "soon"
    else:
        when = f"in {days} days"
    if event_type == "EARNINGS":
        return f"Earnings risk alert: {title} is {when}."
    if event_type == "FOMC":
        return f"High-impact macro event: {title} is {when}."
    if event_type == "MARKET_HOLIDAY":
        return f"Market holiday: {title} is {when}."
    if event_type == "MARKET_EARLY_CLOSE":
        return f"Market early close: {title} is {when}."
    if event_type in {"CPI_RELEASE", "PPI_RELEASE", "JOBS_REPORT", "GDP_RELEASE", "FED_MINUTES"}:
        return f"High-impact macro event: {title} is {when}."
    if event_type.startswith("SEC_"):
        return f"SEC filing alert: {title} {when}."
    if event_type == "CONGRESSIONAL_TRADE":
        return f"Congressional trade signal: {title} {when}."
    if event_type == "NEWS_CATALYST":
        return f"Market catalyst signal: {title} {when}."
    if event_type in {"INVESTOR_DAY", "CONFERENCE", "PRODUCT_EVENT", "SHAREHOLDER_MEETING"}:
        return f"Company event: {title} is {when}."
    return f"Upcoming event: {title} is {when}."


def _recommended_action(event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").upper()
    confidence = str(event.get("confidence") or CONFIRMED).lower()
    if event_type in {"MARKET_HOLIDAY", "MARKET_EARLY_CLOSE"}:
        return "Verify market-hours assumptions before allowing automated entries."
    if event_type == "EARNINGS":
        return "Review open exposure and avoid fresh entries unless earnings-event trading is allowed."
    if event_type == "FOMC":
        return "Review open positions and consider reducing new trade aggressiveness."
    if event_type in {"CPI_RELEASE", "PPI_RELEASE", "JOBS_REPORT", "GDP_RELEASE", "FED_MINUTES"}:
        return "Review open positions and consider reducing new trade aggressiveness ahead of macro release."
    if event_type.startswith("SEC_"):
        return "Review filing details for material impact before opening new positions."
    if confidence == SIGNAL:
        return "Informational signal only. Review context but no automated action required."
    return "Review event context before opening new risk."


_instance: Optional[MarketEventsService] = None
_instance_lock = threading.Lock()


def get_market_events_service() -> MarketEventsService:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MarketEventsService()
    return _instance
