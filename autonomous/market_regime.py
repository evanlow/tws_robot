"""Market-regime evaluation for autonomous trading.

The autonomous strategy is long-biased by default, so broad-market context is a
first-class safety input.  This module combines the existing SPY intraday gate
with an optional VIX volatility/fear gate.

The evaluator is deliberately pure: it receives a price payload and threshold
settings, then returns a JSON-serialisable decision payload.  It does not fetch
market data or place orders.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def _first_float(payload: Dict[str, Any], keys: Iterable[str]) -> float:
    for key in keys:
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _pct_change(open_price: float, current_price: float) -> Optional[float]:
    if open_price <= 0 or current_price <= 0:
        return None
    return ((current_price - open_price) / open_price) * 100.0


def evaluate_market_regime(
    payload: Dict[str, Any],
    *,
    vix_guard_enabled: bool = True,
    vix_caution_level: float = 20.0,
    vix_block_level: float = 30.0,
    vix_caution_intraday_rise_pct: float = 2.5,
    vix_block_intraday_rise_pct: float = 5.0,
    vix_missing_blocks_trade: bool = False,
    vix_caution_size_multiplier: float = 0.50,
    vix_high_size_multiplier: float = 0.25,
) -> Dict[str, Any]:
    """Return market-regime gate details for the autonomous engine.

    Parameters mirror :class:`autonomous.autonomous_config.AutonomousTradingConfig`
    so the evaluator can be unit-tested independently.

    The returned payload keeps the legacy SPY keys (``open``, ``current``,
    ``bullish``) and adds VIX-aware fields:

    ``trade_allowed``
        Whether new long entries may proceed.
    ``size_multiplier``
        Multiplier applied to deployable cash by the engine when the regime is
        allowed but cautionary.
    """

    spy_open = _first_float(payload, ("open", "day_open", "spy_open"))
    spy_current = _first_float(
        payload,
        ("current", "last", "last_price", "spy_current", "spy_last"),
    )
    spy_bullish = spy_open > 0 and spy_current > spy_open

    vix_open = _first_float(payload, ("vix_open", "vix_day_open"))
    vix_current = _first_float(
        payload,
        ("vix_current", "vix_last", "vix_last_price"),
    )
    vix_available = vix_current > 0
    vix_change_pct = _pct_change(vix_open, vix_current) if vix_open > 0 else None

    reasons = []
    warnings = []
    size_multiplier = 1.0
    trade_allowed = True

    if not spy_bullish:
        trade_allowed = False
        reasons.append("SPY is not bullish intraday")

    vix_level_regime = "disabled"
    vix_direction_regime = "disabled"

    if vix_guard_enabled:
        if not vix_available:
            vix_level_regime = "unavailable"
            vix_direction_regime = "unavailable"
            if vix_missing_blocks_trade:
                trade_allowed = False
                reasons.append("VIX data unavailable")
            else:
                warnings.append("VIX data unavailable; VIX guard not applied")
        else:
            if vix_current >= vix_block_level:
                vix_level_regime = "block"
                trade_allowed = False
                reasons.append(
                    f"VIX {vix_current:.2f} >= block level {vix_block_level:.2f}"
                )
            elif vix_current >= vix_caution_level:
                vix_level_regime = "caution"
                size_multiplier = min(size_multiplier, vix_high_size_multiplier)
                warnings.append(
                    f"VIX {vix_current:.2f} >= caution level {vix_caution_level:.2f}"
                )
            else:
                vix_level_regime = "normal"

            if vix_change_pct is None:
                vix_direction_regime = "unknown"
            elif vix_change_pct >= vix_block_intraday_rise_pct:
                vix_direction_regime = "rising_block"
                trade_allowed = False
                reasons.append(
                    f"VIX intraday rise {vix_change_pct:.2f}% >= block threshold "
                    f"{vix_block_intraday_rise_pct:.2f}%"
                )
            elif vix_change_pct >= vix_caution_intraday_rise_pct:
                vix_direction_regime = "rising_caution"
                size_multiplier = min(size_multiplier, vix_caution_size_multiplier)
                warnings.append(
                    f"VIX intraday rise {vix_change_pct:.2f}% >= caution threshold "
                    f"{vix_caution_intraday_rise_pct:.2f}%"
                )
            elif vix_change_pct <= -vix_caution_intraday_rise_pct:
                vix_direction_regime = "falling"
            else:
                vix_direction_regime = "stable"

    classification = "Bullish / Volatility Acceptable"
    if not spy_bullish:
        classification = "Bearish / Not Suitable"
    elif not trade_allowed:
        classification = "Volatility Stress / Not Suitable"
    elif size_multiplier < 1.0:
        classification = "Bullish / Volatility Caution"

    if not trade_allowed:
        size_multiplier = 0.0

    return {
        "symbol": "SPY",
        "open": spy_open,
        "current": spy_current,
        "bullish": spy_bullish,
        "classification": classification,
        "trade_allowed": trade_allowed,
        "size_multiplier": round(size_multiplier, 4),
        "reasons": reasons,
        "warnings": warnings,
        "vix": {
            "symbol": "^VIX",
            "open": vix_open,
            "current": vix_current,
            "change_pct": round(vix_change_pct, 4) if vix_change_pct is not None else None,
            "available": vix_available,
            "guard_enabled": vix_guard_enabled,
            "level_regime": vix_level_regime,
            "direction_regime": vix_direction_regime,
            "caution_level": vix_caution_level,
            "block_level": vix_block_level,
            "caution_intraday_rise_pct": vix_caution_intraday_rise_pct,
            "block_intraday_rise_pct": vix_block_intraday_rise_pct,
        },
    }
