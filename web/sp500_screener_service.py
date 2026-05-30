"""S&P 500 Screener Service.

Scans S&P 500 constituents server-side and returns a compact screener
payload indicating which stocks are technically overbought or oversold
based on Bollinger Bands analysis.

Performance design
------------------
* Tickers are scanned **concurrently** using a bounded ``ThreadPoolExecutor``
  (``MAX_SCAN_WORKERS`` threads, default 10).  This gives roughly a 10x
  wall-clock speed improvement over sequential scanning.
* A short inter-batch sleep (``BATCH_SLEEP_SECONDS``) is inserted between
  worker submissions to avoid hammering yfinance too aggressively.
* Results are **cached in-memory** with a configurable TTL
  (``CACHE_TTL_SECONDS``, default 15 minutes).  Repeat page loads within
  the TTL are served instantly with no network I/O.
* Failures for individual tickers are isolated: the worker logs the error
  and returns an ``insufficient_data`` row so the rest of the scan continues.
* Quality scores use fundamental data (revenue growth, margins, ROE, debt,
  current ratio) fetched alongside price data.  Missing fundamentals degrade
  gracefully to ``"Insufficient Data"`` rather than breaking the page.

Usage::

    from web.sp500_screener_service import sp500_screener_service

    result = sp500_screener_service.get_screener_data(refresh=False)
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

logger = logging.getLogger(__name__)

# Path to the static constituents file (relative to the repo root)
_CONSTITUENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_constituents.csv"

# Cache TTL in seconds.  15 minutes is long enough to serve repeated page
# loads while still being reasonably fresh for a screener.
_CACHE_TTL_SECONDS = 900

# Maximum number of concurrent yfinance fetch threads.
# Higher values speed up the scan but risk hitting yfinance rate limits.
# 10 is a conservative default that works well in practice.
_MAX_SCAN_WORKERS = 10

# Brief sleep between batches (seconds) to reduce pressure on yfinance.
_BATCH_SLEEP_SECONDS = 0.05

# Quality score thresholds and limits.
# Debt-to-equity above this level is considered a quality fail.
_MAX_DEBT_TO_EQUITY = 150
# Current ratio below this level is considered a quality fail.
_MIN_CURRENT_RATIO = 1.0
# Minimum number of available checks required before assigning a quality label.
# Fewer available checks produce "Insufficient Data".
_MIN_QUALITY_CHECKS = 3
# Quality score (0-100) boundaries for label assignment.
_STRONG_QUALITY_THRESHOLD = 75
_MODERATE_QUALITY_THRESHOLD = 50


class SP500ScreenerService:
    """Thread-safe S&P 500 Bollinger Bands screener with in-memory cache."""

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
            # Wait for any in-flight scan started by another thread to complete
            # before deciding whether the cache is warm or a new scan is needed.
            # This prevents concurrent cold-cache requests from each launching
            # their own full ThreadPoolExecutor scan.
            while self._scanning:
                self._lock.wait()

            cache_age = time.time() - self._cache_ts
            if not refresh and self._cache is not None and cache_age < _CACHE_TTL_SECONDS:
                logger.debug("Returning cached screener data (age=%.0fs)", cache_age)
                return self._cache

            # Claim the scan slot before releasing the lock so no other thread
            # can start a second scan while this one is running.
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
        """Load S&P 500 constituents from the CSV file."""
        if not _CONSTITUENTS_PATH.exists():
            logger.error("Constituents file not found: %s", _CONSTITUENTS_PATH)
            return []
        rows: List[Dict[str, str]] = []
        with open(_CONSTITUENTS_PATH, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = row.get("symbol", "").strip()
                if symbol:
                    rows.append({
                        "symbol": symbol,
                        "security": row.get("security", symbol).strip(),
                        "sector": row.get("sector", "").strip(),
                        "sub_industry": row.get("sub_industry", "").strip(),
                    })
        return rows

    def _scan_ticker(self, constituent: Dict[str, str]) -> Dict[str, Any]:
        """Fetch price and fundamental data for a single ticker.

        Returns a screener row dict.  If data cannot be retrieved or is
        insufficient, ``bollinger_status`` is set to ``"insufficient_data"``.
        Always returns a valid dict — never raises.
        """
        from data.fundamentals import fetch_price_history, get_fundamentals

        symbol = constituent["symbol"]
        base_row = _insufficient_data_row(constituent)

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
        annual_dividend = fundamentals.get("dividend_rate") or None
        dividend_yield = fundamentals.get("dividend_yield") or None

        import datetime
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        row = base_row.copy()
        row["current_price"] = round(current_price, 2)
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
                "error": "Constituent list could not be loaded.",
            }

        logger.info(
            "Starting S&P 500 screener scan for %d tickers (workers=%d)…",
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
                    # Should not happen (scan_ticker catches all), but guard anyway
                    symbol = constituents[idx]["symbol"]
                    logger.error("Unexpected error scanning %s: %s", symbol, exc)
                    rows[idx] = _insufficient_data_row(constituents[idx])

        elapsed = time.monotonic() - t0
        logger.info("S&P 500 screener scan completed in %.1fs", elapsed)

        # Sort: status_rank ascending (oversold first), then sector, then symbol
        rows.sort(key=lambda r: (r["status_rank"], r["sector"], r["symbol"]))

        summary = _build_summary(rows)
        as_of = datetime.datetime.now(datetime.timezone.utc).isoformat()
        logger.info("S&P 500 screener scan complete: %s", summary)

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


def _insufficient_data_row(constituent: Dict[str, str]) -> Dict[str, Any]:
    """Build a minimal row for a ticker that could not be scanned."""
    return {
        "symbol": constituent["symbol"],
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


def _empty_summary() -> Dict[str, int]:
    return {
        "overbought": 0,
        "near_overbought": 0,
        "neutral": 0,
        "near_oversold": 0,
        "oversold": 0,
        "insufficient_data": 0,
    }


def _build_summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = _empty_summary()
    status_to_key = {
        "above_upper_band": "overbought",
        "near_upper_band": "near_overbought",
        "within_bands": "neutral",
        "near_lower_band": "near_oversold",
        "below_lower_band": "oversold",
        "insufficient_data": "insufficient_data",
    }
    for row in rows:
        key = status_to_key.get(row["bollinger_status"], "insufficient_data")
        summary[key] += 1
    return summary


def compute_quality_score(fundamentals: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a simplified fundamental quality indicator.

    Uses a points-based model that tolerates missing data.  Each available
    metric contributes one pass/fail vote; the score is the percentage of
    votes that passed.  If fewer than 3 checks have available (non-``None``)
    fundamentals, the label is ``"Insufficient Data"`` regardless of the
    score.

    Parameters
    ----------
    fundamentals:
        Dict as returned by ``get_fundamentals(...)`` in ``data.fundamentals``.
        May be empty or contain an ``"error"`` key; both are handled
        gracefully.

    Returns
    -------
    dict
        Keys: ``quality_score`` (int | None), ``quality_label`` (str),
        ``quality_reasons`` (list[str]), ``quality_warnings`` (list[str]).
    """
    _insufficient: Dict[str, Any] = {
        "quality_score": None,
        "quality_label": "Insufficient Data",
        "quality_reasons": [],
        "quality_warnings": [],
    }

    if not fundamentals or "error" in fundamentals:
        result = dict(_insufficient)
        result["quality_warnings"] = ["Fundamental data unavailable"]
        return result

    checks: List[bool] = []
    reasons: List[str] = []
    warnings: List[str] = []

    def _check(value: Any, condition: bool, pass_reason: str, warn_label: str) -> None:
        if value is None:
            warnings.append(f"{warn_label} unavailable")
        else:
            checks.append(condition)
            if condition:
                reasons.append(pass_reason)

    revenue_growth = fundamentals.get("revenue_growth")
    _check(revenue_growth, (revenue_growth or 0) > 0, "Positive revenue growth", "Revenue growth")

    earnings_growth = fundamentals.get("earnings_growth")
    _check(earnings_growth, (earnings_growth or 0) > 0, "Positive earnings growth", "Earnings growth")

    profit_margin = fundamentals.get("profit_margin")
    _check(profit_margin, (profit_margin or 0) > 0, "Positive profit margin", "Profit margin")

    operating_margin = fundamentals.get("operating_margin")
    _check(operating_margin, (operating_margin or 0) > 0, "Positive operating margin", "Operating margin")

    roe = fundamentals.get("roe")
    _check(roe, (roe or 0) > 0, "Positive return on equity", "Return on equity")

    debt_to_equity = fundamentals.get("debt_to_equity")
    _check(
        debt_to_equity,
        (debt_to_equity or 0) < _MAX_DEBT_TO_EQUITY,
        "Debt-to-equity within threshold",
        "Debt-to-equity",
    )

    current_ratio = fundamentals.get("current_ratio")
    _check(
        current_ratio,
        (current_ratio or 0) >= _MIN_CURRENT_RATIO,
        "Current ratio above 1",
        "Current ratio",
    )

    available = len(checks)
    if available < _MIN_QUALITY_CHECKS:
        result = dict(_insufficient)
        result["quality_reasons"] = reasons
        result["quality_warnings"] = warnings
        return result

    passed = sum(checks)
    quality_score = round(passed / available * 100)

    if quality_score >= _STRONG_QUALITY_THRESHOLD:
        quality_label = "Strong"
    elif quality_score >= _MODERATE_QUALITY_THRESHOLD:
        quality_label = "Moderate"
    else:
        quality_label = "Weak"

    return {
        "quality_score": quality_score,
        "quality_label": quality_label,
        "quality_reasons": reasons,
        "quality_warnings": warnings,
    }


# Module-level singleton used by the route layer.
sp500_screener_service = SP500ScreenerService()
