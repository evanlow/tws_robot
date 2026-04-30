"""Market Events Service — fetches and persists upcoming market-moving events.

Supported event types
---------------------
EARNINGS  — quarterly earnings releases for portfolio symbols (via yfinance)
FOMC      — Federal Open Market Committee meeting dates (federalreserve.gov)
DIVIDEND  — ex-dividend dates for held symbols (via yfinance)

Events are stored in the ``market_events`` table with a unique constraint on
``(event_type, symbol, event_date)`` to avoid duplicates across refreshes.

TTL rules
---------
- EARNINGS / DIVIDEND : refresh at most once every 6 hours per symbol
- FOMC                : refresh at most once per 24 hours

Usage::

    from data.market_events import get_market_events_service

    svc = get_market_events_service()
    events = svc.get_upcoming_events(days_ahead=14, portfolio_symbols=["GOOG"])
    svc.refresh(portfolio_symbols=["GOOG", "AAPL"])
"""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── TTL constants ──────────────────────────────────────────────────────────────
_EARNINGS_TTL_HOURS = 6
_FOMC_TTL_HOURS = 24
_DIVIDEND_TTL_HOURS = 6

# ── Look-ahead window for "upcoming" queries ───────────────────────────────────
_DEFAULT_DAYS_AHEAD = 14
_FOMC_FETCH_DAYS = 365    # fetch a full year of FOMC dates at once


# ──────────────────────────────────────────────────────────────────────────────
# Fetcher helpers (module-level, no DB dependency)
# ──────────────────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for DB


