"""Market-data provider abstractions for autonomous trading.

The autonomous live path treats quotes as safety-critical inputs.  These
models intentionally separate time-sensitive execution quotes from historical
or advisory data sources such as Yahoo Finance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Protocol


IBKR_SOURCE = "IBKR"
YAHOO_SOURCE = "YAHOO"

IBKR_MARKET_DATA_TYPE_LIVE = "LIVE"
IBKR_MARKET_DATA_TYPE_FROZEN = "FROZEN"
IBKR_MARKET_DATA_TYPE_DELAYED = "DELAYED"
IBKR_MARKET_DATA_TYPE_DELAYED_FROZEN = "DELAYED_FROZEN"
IBKR_MARKET_DATA_TYPE_UNKNOWN = "UNKNOWN"

IBKR_MARKET_DATA_TYPE_BY_CODE = {
    1: IBKR_MARKET_DATA_TYPE_LIVE,
    2: IBKR_MARKET_DATA_TYPE_FROZEN,
    3: IBKR_MARKET_DATA_TYPE_DELAYED,
    4: IBKR_MARKET_DATA_TYPE_DELAYED_FROZEN,
}


@dataclass
class MarketDataQuote:
    """Latest level-I quote snapshot for one symbol."""

    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    close: Optional[float] = None
    previous_close: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    last_size: Optional[float] = None
    timestamp: Optional[datetime] = None
    bid_timestamp: Optional[datetime] = None
    ask_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None
    source: str = IBKR_SOURCE
    market_data_type: str = IBKR_MARKET_DATA_TYPE_UNKNOWN
    feed_healthy: Optional[bool] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "close": self.close,
            "previous_close": self.previous_close,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_size": self.last_size,
            "timestamp": _iso(self.timestamp),
            "quote_timestamp": _iso(self.timestamp),
            "bid_timestamp": _iso(self.bid_timestamp),
            "ask_timestamp": _iso(self.ask_timestamp),
            "last_timestamp": _iso(self.last_timestamp),
            "source": self.source,
            "market_data_source": self.source,
            "market_data_type": self.market_data_type,
            "feed_healthy": self.feed_healthy,
            "market_data_feed_healthy": self.feed_healthy,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    def to_candidate_extras(self) -> Dict[str, Any]:
        """Return keys consumed by ``TradePlanner``/``MarketDataHealthGuard``."""

        payload = self.to_dict()
        return {
            "bid": payload["bid"],
            "ask": payload["ask"],
            "quote_last": payload["last"],
            "last": payload["last"],
            "previous_close": payload["previous_close"],
            "quote_timestamp": payload["quote_timestamp"],
            "bid_timestamp": payload["bid_timestamp"],
            "ask_timestamp": payload["ask_timestamp"],
            "last_timestamp": payload["last_timestamp"],
            "market_data_source": payload["market_data_source"],
            "market_data_type": payload["market_data_type"],
            "market_data_status": (
                "healthy" if self.feed_healthy is True else "unhealthy"
                if self.feed_healthy is False
                else None
            ),
            "market_data_feed_healthy": payload["market_data_feed_healthy"],
            "market_data_error_code": payload["error_code"],
            "market_data_error_message": payload["error_message"],
        }

    @classmethod
    def from_mapping(cls, payload: Dict[str, Any]) -> "MarketDataQuote":
        feed_healthy = payload.get("feed_healthy")
        if feed_healthy is None:
            feed_healthy = payload.get("market_data_feed_healthy")

        return cls(
            symbol=str(payload.get("symbol") or "").upper(),
            bid=_positive_float(payload.get("bid")),
            ask=_positive_float(payload.get("ask")),
            last=_positive_float(payload.get("last")),
            close=_positive_float(payload.get("close")),
            previous_close=_positive_float(
                payload.get("previous_close") or payload.get("close")
            ),
            bid_size=_positive_float(payload.get("bid_size")),
            ask_size=_positive_float(payload.get("ask_size")),
            last_size=_positive_float(payload.get("last_size")),
            timestamp=_parse_timestamp(
                payload.get("timestamp") or payload.get("quote_timestamp")
            ),
            bid_timestamp=_parse_timestamp(payload.get("bid_timestamp")),
            ask_timestamp=_parse_timestamp(payload.get("ask_timestamp")),
            last_timestamp=_parse_timestamp(payload.get("last_timestamp")),
            source=str(payload.get("source") or payload.get("market_data_source") or IBKR_SOURCE).upper(),
            market_data_type=normalise_market_data_type(
                payload.get("market_data_type")
            ),
            feed_healthy=_bool_or_none(feed_healthy),
            error_code=_optional_int(payload.get("error_code")),
            error_message=(
                str(payload.get("error_message"))
                if payload.get("error_message") is not None
                else None
            ),
        )


@dataclass
class MarketDataProviderStatus:
    """Provider-level health/status snapshot."""

    provider: str
    connected: bool = False
    healthy: bool = False
    subscribed_symbols: list[str] = field(default_factory=list)
    market_data_type: str = IBKR_MARKET_DATA_TYPE_UNKNOWN
    last_error: Optional[Dict[str, Any]] = None
    quotes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "connected": self.connected,
            "healthy": self.healthy,
            "subscribed_symbols": list(self.subscribed_symbols),
            "market_data_type": self.market_data_type,
            "last_error": dict(self.last_error) if self.last_error else None,
            "quotes": dict(self.quotes),
            "reason": self.reason,
        }


class MarketDataProvider(Protocol):
    """Runtime quote provider interface."""

    def subscribe(self, symbols: Iterable[str]) -> None:
        ...

    def unsubscribe(self, symbols: Iterable[str]) -> None:
        ...

    def latest_quote(self, symbol: str) -> Optional[MarketDataQuote]:
        ...

    def status(self) -> MarketDataProviderStatus:
        ...


class IBKRRealtimeMarketDataProvider:
    """Provider adapter around the existing ``TWSBridge`` market-data API."""

    provider_name = IBKR_SOURCE

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def subscribe(self, symbols: Iterable[str]) -> None:
        subscribe = getattr(self._bridge, "subscribe_market_data", None)
        if callable(subscribe):
            subscribe(list(symbols))

    def unsubscribe(self, symbols: Iterable[str]) -> None:
        unsubscribe = getattr(self._bridge, "unsubscribe_market_data", None)
        if callable(unsubscribe):
            unsubscribe(list(symbols))

    def latest_quote(self, symbol: str) -> Optional[MarketDataQuote]:
        getter = getattr(self._bridge, "get_latest_market_data_quote", None)
        if not callable(getter):
            return None
        payload = getter(symbol)
        if not payload:
            return None
        return MarketDataQuote.from_mapping(payload)

    def status(self) -> MarketDataProviderStatus:
        getter = getattr(self._bridge, "get_market_data_status", None)
        if not callable(getter):
            connected = bool(getattr(self._bridge, "is_connected", False))
            return MarketDataProviderStatus(
                provider=self.provider_name,
                connected=connected,
                healthy=False,
                reason="TWS bridge does not expose market-data status",
            )
        payload = getter() or {}
        return MarketDataProviderStatus(
            provider=str(payload.get("provider") or self.provider_name),
            connected=bool(payload.get("connected")),
            healthy=bool(payload.get("healthy")),
            subscribed_symbols=list(payload.get("subscribed_symbols") or []),
            market_data_type=normalise_market_data_type(
                payload.get("market_data_type")
            ),
            last_error=payload.get("last_error"),
            quotes=dict(payload.get("quotes") or {}),
            reason=str(payload.get("reason") or ""),
        )


def normalise_market_data_type(value: Any) -> str:
    if value is None:
        return IBKR_MARKET_DATA_TYPE_UNKNOWN
    if isinstance(value, int):
        return IBKR_MARKET_DATA_TYPE_BY_CODE.get(value, IBKR_MARKET_DATA_TYPE_UNKNOWN)
    text = str(value).strip().upper().replace(" ", "_").replace("-", "_")
    if text in {"1", "REALTIME", "REAL_TIME", "LIVE"}:
        return IBKR_MARKET_DATA_TYPE_LIVE
    if text in {"2", "FROZEN"}:
        return IBKR_MARKET_DATA_TYPE_FROZEN
    if text in {"3", "DELAYED"}:
        return IBKR_MARKET_DATA_TYPE_DELAYED
    if text in {"4", "DELAYED_FROZEN"}:
        return IBKR_MARKET_DATA_TYPE_DELAYED_FROZEN
    return text or IBKR_MARKET_DATA_TYPE_UNKNOWN


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            try:
                return datetime.fromtimestamp(float(text), tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                return None
    return None


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "healthy", "ok", "connected"}:
        return True
    if text in {"false", "no", "0", "unhealthy", "degraded", "down"}:
        return False
    return None
