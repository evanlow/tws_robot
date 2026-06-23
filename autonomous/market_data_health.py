"""Market-data health guard for autonomous live trade planning.

The guard is deliberately data-source agnostic.  Signal providers attach small
quote snapshots to ``CandidateSignal.extras`` and the planner asks this module
whether those quotes are fresh enough, complete enough, and internally sane
for assisted-live use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from autonomous.market_data_provider import (
    IBKR_MARKET_DATA_TYPE_LIVE,
    IBKR_SOURCE,
    YAHOO_SOURCE,
    normalise_market_data_type,
)


@dataclass
class MarketDataHealthDecision:
    """Diagnostic result for one candidate quote snapshot."""

    allowed: bool
    reason: str
    quote_age_seconds: Optional[float] = None
    max_quote_age_seconds: float = 60.0
    bid_age_seconds: Optional[float] = None
    ask_age_seconds: Optional[float] = None
    last_age_seconds: Optional[float] = None
    spread_pct: Optional[float] = None
    last_mid_deviation_pct: Optional[float] = None
    source: Optional[str] = None
    market_data_type: Optional[str] = None
    feed_healthy: Optional[bool] = None
    market_open: Optional[bool] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "quote_age_seconds": _round(self.quote_age_seconds),
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "bid_age_seconds": _round(self.bid_age_seconds),
            "ask_age_seconds": _round(self.ask_age_seconds),
            "last_age_seconds": _round(self.last_age_seconds),
            "spread_pct": _round(self.spread_pct, places=6),
            "last_mid_deviation_pct": _round(self.last_mid_deviation_pct, places=6),
            "source": self.source,
            "market_data_source": self.source,
            "market_data_type": self.market_data_type,
            "feed_healthy": self.feed_healthy,
            "market_open": self.market_open,
            "warnings": list(self.warnings),
        }


class MarketDataHealthGuard:
    """Validate quote freshness and feed health before live submission."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_quote_age_seconds: float = 60.0,
        max_spread_pct: float = 0.003,
        max_last_mid_deviation_pct: float = 0.01,
        block_stale_quotes_live: bool = True,
        block_missing_bid_ask_live: bool = False,
        block_missing_timestamp_live: bool = False,
        block_feed_unhealthy_live: bool = True,
        block_market_closed_live: bool = True,
        required_live_source: str = IBKR_SOURCE,
        require_live_market_data_type: bool = True,
        allow_yahoo_for_live_trading: bool = False,
    ) -> None:
        self.enabled = enabled
        self.max_quote_age_seconds = max_quote_age_seconds
        self.max_spread_pct = max_spread_pct
        self.max_last_mid_deviation_pct = max_last_mid_deviation_pct
        self.block_stale_quotes_live = block_stale_quotes_live
        self.block_missing_bid_ask_live = block_missing_bid_ask_live
        self.block_missing_timestamp_live = block_missing_timestamp_live
        self.block_feed_unhealthy_live = block_feed_unhealthy_live
        self.block_market_closed_live = block_market_closed_live
        self.required_live_source = str(required_live_source or IBKR_SOURCE).upper()
        self.require_live_market_data_type = require_live_market_data_type
        self.allow_yahoo_for_live_trading = allow_yahoo_for_live_trading

    def evaluate(
        self,
        *,
        symbol: str,
        mode: Any,
        bid: Any = None,
        ask: Any = None,
        last: Any = None,
        reference_price: Any = None,
        bid_timestamp: Any = None,
        ask_timestamp: Any = None,
        last_timestamp: Any = None,
        quote_timestamp: Any = None,
        source: Any = None,
        market_data_type: Any = None,
        feed_healthy: Any = None,
        feed_status: Any = None,
        market_open: Any = None,
        now: Optional[datetime] = None,
    ) -> MarketDataHealthDecision:
        if not self.enabled:
            return MarketDataHealthDecision(
                True,
                "market-data health guard disabled",
                max_quote_age_seconds=self.max_quote_age_seconds,
            )

        now = _normalise_now(now)
        live = _is_live_mode(mode)
        bid_f = _positive_float(bid)
        ask_f = _positive_float(ask)
        last_f = _positive_float(last) or _positive_float(reference_price)
        warnings: list[str] = []
        blockers: list[str] = []

        source_text = _normalise_source(source)
        market_data_type_text = normalise_market_data_type(market_data_type)
        feed_ok = _feed_healthy(feed_healthy, feed_status)
        market_open_bool = _bool_or_none(market_open)

        if live:
            if source_text == YAHOO_SOURCE and not self.allow_yahoo_for_live_trading:
                blockers.append(f"{symbol}: Yahoo Finance quote source is not allowed for live trading")
            if self.required_live_source and source_text != self.required_live_source:
                blockers.append(
                    f"{symbol}: quote source {source_text or 'UNKNOWN'} != required {self.required_live_source}"
                )
            if (
                self.require_live_market_data_type
                and source_text == self.required_live_source
                and market_data_type_text != IBKR_MARKET_DATA_TYPE_LIVE
            ):
                blockers.append(
                    f"{symbol}: IBKR market data type {market_data_type_text} is not LIVE"
                )
        else:
            if source_text == YAHOO_SOURCE:
                warnings.append(f"{symbol}: Yahoo Finance quote source is advisory only")

        if feed_ok is False:
            msg = f"{symbol}: market-data feed unhealthy"
            if live and self.block_feed_unhealthy_live:
                blockers.append(msg)
            else:
                warnings.append(msg)
        if market_open_bool is False:
            msg = f"{symbol}: market is closed"
            if live and self.block_market_closed_live:
                blockers.append(msg)
            else:
                warnings.append(msg)

        if bid_f is None or ask_f is None:
            msg = f"{symbol}: bid/ask unavailable"
            if live and self.block_missing_bid_ask_live:
                blockers.append(msg)
            else:
                warnings.append(msg)

        spread_pct = None
        last_mid_deviation_pct = None
        if bid_f is not None and ask_f is not None:
            if ask_f < bid_f:
                blockers.append(f"{symbol}: crossed quotes (ask {ask_f} < bid {bid_f})")
            else:
                mid = (bid_f + ask_f) / 2.0
                if mid > 0:
                    spread_pct = (ask_f - bid_f) / mid
                    if spread_pct > self.max_spread_pct:
                        msg = (
                            f"{symbol}: quote spread {spread_pct:.4%} > "
                            f"max {self.max_spread_pct:.4%}"
                        )
                        if live:
                            blockers.append(msg)
                        else:
                            warnings.append(msg)
                    if last_f is not None:
                        last_mid_deviation_pct = abs(last_f - mid) / mid
                        if last_mid_deviation_pct > self.max_last_mid_deviation_pct:
                            msg = (
                                f"{symbol}: last/mid deviation "
                                f"{last_mid_deviation_pct:.4%} > "
                                f"max {self.max_last_mid_deviation_pct:.4%}"
                            )
                            if live:
                                blockers.append(msg)
                            else:
                                warnings.append(msg)

        bid_age = _age_seconds(bid_timestamp, now)
        ask_age = _age_seconds(ask_timestamp, now)
        last_age = _age_seconds(last_timestamp, now)
        shared_age = _age_seconds(quote_timestamp, now)
        known_ages = [age for age in (bid_age, ask_age, last_age, shared_age) if age is not None]
        quote_age = max(known_ages) if known_ages else None

        if quote_age is None:
            msg = f"{symbol}: quote timestamp unavailable"
            if live and self.block_missing_timestamp_live:
                blockers.append(msg)
            else:
                warnings.append(msg)
        elif quote_age > self.max_quote_age_seconds:
            msg = (
                f"{symbol}: quote age {quote_age:.1f}s > "
                f"max {self.max_quote_age_seconds:.1f}s"
            )
            if live and self.block_stale_quotes_live:
                blockers.append(msg)
            else:
                warnings.append(msg)

        if blockers:
            return MarketDataHealthDecision(
                False,
                "; ".join(blockers),
                quote_age_seconds=quote_age,
                max_quote_age_seconds=self.max_quote_age_seconds,
                bid_age_seconds=bid_age,
                ask_age_seconds=ask_age,
                last_age_seconds=last_age,
                spread_pct=spread_pct,
                last_mid_deviation_pct=last_mid_deviation_pct,
                source=source_text,
                market_data_type=market_data_type_text,
                feed_healthy=feed_ok,
                market_open=market_open_bool,
                warnings=warnings,
            )

        return MarketDataHealthDecision(
            True,
            "market-data health acceptable",
            quote_age_seconds=quote_age,
            max_quote_age_seconds=self.max_quote_age_seconds,
            bid_age_seconds=bid_age,
            ask_age_seconds=ask_age,
            last_age_seconds=last_age,
            spread_pct=spread_pct,
            last_mid_deviation_pct=last_mid_deviation_pct,
            source=source_text,
            market_data_type=market_data_type_text,
            feed_healthy=feed_ok,
            market_open=market_open_bool,
            warnings=warnings,
        )


