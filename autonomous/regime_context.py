"""Sector and time-of-day regime helpers.

These helpers enrich candidate features with stable context labels.  They are
purely descriptive and do not place orders or change execution behaviour.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Dict, Optional


SECTOR_ETF_MAP = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Tech": "XLK",
    "Technology": "XLK",
}


def sector_etf_for(sector: Optional[str]) -> Optional[str]:
    if not sector:
        return None
    return SECTOR_ETF_MAP.get(str(sector))


def classify_sector_regime(*, sector_bullish: Optional[bool], relative_strength_pct: Optional[float]) -> str:
    if sector_bullish is False:
        return "sector_hostile"
    if sector_bullish is True and relative_strength_pct is not None and relative_strength_pct >= 0:
        return "sector_supportive"
    if sector_bullish is True:
        return "sector_bullish_unknown_rs"
    if relative_strength_pct is not None:
        return "sector_relative_strength" if relative_strength_pct >= 0 else "sector_relative_weakness"
    return "sector_unknown"


def classify_time_of_day(moment: Optional[Any] = None) -> str:
    dt = _parse_datetime(moment) or datetime.now(timezone.utc)
    t = dt.time()
    if time(13, 30) <= t < time(14, 30):
        return "opening_volatility"
    if time(14, 30) <= t < time(19, 0):
        return "regular_session"
    if time(19, 0) <= t < time(20, 30):
        return "midday_liquidity_lull"
    if time(20, 30) <= t < time(21, 0):
        return "closing_volatility"
    return "outside_regular_session"


def build_regime_context(
    *,
    sector: Optional[str],
    extras: Optional[Dict[str, Any]] = None,
    market_gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    extras = extras or {}
    market_gate = market_gate or {}
    sector_etf = extras.get("sector_etf") or sector_etf_for(sector)
    sector_bullish = _bool_or_none(extras.get("sector_etf_bullish", extras.get("sector_bullish")))
    relative_strength = _float(extras.get("sector_relative_strength_pct"))
    moment = extras.get("timestamp") or market_gate.get("timestamp")
    tod = extras.get("time_of_day_regime") or market_gate.get("time_of_day_regime") or classify_time_of_day(moment)

    return {
        "sector_etf": sector_etf,
        "sector_bullish": sector_bullish,
        "sector_relative_strength_pct": relative_strength,
        "sector_regime": classify_sector_regime(
            sector_bullish=sector_bullish,
            relative_strength_pct=relative_strength,
        ),
        "time_of_day_regime": tod,
    }


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "bullish"}:
            return True
        if lowered in {"false", "no", "0", "bearish"}:
            return False
    return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