def _fetch_earnings_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the next earnings event dict for *symbol*, or None.

    Uses ``yfinance.Ticker.calendar`` which returns a dict with at least
    ``Earnings Date`` (list of datetime).  We take the nearest future date.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return None

        # calendar is a dict; key "Earnings Date" is a list of Timestamps
        earnings_dates = cal.get("Earnings Date") or cal.get("earningsDate") or []
        if not earnings_dates:
            return None

        # Pick the first future (or today's) date
        now = datetime.now()
        future_dates = []
        for d in earnings_dates:
            try:
                dt = d.to_pydatetime() if hasattr(d, "to_pydatetime") else datetime.fromisoformat(str(d))
                # Strip timezone info for naive comparison
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                if dt.date() >= now.date():
                    future_dates.append(dt)
            except Exception:
                continue

        if not future_dates:
            return None

        event_dt = min(future_dates)

        # Best-effort EPS / revenue estimates
        eps_est = None
        rev_est = None
        try:
            eps_est = cal.get("EPS Estimate") or cal.get("epsEstimate")
            rev_est = cal.get("Revenue Estimate") or cal.get("revenueEstimate")
            if eps_est is not None:
                try:
                    eps_est = float(eps_est)
                except (TypeError, ValueError):
                    eps_est = None
            if rev_est is not None:
                try:
                    rev_est = float(rev_est)
                except (TypeError, ValueError):
                    rev_est = None
        except Exception:
            pass

        # Determine BMO / AMC hint from time component
        event_time = None
        if event_dt.hour == 0 and event_dt.minute == 0:
            event_time = "TBD"
        elif event_dt.hour < 9:
            event_time = "BMO"
        elif event_dt.hour >= 16:
            event_time = "AMC"
        else:
            event_time = f"{event_dt.strftime('%H:%M')} ET"

        # Fetch short name
        short_name = symbol
        try:
            info = ticker.fast_info
            short_name = getattr(info, "shortName", None) or symbol
        except Exception:
            pass

        detail = {}
        if eps_est is not None:
            detail["eps_estimate"] = eps_est
        if rev_est is not None:
            detail["revenue_estimate"] = rev_est

        return {
            "event_type": "EARNINGS",
            "symbol": symbol,
            "title": f"{short_name} Earnings",
            "event_date": event_dt,
            "event_time": event_time,
            "source": "yfinance",
            "detail": detail,
        }
    except Exception as exc:
        logger.warning("Earnings fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_dividend_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the next ex-dividend event dict for *symbol*, or None."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # yfinance exposes the next ex-dividend date in .info
        ex_div_ts = info.get("exDividendDate")
        if not ex_div_ts:
            return None

        # exDividendDate is a Unix timestamp (int)
        try:
            ex_div_dt = datetime.utcfromtimestamp(int(ex_div_ts))
        except (TypeError, ValueError):
            return None

        if ex_div_dt.date() < datetime.now().date():
            return None  # past date, skip

        div_rate = info.get("dividendRate") or info.get("lastDividendValue")
        div_yield = info.get("dividendYield")
        short_name = info.get("shortName") or symbol

        detail: Dict[str, Any] = {}
        if div_rate is not None:
            try:
                detail["dividend_rate"] = float(div_rate)
            except (TypeError, ValueError):
                pass
        if div_yield is not None:
            try:
                detail["dividend_yield"] = float(div_yield)
            except (TypeError, ValueError):
                pass

        return {
            "event_type": "DIVIDEND",
            "symbol": symbol,
            "title": f"{short_name} Ex-Dividend",
            "event_date": ex_div_dt,
            "event_time": None,
            "source": "yfinance",
            "detail": detail,
        }
    except Exception as exc:
        logger.warning("Dividend fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_fomc_dates() -> List[Dict[str, Any]]:
    """Parse the Federal Reserve's public FOMC calendar page.

    Falls back to an empty list on any network or parse error so that the
    rest of the refresh continues unaffected.
    """
    events: List[Dict[str, Any]] = []
    try:
        import urllib.request
        import html.parser

        url = (
            "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "tws_robot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_bytes = resp.read()

        html_text = html_bytes.decode("utf-8", errors="replace")

        # The page lists meeting dates in spans like:
        #   <span class="fomc-meeting__date">April 30-May 1</span>
        # or sometimes just:
        #   <td class="fomc-meeting__date">January 28-29</td>
        # We extract year from <h4> headings and pair them with meeting rows.

        import re

        current_year = datetime.now().year

        # Find all occurrences of date strings adjacent to year headings.
        # Strategy: find all <h4>YEAR</h4> blocks, then find date spans within each block.
        year_sections = re.split(r'<h[34][^>]*>\s*(\d{4})\s*</h[34]>', html_text)

        # year_sections alternates: [pre-text, year, block, year, block, ...]
        for i in range(1, len(year_sections) - 1, 2):
            try:
                section_year = int(year_sections[i])
            except ValueError:
                continue

            if section_year < current_year or section_year > current_year + 1:
                continue

            block = year_sections[i + 1]

            # Extract date strings like "January 28-29", "March 18-19 *"
            date_matches = re.findall(
                r'<[^>]+class="[^"]*fomc-meeting__date[^"]*"[^>]*>\s*([^<]+?)\s*</[^>]+>',
                block,
            )
            if not date_matches:
                # Fallback: grab raw date text near "meeting" keywords
                date_matches = re.findall(
                    r'(?:January|February|March|April|May|June|July|August|'
                    r'September|October|November|December)\s+\d[\d\-\s,]*',
                    block,
                )

            for raw_date in date_matches:
                raw_date = raw_date.strip().strip('*').strip()
                if not raw_date:
                    continue

                # Normalise ranges: "April 30-May 1" → use the *last* day as
                # the decision-announcement day; "March 18-19" → use "March 19"
                end_date_str = _parse_fomc_date_range(raw_date, section_year)
                if end_date_str is None:
                    continue

                events.append({
                    "event_type": "FOMC",
                    "symbol": None,
                    "title": "FOMC Meeting",
                    "event_date": end_date_str,
                    "event_time": "14:00 ET",
                    "source": "federalreserve.gov",
                    "detail": {},
                })

    except Exception as exc:
        logger.warning("FOMC fetch failed: %s", exc)

    # De-duplicate by date (keep first occurrence per date)
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for ev in events:
        key = ev["event_date"].isoformat() if isinstance(ev["event_date"], datetime) else str(ev["event_date"])
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    logger.info("Fetched %d FOMC dates from federalreserve.gov", len(unique))
    return unique


_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_fomc_date_range(raw: str, year: int) -> Optional[datetime]:
    """Parse a raw FOMC date string like 'April 30-May 1' or 'March 18-19'.

    Returns a naive datetime for the *end* (announcement) day, or None.
    """
    import re

    raw = raw.strip().strip('*').strip()

    month_names = "|".join(_MONTH_MAP.keys())
    # Pattern 1: "Month D-Month D" e.g. "April 30-May 1"
    m = re.match(
        rf'({month_names})\s+(\d+)\s*[-–]\s*({month_names})\s+(\d+)',
        raw, re.IGNORECASE,
    )
    if m:
        month2 = _MONTH_MAP[m.group(3).lower()]
        day2 = int(m.group(4))
        try:
            return datetime(year, month2, day2)
        except ValueError:
            return None

    # Pattern 2: "Month D-D" e.g. "March 18-19"
    m = re.match(
        rf'({month_names})\s+(\d+)\s*[-–]\s*(\d+)',
        raw, re.IGNORECASE,
    )
    if m:
        month1 = _MONTH_MAP[m.group(1).lower()]
        day2 = int(m.group(3))
        try:
            return datetime(year, month1, day2)
        except ValueError:
            return None

    # Pattern 3: single date "Month D"
    m = re.match(rf'({month_names})\s+(\d+)', raw, re.IGNORECASE)
    if m:
        month1 = _MONTH_MAP[m.group(1).lower()]
        day1 = int(m.group(2))
        try:
            return datetime(year, month1, day1)
        except ValueError:
            return None

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Service class
# ──────────────────────────────────────────────────────────────────────────────

class MarketEventsService:
    """Manages market event data with DB persistence and TTL-based refreshing.

    Thread-safe: all public methods acquire ``_lock``.
    """

    def __init__(self, database=None):
        self._lock = threading.Lock()
        self._db = database
        self._refreshing = False

        # Track when each event_type was last fetched so we respect TTLs.
        # Symbol-level: {symbol: last_fetched_dt} for EARNINGS/DIVIDEND
        # Macro-level:  {"FOMC": last_fetched_dt}
        self._last_fetched: Dict[str, datetime] = {}

    # ------------------------------------------------------------------ #
    # DB access
    # ------------------------------------------------------------------ #

    def _get_db(self):
        if self._db is None:
            from data.database import get_database
            self._db = get_database()
            self._db.create_tables()
        return self._db

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_upcoming_events(
        self,
        days_ahead: int = _DEFAULT_DAYS_AHEAD,
        portfolio_symbols: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return events occurring within the next *days_ahead* calendar days.

        Events are returned chronologically.  Each dict has the shape::

            {
                "event_type": "EARNINGS",
                "symbol": "GOOG",
                "title": "Alphabet Earnings",
                "event_date": "2025-04-29T00:00:00",
                "event_time": "AMC",
                "source": "yfinance",
                "detail": {...},
                "is_portfolio_relevant": true,
                "days_away": 2,
            }
        """
        try:
            from data.models import MarketEvent
            db = self._get_db()
            now = datetime.now()
            cutoff = now + timedelta(days=days_ahead)

            portfolio_set: Set[str] = set(s.upper() for s in (portfolio_symbols or []))

            with db.session_scope() as session:
                rows = (
                    session.query(MarketEvent)
                    .filter(
                        MarketEvent.event_date >= now,
                        MarketEvent.event_date <= cutoff,
                    )
                    .order_by(MarketEvent.event_date.asc())
                    .all()
                )

                result = []
                for row in rows:
                    d = row.to_dict()
                    # Refresh portfolio-relevance based on caller-supplied symbols
                    if portfolio_set:
                        d["is_portfolio_relevant"] = (
                            row.symbol is not None
                            and row.symbol.upper() in portfolio_set
                        )
                    # Add human-readable days_away
                    try:
                        ev_dt = datetime.fromisoformat(d["event_date"]) if isinstance(d["event_date"], str) else row.event_date
                        d["days_away"] = max(0, (ev_dt.date() - now.date()).days)
                    except Exception:
                        d["days_away"] = None
                    result.append(d)

                return result
        except Exception as exc:
            logger.error("get_upcoming_events failed: %s", exc)
            return []

    def refresh(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        force: bool = False,
    ) -> None:
        """Fetch fresh event data from external sources and persist to DB.

        Respects TTLs unless *force=True*.
        """
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        try:
            symbols = list(portfolio_symbols or [])
            self._refresh_earnings(symbols, force=force)
            self._refresh_dividends(symbols, force=force)
            self._refresh_fomc(force=force)
        except Exception as exc:
            logger.error("MarketEventsService.refresh failed: %s", exc)
        finally:
            with self._lock:
                self._refreshing = False

    def refresh_async(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        force: bool = False,
    ) -> None:
        """Non-blocking version of :meth:`refresh`."""
        with self._lock:
            if self._refreshing:
                return
        thread = threading.Thread(
            target=self.refresh,
            kwargs={"portfolio_symbols": portfolio_symbols, "force": force},
            daemon=True,
        )
        thread.start()

    def is_stale(self, event_type: str = "FOMC") -> bool:
        """Return True if the given event_type has never been fetched or TTL has expired."""
        with self._lock:
            last = self._last_fetched.get(event_type)
        if last is None:
            return True
        ttl_hours = _FOMC_TTL_HOURS if event_type == "FOMC" else _EARNINGS_TTL_HOURS
        return (datetime.now() - last).total_seconds() > ttl_hours * 3600

    # ------------------------------------------------------------------ #
    # Private refresh helpers
    # ------------------------------------------------------------------ #

    def _ttl_ok(self, key: str, ttl_hours: int) -> bool:
        """Return True if we are still within the TTL for *key*."""
        last = self._last_fetched.get(key)
        if last is None:
            return False
        return (datetime.now() - last).total_seconds() < ttl_hours * 3600

    def _refresh_earnings(self, symbols: List[str], force: bool = False) -> None:
        if not symbols:
            return
        for symbol in symbols:
            key = f"EARNINGS:{symbol}"
            if not force and self._ttl_ok(key, _EARNINGS_TTL_HOURS):
                continue
            event = _fetch_earnings_for_symbol(symbol)
            if event:
                self._upsert_event(event)
            with self._lock:
                self._last_fetched[key] = datetime.now()

    def _refresh_dividends(self, symbols: List[str], force: bool = False) -> None:
        if not symbols:
            return
        for symbol in symbols:
            key = f"DIVIDEND:{symbol}"
            if not force and self._ttl_ok(key, _DIVIDEND_TTL_HOURS):
                continue
            event = _fetch_dividend_for_symbol(symbol)
            if event:
                self._upsert_event(event)
            with self._lock:
                self._last_fetched[key] = datetime.now()

    def _refresh_fomc(self, force: bool = False) -> None:
        key = "FOMC"
        if not force and self._ttl_ok(key, _FOMC_TTL_HOURS):
            return
        events = _fetch_fomc_dates()
        for event in events:
            self._upsert_event(event)
        with self._lock:
            self._last_fetched[key] = datetime.now()

    # ------------------------------------------------------------------ #
    # DB persistence
    # ------------------------------------------------------------------ #

    def _upsert_event(self, event: Dict[str, Any]) -> None:
        """Insert or update a MarketEvent row in the database.

        The unique constraint is on (event_type, symbol, event_date).
        We attempt an insert; on constraint violation we update the row.
        """
        try:
            from data.models import MarketEvent
            from sqlalchemy.exc import IntegrityError

            db = self._get_db()
            event_date = event["event_date"]
            if not isinstance(event_date, datetime):
                event_date = datetime.fromisoformat(str(event_date))

            detail_json = json.dumps(event.get("detail") or {})

            with db.session_scope() as session:
                existing = (
                    session.query(MarketEvent)
                    .filter_by(
                        event_type=event["event_type"],
                        symbol=event.get("symbol"),
                        event_date=event_date,
                    )
                    .first()
                )
                if existing:
                    existing.title = event["title"]
                    existing.event_time = event.get("event_time")
                    existing.source = event.get("source")
                    existing.detail_json = detail_json
                    existing.fetched_at = datetime.now()
                else:
                    row = MarketEvent(
                        event_type=event["event_type"],
                        symbol=event.get("symbol"),
                        title=event["title"],
                        event_date=event_date,
                        event_time=event.get("event_time"),
                        source=event.get("source"),
                        detail_json=detail_json,
                        is_portfolio_relevant=event.get("is_portfolio_relevant", False),
                        fetched_at=datetime.now(),
                    )
                    session.add(row)
        except Exception as exc:
            logger.warning("Failed to upsert market event %s: %s", event, exc)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────────

_instance: Optional[MarketEventsService] = None
_instance_lock = threading.Lock()


def get_market_events_service() -> MarketEventsService:
    """Return (or create) the module-level singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MarketEventsService()
    return _instance