def _is_live_mode(mode: Any) -> bool:
    value = getattr(mode, "value", mode)
    return str(value) == "assisted_live"


def _normalise_now(value: Optional[datetime]) -> datetime:
    out = value or datetime.now(timezone.utc)
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out


def _age_seconds(value: Any, now: datetime) -> Optional[float]:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (now - parsed).total_seconds())


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


def _bool_or_none(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "1", "open", "opened"}:
            return True
        if text in {"false", "no", "0", "closed", "halted"}:
            return False
    return None


def _feed_healthy(feed_healthy: Any, feed_status: Any) -> Optional[bool]:
    explicit = _bool_or_none(feed_healthy)
    if explicit is not None:
        return explicit
    if feed_status is None:
        return None
    status = str(feed_status).strip().lower()
    if status in {"healthy", "ok", "ready", "live", "connected"}:
        return True
    if status in {"unhealthy", "degraded", "down", "stale", "disconnected", "not_configured"}:
        return False
    return None


def _normalise_source(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper().replace(" ", "_").replace("-", "_")
    if text in {"YAHOO", "YAHOO_FINANCE", "YFINANCE"}:
        return YAHOO_SOURCE
    if text in {"IB", "IBKR", "INTERACTIVE_BROKERS"}:
        return IBKR_SOURCE
    return text or None


def _round(value: Optional[float], *, places: int = 3) -> Optional[float]:
    return round(value, places) if value is not None else None
