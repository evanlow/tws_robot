"""STI (Straits Times Index) Screener Service.

Scans STI constituents server-side and returns a compact screener payload
indicating which stocks are technically overbought or oversold based on
Bollinger Bands analysis.

This service mirrors the S&P 500 screener pattern but is tailored for the
Singapore market (SGX-listed stocks, ~30 constituents, yfinance ``.SI`` suffix
tickers).

Performance design
------------------
* Tickers are scanned **concurrently** using a bounded ``ThreadPoolExecutor``
  (``MAX_SCAN_WORKERS`` threads, default 5).  The STI universe (~30 stocks)
  is much smaller than the S&P 500, so fewer workers are needed.
* Results are **cached in-memory** with a configurable TTL
  (``CACHE_TTL_SECONDS``, default 15 minutes).
* Failures for individual tickers are isolated: the worker logs the error
  and returns an ``insufficient_data`` row so the rest of the scan continues.
* Quality scores use the same fundamental scoring logic as the S&P 500 screener.

Usage::

    from web.sti_screener_service import sti_screener_service

    result = sti_screener_service.get_screener_data(refresh=False)
"""

import csv
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from web.technical_analysis import (
    BOLLINGER_STATUS_LABELS,
    BOLLINGER_STATUS_RANK,
    calc_52w_percentile,
    compute_bollinger_bands,
    compute_oversold_momentum_confirmation,
)
from web.sp500_screener_service import (
    compute_quality_score,
    _empty_summary,
    _build_summary,
)

logger = logging.getLogger(__name__)

# Path to the static constituents file (relative to the repo root)
_CONSTITUENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "sti_constituents.csv"

# Cache TTL in seconds.  15 minutes matches the S&P 500 screener default.
_CACHE_TTL_SECONDS = 900

# Maximum number of concurrent yfinance fetch threads.
# 5 is sufficient for the ~30-stock STI universe.
_MAX_SCAN_WORKERS = 5

# Brief sleep between batches (seconds) to reduce pressure on yfinance.
_BATCH_SLEEP_SECONDS = 0.05


