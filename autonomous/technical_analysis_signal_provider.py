"""Production ``SignalProvider`` backed by the S&P 500 screener service.

The autonomous trading engine consumes :class:`CandidateSignal` objects emitted
by a ``SignalProvider``.  This provider reuses the existing S&P 500 screener
technical/fundamental analysis to produce ``Strong(100) / Confirmed Rebound``
candidates.

A row qualifies when both conditions hold:

* ``momentum_label == "Confirmed Rebound"``
* ``quality_label == "Strong"``

Qualifying rows receive ``strength_score = 100`` so the default ranker allows
them through.  Non-qualifying rows are still returned with ``strength_score = 0``
so the rejection reason remains visible in audit/evidence logs.

Support/resistance enrichment
-----------------------------

When a screener row publishes ``support_price`` / ``resistance_price``, this
provider forwards those levels.  Otherwise, qualifying production signals are
enriched by fetching daily bars and selecting the nearest recent low below the
current price and nearest recent high above it.  Direct/test construction keeps
this enrichment disabled by default to avoid accidental network I/O.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from autonomous.adr_calculator import ADRResult, calculate_adr
from autonomous.candidate_scanner import CandidateSignal
from autonomous.technical_levels import compute_support_resistance_levels

logger = logging.getLogger(__name__)

STRONG_REBOUND_STRENGTH_SCORE: int = 100
_PRODUCTION_DEFAULT_LEVEL_LOOKBACK_DAYS = 30


class TechnicalAnalysisSignalProvider:
    """``SignalProvider`` backed by the existing S&P 500 screener service."""

    def __init__(
        self,
        screener_service: Any = None,
        refresh_on_first_call: bool = True,
        rows_loader: Optional[Callable[[], Any]] = None,
        adr_lookback_days: int = 0,
        support_resistance_lookback_days: Optional[int] = None,
        price_history_fetcher: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    ) -> None:
        use_production_defaults = (
            screener_service is None
            and rows_loader is None
            and support_resistance_lookback_days is None
        )
        if screener_service is None and rows_loader is None:
            from web.sp500_screener_service import sp500_screener_service
            screener_service = sp500_screener_service
        self._screener_service = screener_service
        self._rows_loader = rows_loader
        self._refresh_on_first_call = refresh_on_first_call
        self._adr_lookback_days = int(adr_lookback_days or 0)
        if use_production_defaults:
            self._support_resistance_lookback_days = _PRODUCTION_DEFAULT_LEVEL_LOOKBACK_DAYS
        else:
            self._support_resistance_lookback_days = int(support_resistance_lookback_days or 0)
        self._price_history_fetcher = price_history_fetcher
        self._rows_by_symbol: Optional[Dict[str, Dict[str, Any]]] = None

    def analyze(self, symbol: str) -> Optional[CandidateSignal]:
        """Return a :class:`CandidateSignal` for ``symbol`` or ``None``."""
        try:
            row = self._lookup_row(symbol)
        except Exception:
            logger.exception("TechnicalAnalysisSignalProvider failed to load row for %s", symbol)
            return None
        if not row or row.get("bollinger_status") == "insufficient_data":
            return None
        try:
            signal = self._row_to_signal(symbol, row)
        except Exception:
            logger.exception("TechnicalAnalysisSignalProvider failed mapping row for %s", symbol)
            return None

        if signal.strength_score >= STRONG_REBOUND_STRENGTH_SCORE:
            self._enrich_support_resistance(signal)

        if self._adr_lookback_days > 0:
            adr_result = self._compute_adr_for_symbol(symbol, signal.last_price)
            if adr_result is not None:
                signal.extras["adr"] = adr_result.adr
                signal.extras["adr_pct"] = adr_result.adr_pct
                signal.extras["adr_lookback_days_used"] = adr_result.lookback_days_used
                signal.extras["adr_valid"] = adr_result.valid
        return signal

    def _lookup_row(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self._rows_by_symbol is None:
            self._rows_by_symbol = self._load_rows()
        return self._rows_by_symbol.get(symbol.upper())

    def _load_rows(self) -> Dict[str, Dict[str, Any]]:
        if self._rows_loader is not None:
            rows = self._rows_loader() or []
        else:
            try:
                payload = self._screener_service.get_screener_data(
                    refresh=self._refresh_on_first_call,
                )
            except Exception:
                logger.exception("TechnicalAnalysisSignalProvider: screener_service raised")
                return {}
            rows = (payload or {}).get("rows") or []
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                out[sym] = row
        return out

    def _history_fetcher(self):
        if self._price_history_fetcher is not None:
            return self._price_history_fetcher
        try:
            from data.fundamentals import fetch_price_history
            return fetch_price_history
        except ImportError:
            return None

    def _enrich_support_resistance(self, signal: CandidateSignal) -> None:
        if signal.support_price and signal.resistance_price:
            signal.extras.setdefault("levels_source", "screener_row")
            signal.extras["levels_valid"] = True
            return
        lookback = self._support_resistance_lookback_days
        if lookback <= 0 or signal.last_price <= 0:
            return
        fetcher = self._history_fetcher()
        if fetcher is None:
            signal.extras["levels_valid"] = False
            signal.extras["levels_reason"] = "price history fetcher unavailable"
            return
        try:
            period_days = max(lookback * 2, 30)
            period = f"{period_days}d" if period_days <= 60 else "3mo"
            bars = fetcher(signal.symbol, period=period, interval="1d")
        except Exception:
            logger.debug("support/resistance price history fetch failed for %s", signal.symbol)
            signal.extras["levels_valid"] = False
            signal.extras["levels_reason"] = "price history fetch failed"
            return
        levels = compute_support_resistance_levels(
            daily_bars=bars or [],
            current_price=signal.last_price,
            lookback_days=lookback,
        )
        if signal.support_price is None and levels.get("support_price") is not None:
            signal.support_price = levels["support_price"]
        if signal.resistance_price is None and levels.get("resistance_price") is not None:
            signal.resistance_price = levels["resistance_price"]
        signal.extras["support_source"] = levels.get("support_source")
        signal.extras["resistance_source"] = levels.get("resistance_source")
        signal.extras["levels_lookback_days"] = levels.get("lookback_days")
        signal.extras["levels_bars_used"] = levels.get("bars_used")
        signal.extras["levels_valid"] = bool(levels.get("valid"))
        signal.extras["levels_reason"] = levels.get("reason")

    def _compute_adr_for_symbol(self, symbol: str, last_price: float) -> Optional[ADRResult]:
        if last_price <= 0:
            return None
        fetcher = self._history_fetcher()
        if fetcher is None:
            return None
        try:
            period_days = self._adr_lookback_days * 2
            period = f"{period_days}d" if period_days <= 60 else "3mo"
            bars = fetcher(symbol, period=period, interval="1d")
        except Exception:
            logger.debug("ADR price history fetch failed for %s", symbol)
            return None
        if not bars:
            return None
        result = calculate_adr(
            daily_bars=bars,
            reference_price=last_price,
            lookback_days=self._adr_lookback_days,
        )
        return result if result.valid else None

    @staticmethod
    def _row_to_signal(symbol: str, row: Dict[str, Any]) -> CandidateSignal:
        momentum_label = row.get("momentum_label") or ""
        quality_label = row.get("quality_label") or ""
        qualifies = momentum_label == "Confirmed Rebound" and quality_label == "Strong"
        strength_score = STRONG_REBOUND_STRENGTH_SCORE if qualifies else 0
        signal_label = "Confirmed Rebound" if qualifies else (momentum_label or "No Signal")

        reasons = []
        for r in (row.get("momentum_reasons") or []):
            if isinstance(r, str):
                reasons.append(r)
        for r in (row.get("quality_reasons") or []):
            if isinstance(r, str):
                reasons.append(r)

        support_price = _positive_float(row.get("support_price"))
        resistance_price = _positive_float(row.get("resistance_price"))
        bid = _positive_float(_first(row, "bid", "quote_bid", "execution_bid"))
        ask = _positive_float(_first(row, "ask", "quote_ask", "execution_ask"))
        quote_timestamp = _first(
            row,
            "quote_timestamp",
            "market_data_timestamp",
            "updated_at",
            "last_updated",
            "timestamp",
            "as_of",
        )

        return CandidateSignal(
            symbol=symbol.upper(),
            strength_score=strength_score,
            signal_label=signal_label,
            company_name=row.get("company") or "",
            sector=row.get("sector") or "",
            last_price=float(row.get("current_price") or 0.0),
            technical_reason="; ".join(reasons),
            support_price=support_price,
            resistance_price=resistance_price,
            volume_ok=True,
            trend_ok=True,
            earnings_date=None,
            extras={
                "quality_label": quality_label,
                "quality_score": row.get("quality_score"),
                "momentum_label": momentum_label,
                "momentum_confirmation": row.get("momentum_confirmation"),
                "bollinger_status": row.get("bollinger_status"),
                "rsi_14": row.get("rsi_14"),
                "rsi_status": row.get("rsi_status"),
                "support_source": row.get("support_source") if support_price else None,
                "resistance_source": row.get("resistance_source") if resistance_price else None,
                "levels_valid": bool(support_price or resistance_price),
                "bid": bid,
                "ask": ask,
                "quote_last": _positive_float(_first(row, "last", "quote_last", "current_price")),
                "quote_timestamp": quote_timestamp,
                "bid_timestamp": _first(row, "bid_timestamp", "quote_bid_timestamp"),
                "ask_timestamp": _first(row, "ask_timestamp", "quote_ask_timestamp"),
                "last_timestamp": _first(row, "last_timestamp", "quote_last_timestamp"),
                "market_data_source": _first(row, "market_data_source", "quote_source", "source") or "YAHOO",
                "market_data_status": _first(row, "market_data_status", "feed_status", "data_status"),
                "market_data_type": _first(row, "market_data_type", "ibkr_market_data_type"),
                "market_data_feed_healthy": _first(row, "market_data_feed_healthy", "feed_healthy"),
                "market_is_open": _first(row, "market_is_open", "market_open"),
            },
        )

    @classmethod
    def try_build(cls, **kwargs: Any) -> Optional["TechnicalAnalysisSignalProvider"]:
        try:
            return cls(**kwargs)
        except Exception:
            logger.exception(
                "TechnicalAnalysisSignalProvider construction failed; caller should fall back to StaticSignalProvider"
            )
            return None


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _first(mapping: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None
