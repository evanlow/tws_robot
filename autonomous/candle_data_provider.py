"""Runtime candle data provider for ORB recommend-only / paper-autonomous mode.

Produces closed 1-minute OHLCV candles for a configured symbol whitelist,
aggregates them into closed 5-minute and 15-minute candles, normalizes session
boundaries to New York market time (preserving original timestamps), and exposes
per-symbol provider health for the future ORB dashboard/API.

Safety posture (Prime Directive):
- Pure data layer: no broker/TWS/order imports. Never places orders.
- A forming candle is never returned as a closed confirmation candle.
- Missing, duplicate, out-of-order, stale, and forming-only data are surfaced as
  degraded status rather than silently accepted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Protocol

from autonomous.candle_aggregator import (
    CandleDataStatus,
    assess_one_minute_quality,
    closed_aggregates,
    normalize_to_ny,
)
from autonomous.opening_range import Candle

SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m")
_AGG_FACTOR = {"1m": 1, "5m": 5, "15m": 15}
DEFAULT_STALE_SECONDS = 120.0


class CandleDataProvider(Protocol):
    """Runtime candle provider interface consumed by ORB and dashboards."""

    def subscribe_candles(self, symbols: Iterable[str], base_timeframe: str = "1m") -> None: ...

    def latest_closed_candle(self, symbol: str, timeframe: str) -> Optional[Candle]: ...

    def recent_closed_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]: ...

    def status(self) -> dict: ...


class RuntimeCandleProvider:
    """In-memory closed-candle provider with health/aggregation, broker-free.

    Closed 1-minute candles are fed in via :meth:`ingest` (live runtime) or
    :meth:`backfill` (session recovery). Forming candles may be supplied for
    diagnostics but are never returned as closed or aggregated.
    """

    def __init__(self, *, stale_seconds: float = DEFAULT_STALE_SECONDS, now_fn=None) -> None:
        self._stale_seconds = float(stale_seconds)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._symbols: List[str] = []
        self._base_timeframe = "1m"
        self._closed: Dict[str, List[Candle]] = {}
        self._forming: Dict[str, Optional[Candle]] = {}

    def subscribe_candles(self, symbols: Iterable[str], base_timeframe: str = "1m") -> None:
        if base_timeframe != "1m":
            raise ValueError("RuntimeCandleProvider base timeframe must be '1m'")
        for sym in symbols:
            if sym not in self._symbols:
                self._symbols.append(sym)
                self._closed.setdefault(sym, [])
                self._forming.setdefault(sym, None)
        self._base_timeframe = base_timeframe

    def ingest(self, candle: Candle) -> None:
        """Record one 1m candle. Closed bars are stored; forming bars buffered."""
        sym = candle.symbol
        if sym not in self._symbols:
            self.subscribe_candles([sym])
        if not candle.is_closed:
            self._forming[sym] = candle
            return
        self._forming[sym] = None
        self._closed[sym].append(candle)

    def backfill(self, candles: Iterable[Candle]) -> None:
        """Load closed 1m candles for current-session recovery after restart."""
        for c in candles:
            if c.is_closed:
                self.ingest(c)

    def latest_closed_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        bars = self._closed_timeframe(symbol, timeframe)
        return bars[-1] if bars else None

    def recent_closed_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        if limit <= 0:
            return []
        return self._closed_timeframe(symbol, timeframe)[-limit:]

    def status(self) -> dict:
        return {sym: self._symbol_status(sym) for sym in self._symbols}

    def _closed_timeframe(self, symbol: str, timeframe: str) -> List[Candle]:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe!r}")
        ones = list(self._closed.get(symbol, []))
        if timeframe == "1m":
            return ones
        return closed_aggregates(ones, _AGG_FACTOR[timeframe])

    def _symbol_status(self, symbol: str) -> dict:
        ones = self._closed.get(symbol, [])
        quality = assess_one_minute_quality(ones)
        status = quality
        last = ones[-1] if ones else None
        if not ones:
            status = (
                CandleDataStatus.FORMING_ONLY
                if self._forming.get(symbol) is not None
                else CandleDataStatus.WAITING_FOR_DATA
            )
        elif quality == CandleDataStatus.HEALTHY and self._is_stale(last):
            status = CandleDataStatus.STALE
        last_ny = normalize_to_ny(last) if last is not None else None
        return {
            "status": status.value,
            "one_minute_count": len(ones),
            "five_minute_count": len(self._closed_timeframe(symbol, "5m")),
            "fifteen_minute_count": len(self._closed_timeframe(symbol, "15m")),
            "forming": self._forming.get(symbol) is not None,
            "last_closed_utc": last.start.isoformat() if last is not None else None,
            "last_closed_ny": last_ny.start.isoformat() if last_ny is not None else None,
        }

    def _is_stale(self, candle: Optional[Candle]) -> bool:
        if candle is None or candle.end.tzinfo is None:
            return False
        age = (self._now_fn() - candle.end).total_seconds()
        return age > self._stale_seconds