class STIScreenerService:
    """Thread-safe STI Bollinger Bands screener with in-memory cache.

    Handles SGX-listed stocks with yfinance ``.SI`` suffix symbols.  The
    ``display_symbol`` field in each row contains the short SGX code (e.g.
    ``D05``) suitable for display, while ``symbol`` contains the full
    yfinance-compatible ticker (e.g. ``D05.SI``) used for fetching and for
    the analysis drill-down URL.
    """

    def __init__(self) -> None:
        self._lock = threading.Condition(threading.Lock())
        self._scanning: bool = False
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_screener_data(self, refresh: bool = False) -> Dict[str, Any]:
        """Return the screener payload, using cache if it is still fresh.

        Parameters
        ----------
        refresh:
            When ``True`` the cache is bypassed and a fresh scan is performed.

        Returns
        -------
        dict
            Keys: ``as_of``, ``source``, ``count``, ``summary``, ``rows``.
        """
        with self._lock:
            while self._scanning:
                self._lock.wait()

            cache_age = time.time() - self._cache_ts
            if not refresh and self._cache is not None and cache_age < _CACHE_TTL_SECONDS:
                logger.debug("Returning cached STI screener data (age=%.0fs)", cache_age)
                return self._cache

            self._scanning = True

        result: Optional[Dict[str, Any]] = None
        try:
            result = self._scan()
            return result
        finally:
            with self._lock:
                if result is not None:
                    self._cache = result
                    self._cache_ts = time.time()
                self._scanning = False
                self._lock.notify_all()

    def invalidate_cache(self) -> None:
        """Force the next call to ``get_screener_data`` to re-scan."""
        with self._lock:
            self._cache = None
            self._cache_ts = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_constituents(self) -> List[Dict[str, str]]:
        """Load STI constituents from the CSV file."""
        if not _CONSTITUENTS_PATH.exists():
            logger.error("STI constituents file not found: %s", _CONSTITUENTS_PATH)
            return []
        rows: List[Dict[str, str]] = []
        with open(_CONSTITUENTS_PATH, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = row.get("symbol", "").strip()
                if symbol:
                    rows.append({
                        "symbol": symbol,
                        "display_symbol": row.get("display_symbol", symbol.replace(".SI", "")).strip(),
                        "security": row.get("security", symbol).strip(),
                        "sector": row.get("sector", "").strip(),
                        "sub_industry": row.get("sub_industry", "").strip(),
                    })
        return rows

    def _scan_ticker(self, constituent: Dict[str, str]) -> Dict[str, Any]:
        """Fetch price and fundamental data for a single SGX ticker.

        Returns a screener row dict.  If data cannot be retrieved or is
        insufficient, ``bollinger_status`` is set to ``"insufficient_data"``.
        Always returns a valid dict — never raises.
        """
        from data.fundamentals import fetch_price_history, get_fundamentals

        symbol = constituent["symbol"]
        base_row = _sti_insufficient_data_row(constituent)

        try:
            raw_bars = fetch_price_history(symbol, period="1y", interval="1d")
        except Exception as exc:
            logger.warning("Price history fetch failed for %s: %s", symbol, exc)
            return base_row

        # Filter bars with non-finite OHLC values
        bars = [
            b for b in raw_bars
            if all(
                isinstance(b.get(k), (int, float)) and math.isfinite(b[k])
                for k in ("open", "high", "low", "close")
                if b.get(k) is not None
            )
        ]

        if not bars:
            return base_row

        current_price_raw = bars[-1].get("close")
        if current_price_raw is None or not math.isfinite(float(current_price_raw)):
            return base_row

        current_price = float(current_price_raw)

        # 52-week range from bars
        closes = [b["close"] for b in bars if b.get("close") is not None]
        low_52w = min(closes) if closes else None
        high_52w = max(closes) if closes else None
        position_percentile = calc_52w_percentile(current_price, low_52w, high_52w)

        # Bollinger Bands
        bb = compute_bollinger_bands(bars, current_price)

        # Momentum confirmation — only populated for oversold / near-oversold
        momentum = compute_oversold_momentum_confirmation(bars, bb["status"])

        # Fundamentals / quality score — failures are non-fatal
        try:
            fundamentals = get_fundamentals(symbol)
        except Exception as exc:
            logger.warning("Fundamentals fetch failed for %s: %s", symbol, exc)
            fundamentals = {}
        quality = compute_quality_score(fundamentals)

        # Dividend fields — missing values stay None
        annual_dividend = fundamentals.get("dividend_rate")
        dividend_yield = fundamentals.get("dividend_yield")

        import datetime
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        row = base_row.copy()
        row["current_price"] = round(current_price, 3)
        row["range_52w_position_percentile"] = position_percentile
        row["bollinger_percent_b"] = bb.get("percent_b")
        row["bollinger_status"] = bb["status"]
        row["status_label"] = BOLLINGER_STATUS_LABELS.get(bb["status"], bb["status"])
        row["status_rank"] = BOLLINGER_STATUS_RANK.get(bb["status"], 5)
        row["quality_score"] = quality["quality_score"]
        row["quality_label"] = quality["quality_label"]
        row["quality_reasons"] = quality["quality_reasons"]
        row["quality_warnings"] = quality["quality_warnings"]
        row["annual_dividend"] = annual_dividend
        row["dividend_yield"] = dividend_yield
        row["momentum_confirmation"] = momentum["momentum_confirmation"]
        row["momentum_label"] = momentum["momentum_label"]
        row["momentum_reasons"] = momentum["momentum_reasons"]
        row["last_updated"] = now_iso
        return row

    def _scan(self) -> Dict[str, Any]:
        """Run a full scan of all constituents concurrently and build the response payload."""
        import datetime

        constituents = self._load_constituents()
        if not constituents:
            return {
                "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": str(_CONSTITUENTS_PATH),
                "count": 0,
                "summary": _empty_summary(),
                "rows": [],
                "error": "STI constituent list could not be loaded.",
            }

        logger.info(
            "Starting STI screener scan for %d tickers (workers=%d)…",
            len(constituents),
            _MAX_SCAN_WORKERS,
        )
        t0 = time.monotonic()

        rows: List[Dict[str, Any]] = [None] * len(constituents)  # preserve slot order

        with ThreadPoolExecutor(max_workers=_MAX_SCAN_WORKERS) as executor:
            future_to_index = {}
            for idx, constituent in enumerate(constituents):
                future = executor.submit(self._scan_ticker, constituent)
                future_to_index[future] = idx
                # Brief sleep every batch to reduce yfinance pressure
                if idx > 0 and idx % _MAX_SCAN_WORKERS == 0:
                    time.sleep(_BATCH_SLEEP_SECONDS)

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    rows[idx] = future.result()
                except Exception as exc:
                    symbol = constituents[idx]["symbol"]
                    logger.error("Unexpected error scanning %s: %s", symbol, exc)
                    rows[idx] = _sti_insufficient_data_row(constituents[idx])

        elapsed = time.monotonic() - t0
        logger.info("STI screener scan completed in %.1fs", elapsed)

        # Sort: status_rank ascending (oversold first), then sector, then symbol
        rows.sort(key=lambda r: (r["status_rank"], r["sector"], r["symbol"]))

        summary = _build_summary(rows)
        as_of = datetime.datetime.now(datetime.timezone.utc).isoformat()
        logger.info("STI screener scan complete: %s", summary)

        return {
            "as_of": as_of,
            "source": _CONSTITUENTS_PATH.name,
            "count": len(rows),
            "summary": summary,
            "rows": rows,
            "scan_duration_seconds": round(elapsed, 1),
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _sti_insufficient_data_row(constituent: Dict[str, str]) -> Dict[str, Any]:
    """Build a minimal row for an STI ticker that could not be scanned."""
    return {
        "symbol": constituent["symbol"],
        "display_symbol": constituent.get("display_symbol", constituent["symbol"].replace(".SI", "")),
        "company": constituent.get("security", constituent["symbol"]),
        "sector": constituent.get("sector", ""),
        "current_price": None,
        "range_52w_position_percentile": None,
        "bollinger_percent_b": None,
        "bollinger_status": "insufficient_data",
        "status_label": BOLLINGER_STATUS_LABELS["insufficient_data"],
        "status_rank": BOLLINGER_STATUS_RANK["insufficient_data"],
        "quality_score": None,
        "quality_label": "Insufficient Data",
        "quality_reasons": [],
        "quality_warnings": [],
        "annual_dividend": None,
        "dividend_yield": None,
        "momentum_confirmation": None,
        "momentum_label": None,
        "momentum_reasons": [],
        "last_updated": None,
    }


# Module-level singleton used by the route layer.
sti_screener_service = STIScreenerService()
