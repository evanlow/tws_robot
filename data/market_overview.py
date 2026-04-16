"""Global Market Overview Service.

Fetches index-level data from Yahoo Finance, persists snapshots in
SQLite for offline viewing and sparkline history, and serves cached
results to the dashboard.

Usage::

    from data.market_overview import MarketOverviewService

    svc = MarketOverviewService()
    overview = svc.get_overview()       # latest snapshots (from cache/DB)
    svc.refresh()                       # fetch fresh data from yfinance
"""

import logging
import threading
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Index definitions: symbol → (display name, region)
# ──────────────────────────────────────────────────────────────────────

INDEX_DEFINITIONS: Dict[str, Dict[str, str]] = {
    # US
    "^GSPC":     {"name": "S&P 500",          "region": "US"},
    "^DJI":      {"name": "Dow Jones",         "region": "US"},
    "^IXIC":     {"name": "Nasdaq",            "region": "US"},
    "^RUT":      {"name": "Russell 2000",      "region": "US"},
    "^VIX":      {"name": "VIX",               "region": "US"},
    # Europe
    "^FTSE":     {"name": "FTSE 100",          "region": "Europe"},
    "^GDAXI":    {"name": "DAX",               "region": "Europe"},
    "^STOXX50E": {"name": "Euro Stoxx 50",     "region": "Europe"},
    "^FCHI":     {"name": "CAC 40",            "region": "Europe"},
    # Asia
    "^N225":     {"name": "Nikkei 225",        "region": "Asia"},
    "^HSI":      {"name": "Hang Seng",         "region": "Asia"},
    "000001.SS": {"name": "Shanghai Composite", "region": "Asia"},
    "^KS11":     {"name": "KOSPI",             "region": "Asia"},
    "^AXJO":     {"name": "ASX 200",           "region": "Asia"},
}

# Cache TTL — 5 minutes
_CACHE_TTL_SECONDS = 300


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _market_status() -> Dict[str, str]:
    """Return approximate open/closed status for each region.

    This is a heuristic based on broad trading hours in UTC.
    It does not account for holidays.
    """
    now = _utcnow()
    weekday = now.weekday()  # 0=Mon … 6=Sun

    status: Dict[str, str] = {}

    # US: NYSE 14:30–21:00 UTC (Mon-Fri)
    if (
        0 <= weekday <= 4
        and now.hour < 21
        and (now.hour > 14 or (now.hour == 14 and now.minute >= 30))
    ):
        status["US"] = "open"
    else:
        status["US"] = "closed"

    # Europe: LSE/Xetra roughly 08:00–16:30 UTC (Mon-Fri)
    if 0 <= weekday <= 4 and 8 <= now.hour < 17:
        status["Europe"] = "open"
    else:
        status["Europe"] = "closed"

    # Asia: TSE 00:00–06:00 UTC, HSI 01:30–08:00 UTC (Mon-Fri, rough)
    if 0 <= weekday <= 4 and 0 <= now.hour < 8:
        status["Asia"] = "open"
    else:
        status["Asia"] = "closed"

    return status


def _fetch_from_yfinance() -> List[Dict[str, Any]]:
    """Download latest quotes for all tracked indices via yfinance.

    Returns a list of snapshot dicts ready for DB insertion.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance is not installed — cannot fetch market data")
        return []

    symbols = list(INDEX_DEFINITIONS.keys())
    snapshots: List[Dict[str, Any]] = []
    now = datetime.now()

    try:
        tickers = yf.Tickers(" ".join(symbols))
    except Exception as exc:
        logger.error("yfinance Tickers() call failed: %s", exc)
        return []

    for symbol in symbols:
        defn = INDEX_DEFINITIONS[symbol]
        try:
            ticker = tickers.tickers.get(symbol)
            if ticker is None:
                logger.warning("Ticker %s not returned by yfinance", symbol)
                continue

            info = ticker.fast_info
            price = float(getattr(info, "last_price", 0) or 0)
            prev_close = float(getattr(info, "previous_close", 0) or 0)
            day_high = float(getattr(info, "day_high", 0) or 0)
            day_low = float(getattr(info, "day_low", 0) or 0)

            if price == 0 and prev_close == 0:
                # Fallback: try quote_type / regularMarketPrice
                try:
                    qinfo = ticker.info
                    price = float(qinfo.get("regularMarketPrice", 0) or 0)
                    prev_close = float(qinfo.get("regularMarketPreviousClose", 0) or 0)
                    day_high = float(qinfo.get("regularMarketDayHigh", 0) or 0)
                    day_low = float(qinfo.get("regularMarketDayLow", 0) or 0)
                except Exception:
                    pass

            if price == 0:
                logger.warning("No price data for %s — skipping", symbol)
                continue

            change = (price - prev_close) if prev_close else None
            change_pct = ((change / prev_close) * 100) if prev_close and change is not None else None

            snapshots.append({
                "symbol": symbol,
                "name": defn["name"],
                "region": defn["region"],
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "day_high": day_high if day_high else None,
                "day_low": day_low if day_low else None,
                "prev_close": prev_close if prev_close else None,
                "volume": None,
                "timestamp": now,
                "market_date": now.date(),
            })
        except Exception as exc:
            logger.warning("Failed to process %s: %s", symbol, exc)

    logger.info("Fetched %d / %d market snapshots from yfinance", len(snapshots), len(symbols))
    return snapshots


def _fetch_sparkline_from_yfinance(days: int = 5) -> Dict[str, List[float]]:
    """Fetch recent daily close prices for sparkline rendering.

    Returns {symbol: [close_0, close_1, …, close_n]} ordered oldest → newest.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    symbols = list(INDEX_DEFINITIONS.keys())
    sparklines: Dict[str, List[float]] = {}

    try:
        # Download historical data for all symbols at once
        data = yf.download(
            " ".join(symbols),
            period=f"{days + 3}d",  # extra buffer for weekends
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )

        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    closes = data["Close"].dropna().tolist()
                else:
                    closes = data[symbol]["Close"].dropna().tolist()
                sparklines[symbol] = closes[-days:] if len(closes) > days else closes
            except Exception:
                sparklines[symbol] = []
    except Exception as exc:
        logger.warning("Sparkline download failed: %s", exc)

    return sparklines


