"""Deterministic setup identities for autonomous evidence learning.

This module is analytics-only.  It maps evidence records and feature payloads
into stable setup IDs so later calibrators can aggregate realized outcomes by
repeatable setup family without changing execution, sizing, or risk gates.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


SETUP_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class SetupDimensions:
    """Canonical dimensions that define one repeatable setup identity."""

    signal_label: str
    quality_label: str
    momentum_label: str
    market_classification: str
    vix_level_regime: str
    vix_direction_regime: str
    sector_regime: str
    time_of_day_regime: str
    support_distance_bucket: str
    resistance_room_bucket: str
    adr_volatility_bucket: str
    basket_context: str
    trade_type: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "signal_label": self.signal_label,
            "quality_label": self.quality_label,
            "momentum_label": self.momentum_label,
            "market_classification": self.market_classification,
            "vix_level_regime": self.vix_level_regime,
            "vix_direction_regime": self.vix_direction_regime,
            "sector_regime": self.sector_regime,
            "time_of_day_regime": self.time_of_day_regime,
            "support_distance_bucket": self.support_distance_bucket,
            "resistance_room_bucket": self.resistance_room_bucket,
            "adr_volatility_bucket": self.adr_volatility_bucket,
            "basket_context": self.basket_context,
            "trade_type": self.trade_type,
        }


@dataclass
class SetupMetadata:
    """Registry row for one deterministic setup family."""

    setup_id: str
    dimensions: SetupDimensions
    version: int = SETUP_REGISTRY_VERSION
    observation_count: int = 0
    symbols: List[str] = field(default_factory=list)
    source: str = "autonomous_evidence"

    def add_observation(self, *, symbol: Optional[str] = None) -> None:
        self.observation_count += 1
        if symbol and symbol not in self.symbols:
            self.symbols.append(symbol)
            self.symbols.sort()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "setup_id": self.setup_id,
            "version": self.version,
            "dimensions": self.dimensions.to_dict(),
            "observation_count": self.observation_count,
            "symbols": list(self.symbols),
            "source": self.source,
        }


class SetupRegistry:
    """Build setup identities and registry metadata from evidence records."""

    def dimensions_from_record(self, record: Dict[str, Any]) -> SetupDimensions:
        bucket = record.get("strategy_bucket") or {}
        market_gate = record.get("market_gate") or {}
        vix = market_gate.get("vix") or {}
        selected = record.get("selected") or {}
        features = (
            record.get("features")
            or selected.get("features")
            or record.get("candidate_features")
            or {}
        )
        candidate = selected.get("candidate") or record.get("candidate") or {}
        extras = candidate.get("extras") or {}
        trade_plan = record.get("trade_plan") or {}

        support_distance = _first_float(
            features.get("support_distance_pct"),
            extras.get("support_distance_pct"),
            _support_distance_pct(candidate.get("last_price"), candidate.get("support_price")),
        )
        resistance_room = _first_float(
            features.get("resistance_room_pct"),
            extras.get("resistance_room_pct"),
            _resistance_room_pct(candidate.get("resistance_price"), candidate.get("last_price")),
        )
        adr_pct = _first_float(features.get("adr_pct"), extras.get("adr_pct"))

        return SetupDimensions(
            signal_label=_value(
                bucket.get("signal_label"),
                features.get("signal_label"),
                candidate.get("signal_label"),
                default="unknown_signal",
            ),
            quality_label=_value(
                bucket.get("quality_label"),
                features.get("quality_label"),
                extras.get("quality_label"),
                default="unknown_quality",
            ),
            momentum_label=_value(
                bucket.get("momentum_label"),
                features.get("momentum_label"),
                extras.get("momentum_label"),
                default="unknown_momentum",
            ),
            market_classification=_value(
                bucket.get("market_classification"),
                features.get("market_classification"),
                market_gate.get("classification"),
                default="unknown_market",
            ),
            vix_level_regime=_value(
                bucket.get("vix_level_regime"),
                features.get("vix_level_regime"),
                vix.get("level_regime"),
                default="unknown_vix_level",
            ),
            vix_direction_regime=_value(
                bucket.get("vix_direction_regime"),
                features.get("vix_direction_regime"),
                vix.get("direction_regime"),
                default="unknown_vix_direction",
            ),
            sector_regime=_sector_regime(bucket=bucket, features=features, extras=extras),
            time_of_day_regime=_value(
                features.get("time_of_day_regime"),
                extras.get("time_of_day_regime"),
                default="unknown_time_of_day",
            ),
            support_distance_bucket=_support_distance_bucket(support_distance),
            resistance_room_bucket=_resistance_room_bucket(resistance_room),
            adr_volatility_bucket=_adr_volatility_bucket(adr_pct),
            basket_context=_basket_context(record),
            trade_type=_value(
                trade_plan.get("trade_type"),
                trade_plan.get("action"),
                features.get("trade_type"),
                default="unknown_trade_type",
            ),
        )

    def setup_id_for_dimensions(self, dimensions: SetupDimensions) -> str:
        parts = [
            f"signal-{_slug(dimensions.signal_label)}",
            f"quality-{_slug(dimensions.quality_label)}",
            f"momentum-{_slug(dimensions.momentum_label)}",
            f"market-{_slug(dimensions.market_classification)}",
            f"vix-{_slug(dimensions.vix_level_regime)}",
            f"vixdir-{_slug(dimensions.vix_direction_regime)}",
            f"sector-{_slug(dimensions.sector_regime)}",
            f"time-{_slug(dimensions.time_of_day_regime)}",
            f"support-{_slug(dimensions.support_distance_bucket)}",
            f"resistance-{_slug(dimensions.resistance_room_bucket)}",
            f"vol-{_slug(dimensions.adr_volatility_bucket)}",
            f"basket-{_slug(dimensions.basket_context)}",
            f"type-{_slug(dimensions.trade_type)}",
        ]
        return f"setup_v{SETUP_REGISTRY_VERSION}__" + "__".join(parts)

    def metadata_for_record(self, record: Dict[str, Any]) -> SetupMetadata:
        dimensions = self.dimensions_from_record(record)
        metadata = SetupMetadata(
            setup_id=self.setup_id_for_dimensions(dimensions),
            dimensions=dimensions,
        )
        metadata.add_observation(symbol=_symbol(record))
        return metadata

    def build_registry(self, records: Iterable[Dict[str, Any]]) -> Dict[str, SetupMetadata]:
        registry: Dict[str, SetupMetadata] = {}
        for record in records:
            metadata = self.metadata_for_record(record)
            existing = registry.get(metadata.setup_id)
            if existing is None:
                registry[metadata.setup_id] = metadata
                continue
            existing.add_observation(symbol=_symbol(record))
        return registry


def setup_id_for_record(record: Dict[str, Any]) -> str:
    """Convenience wrapper for a deterministic setup ID."""

    return SetupRegistry().metadata_for_record(record).setup_id


def _value(*values: Any, default: str) -> str:
    for value in values:
        if value is None or value == "":
            continue
        return str(value)
    return default


def _symbol(record: Dict[str, Any]) -> Optional[str]:
    value = record.get("symbol")
    if value:
        return str(value)
    trade_plan = record.get("trade_plan") or {}
    if trade_plan.get("symbol"):
        return str(trade_plan["symbol"])
    return None


def _sector_regime(
    *,
    bucket: Dict[str, Any],
    features: Dict[str, Any],
    extras: Dict[str, Any],
) -> str:
    explicit = _value(
        features.get("sector_regime"),
        extras.get("sector_regime"),
        default="",
    )
    if explicit:
        return explicit
    if features.get("sector_bullish") is True:
        return "sector_supportive"
    if features.get("sector_bullish") is False:
        return "sector_hostile"
    sector = bucket.get("sector") or features.get("sector")
    return f"sector_{sector}" if sector else "unknown_sector_regime"


def _basket_context(record: Dict[str, Any]) -> str:
    trade_plan = record.get("trade_plan") or {}
    candidate_counts = record.get("candidate_counts") or {}
    if trade_plan.get("basket_id") or trade_plan.get("leg_id"):
        return "basket_leg"
    if record.get("basket_id") or record.get("selected_basket"):
        return "basket_leg"
    try:
        if int(candidate_counts.get("basket_legs") or 0) > 0:
            return "basket_leg"
    except (TypeError, ValueError):
        pass
    return "single_leg" if trade_plan else "unknown_basket_context"


def _support_distance_bucket(value: Optional[float]) -> str:
    if value is None:
        return "unknown_support_distance"
    if value <= 0:
        return "at_or_below_support"
    if value <= 0.03:
        return "near_support"
    if value <= 0.08:
        return "moderate_support_distance"
    return "extended_from_support"


def _resistance_room_bucket(value: Optional[float]) -> str:
    if value is None:
        return "unknown_resistance_room"
    if value <= 0:
        return "no_resistance_room"
    if value <= 0.03:
        return "tight_resistance_room"
    if value <= 0.08:
        return "moderate_resistance_room"
    return "open_resistance_room"


def _adr_volatility_bucket(value: Optional[float]) -> str:
    if value is None:
        return "unknown_adr_volatility"
    if value <= 0.02:
        return "quiet_adr_volatility"
    if value <= 0.05:
        return "normal_adr_volatility"
    if value <= 0.08:
        return "elevated_adr_volatility"
    return "extreme_adr_volatility"


def _support_distance_pct(last_price: Any, support_price: Any) -> Optional[float]:
    last = _float(last_price)
    support = _float(support_price)
    if last is None or support is None or last <= 0:
        return None
    return (last - support) / last


def _resistance_room_pct(resistance_price: Any, last_price: Any) -> Optional[float]:
    resistance = _float(resistance_price)
    last = _float(last_price)
    if resistance is None or last is None or last <= 0:
        return None
    return (resistance - last) / last


def _first_float(*values: Any) -> Optional[float]:
    for value in values:
        out = _float(value)
        if out is not None:
            return out
    return None


def _float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _slug(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"