class MarketOverviewService:
    """Manages market overview data with DB persistence and in-memory caching.

    Thread-safe: all public methods acquire ``_lock``.
    """

    def __init__(self, database=None):
        self._lock = threading.Lock()
        self._db = database
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._refreshing = False

    def _get_db(self):
        """Lazy DB access — only import when actually needed."""
        if self._db is None:
            from data.database import get_database
            self._db = get_database()
            self._db.create_tables()
        return self._db

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_overview(self) -> Dict[str, Any]:
        """Return the latest market overview.

        1. Serve from in-memory cache if fresh (< 5 min).
        2. Otherwise fall back to the most recent DB snapshots.
        3. If DB is also empty, return a stub with empty lists.
        """
        with self._lock:
            if self._cache and self._cache_time:
                age = (datetime.now() - self._cache_time).total_seconds()
                if age < _CACHE_TTL_SECONDS:
                    return self._cache

        # Try DB
        overview = self._load_from_db()
        if overview and overview.get("snapshots"):
            with self._lock:
                self._cache = overview
                self._cache_time = datetime.now()
            return overview

        return self._empty_overview()

    def refresh(self) -> Dict[str, Any]:
        """Fetch fresh data from yfinance, persist to DB, and update cache.

        Returns the new overview dict.
        """
        with self._lock:
            if self._refreshing:
                return self._cache or self._empty_overview()
            self._refreshing = True

        try:
            snapshots = _fetch_from_yfinance()
            sparklines = _fetch_sparkline_from_yfinance()

            if not snapshots:
                # Fetch returned nothing (network/API issue).  Keep the
                # existing cache / DB-backed overview instead of
                # overwriting with empty data.
                logger.warning("yfinance returned no snapshots — keeping existing cache")
                return self._cache or self._load_from_db() or self._empty_overview()

            self._persist_snapshots(snapshots)

            overview = self._build_overview(snapshots, sparklines)

            with self._lock:
                self._cache = overview
                self._cache_time = datetime.now()

            return overview
        except Exception as exc:
            logger.error("Market refresh failed: %s", exc)
            return self._cache or self._empty_overview()
        finally:
            with self._lock:
                self._refreshing = False

    def refresh_async(self) -> None:
        """Trigger a background refresh (non-blocking).

        Guarded: if a refresh is already in progress the call is a no-op,
        preventing thread churn under repeated requests.
        """
        with self._lock:
            if self._refreshing:
                return
        thread = threading.Thread(target=self.refresh, daemon=True)
        thread.start()

    def is_stale(self) -> bool:
        """Return True if cache is empty or older than the TTL."""
        with self._lock:
            if not self._cache or not self._cache_time:
                return True
            return (datetime.now() - self._cache_time).total_seconds() >= _CACHE_TTL_SECONDS

    # ------------------------------------------------------------------ #
    # DB operations
    # ------------------------------------------------------------------ #

    def _persist_snapshots(self, snapshots: List[Dict[str, Any]]) -> None:
        """Append snapshot rows to the database."""
        try:
            from data.models import MarketSnapshot
            db = self._get_db()
            with db.session_scope() as session:
                for s in snapshots:
                    row = MarketSnapshot(
                        symbol=s["symbol"],
                        name=s["name"],
                        region=s["region"],
                        price=s["price"],
                        change=s.get("change"),
                        change_pct=s.get("change_pct"),
                        day_high=s.get("day_high"),
                        day_low=s.get("day_low"),
                        prev_close=s.get("prev_close"),
                        volume=s.get("volume"),
                        timestamp=s["timestamp"],
                        market_date=s.get("market_date"),
                    )
                    session.add(row)
            logger.info("Persisted %d market snapshots to DB", len(snapshots))
        except Exception as exc:
            logger.error("Failed to persist market snapshots: %s", exc)

    def _load_from_db(self) -> Optional[Dict[str, Any]]:
        """Load the most recent snapshot per symbol from the database."""
        try:
            from data.models import MarketSnapshot
            from sqlalchemy import func
            db = self._get_db()

            with db.session_scope() as session:
                # Subquery: max timestamp per symbol
                subq = (
                    session.query(
                        MarketSnapshot.symbol,
                        func.max(MarketSnapshot.timestamp).label("max_ts"),
                    )
                    .group_by(MarketSnapshot.symbol)
                    .subquery()
                )
                rows = (
                    session.query(MarketSnapshot)
                    .join(
                        subq,
                        (MarketSnapshot.symbol == subq.c.symbol)
                        & (MarketSnapshot.timestamp == subq.c.max_ts),
                    )
                    .all()
                )
                if not rows:
                    return None

                snapshots = [r.to_dict() for r in rows]

                # Load sparkline data from recent history
                sparklines = self._load_sparklines_from_db(session)

            return self._build_overview(
                snapshots,
                sparklines,
            )
        except Exception as exc:
            logger.error("Failed to load market snapshots from DB: %s", exc)
            return None

    def _load_sparklines_from_db(
        self, session, days: int = 5
    ) -> Dict[str, List[float]]:
        """Load recent daily close prices from persisted snapshots."""
        from data.models import MarketSnapshot
        from sqlalchemy import func

        cutoff = datetime.now() - timedelta(days=days + 3)
        sparklines: Dict[str, List[float]] = {}

        try:
            # For each symbol, get distinct (market_date, price) ordered by date
            symbols = list(INDEX_DEFINITIONS.keys())
            for sym in symbols:
                # Order DESC to grab the most recent N trading days,
                # then reverse in Python to get oldest→newest for the chart.
                rows = (
                    session.query(
                        MarketSnapshot.market_date,
                        func.avg(MarketSnapshot.price).label("avg_price"),
                    )
                    .filter(
                        MarketSnapshot.symbol == sym,
                        MarketSnapshot.timestamp >= cutoff,
                        MarketSnapshot.market_date.isnot(None),
                    )
                    .group_by(MarketSnapshot.market_date)
                    .order_by(MarketSnapshot.market_date.desc())
                    .limit(days)
                    .all()
                )
                sparklines[sym] = [float(r.avg_price) for r in reversed(rows)]
        except Exception as exc:
            logger.warning("Sparkline DB load failed: %s", exc)

        return sparklines

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_overview(
        snapshots: List[Dict[str, Any]],
        sparklines: Optional[Dict[str, List[float]]] = None,
    ) -> Dict[str, Any]:
        """Organise flat snapshot list into a region-grouped overview."""
        if sparklines is None:
            sparklines = {}

        by_region: Dict[str, List[Dict[str, Any]]] = {
            "US": [],
            "Europe": [],
            "Asia": [],
        }

        for s in snapshots:
            region = s.get("region", "US")
            entry = dict(s)
            entry["sparkline"] = sparklines.get(s["symbol"], [])
            by_region.setdefault(region, []).append(entry)

        status = _market_status()

        # Derive last_updated from the newest snapshot timestamp rather
        # than datetime.now() so that DB-loaded data does not appear fresh.
        last_updated = None
        for s in snapshots:
            ts = s.get("timestamp")
            if ts is None:
                continue
            ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
            if last_updated is None or ts_str > last_updated:
                last_updated = ts_str

        return {
            "regions": [
                {"name": "US", "flag": "🇺🇸", "label": "US Markets",
                 "status": status.get("US", "closed"), "indices": by_region.get("US", [])},
                {"name": "Europe", "flag": "🇪🇺", "label": "European Markets",
                 "status": status.get("Europe", "closed"), "indices": by_region.get("Europe", [])},
                {"name": "Asia", "flag": "🌏", "label": "Asian Markets",
                 "status": status.get("Asia", "closed"), "indices": by_region.get("Asia", [])},
            ],
            "market_status": status,
            "last_updated": last_updated,
            "snapshots": snapshots,
        }

    @staticmethod
    def _empty_overview() -> Dict[str, Any]:
        status = _market_status()
        return {
            "regions": [
                {"name": "US", "flag": "🇺🇸", "label": "US Markets",
                 "status": status.get("US", "closed"), "indices": []},
                {"name": "Europe", "flag": "🇪🇺", "label": "European Markets",
                 "status": status.get("Europe", "closed"), "indices": []},
                {"name": "Asia", "flag": "🌏", "label": "Asian Markets",
                 "status": status.get("Asia", "closed"), "indices": []},
            ],
            "market_status": status,
            "last_updated": None,
            "snapshots": [],
        }


# ──────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────

_instance: Optional[MarketOverviewService] = None
_instance_lock = threading.Lock()


def get_market_overview_service() -> MarketOverviewService:
    """Return (or create) the module-level singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MarketOverviewService()
    return _instance
