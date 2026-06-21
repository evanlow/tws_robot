"""Broker-side protection verification for autonomous live trades.

This module verifies that an open autonomous live position has a broker-visible
protective stop/bracket child order before the runner allows new entries.
It is intentionally snapshot-based and conservative: when broker order state is
missing or ambiguous, verification fails closed and marks recovery required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from autonomous.trade_store import AutonomousTrade


ACTIVE_ORDER_STATUSES = {
    "apipending",
    "pendingsubmit",
    "presubmitted",
    "submitted",
}
INACTIVE_ORDER_STATUSES = {
    "cancelled",
    "filled",
    "inactive",
    "rejected",
}
PROTECTIVE_ORDER_TYPES = {
    "STP",
    "STP LMT",
    "STOP",
    "STOP LIMIT",
    "TRAIL",
    "TRAIL LIMIT",
    "TRAILLMT",
}


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    """Normalised broker open-order snapshot used by protection checks."""

    order_id: Optional[int]
    symbol: str
    action: str = ""
    order_type: str = ""
    quantity: float = 0.0
    remaining: Optional[float] = None
    status: str = ""
    parent_id: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any) -> "BrokerOrderSnapshot":
        """Normalise dicts, core.order_manager.OrderRecord, or simple objects."""

        def get(name: str, default: Any = None) -> Any:
            if isinstance(raw, dict):
                return raw.get(name, default)
            return getattr(raw, name, default)

        order = get("order")
        contract = get("contract")

        order_id = _as_int(
            get("order_id", get("orderId", get("id", get("permId"))))
        )
        symbol = _as_str(
            get("symbol")
            or _obj_get(contract, "symbol")
            or get("contract_symbol")
        )
        action = _as_str(get("action") or _obj_get(order, "action")).upper()
        order_type = _as_str(
            get("order_type")
            or get("orderType")
            or _obj_get(order, "orderType")
        ).upper()
        quantity = _as_float(
            get("quantity")
            or get("totalQuantity")
            or _obj_get(order, "totalQuantity")
            or 0.0
        )
        remaining = _as_float_or_none(get("remaining"))
        status_value = get("status", "")
        status = getattr(status_value, "value", status_value)
        parent_id = _as_int(
            get("parent_id", get("parentId", _obj_get(order, "parentId")))
        )
        return cls(
            order_id=order_id,
            symbol=symbol,
            action=action,
            order_type=order_type,
            quantity=quantity,
            remaining=remaining,
            status=_as_str(status),
            parent_id=parent_id,
            raw=dict(raw) if isinstance(raw, dict) else {},
        )

    @property
    def active_quantity(self) -> float:
        if self.remaining is not None and self.remaining > 0:
            return self.remaining
        return self.quantity

    @property
    def is_active(self) -> bool:
        if not self.status:
            return True
        normalised = self.status.replace(" ", "").replace("_", "").lower()
        return normalised in ACTIVE_ORDER_STATUSES and normalised not in INACTIVE_ORDER_STATUSES

    @property
    def is_protective_sell_stop(self) -> bool:
        return (
            self.action == "SELL"
            and self.order_type in PROTECTIVE_ORDER_TYPES
            and self.is_active
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "action": self.action,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "remaining": self.remaining,
            "active_quantity": self.active_quantity,
            "status": self.status,
            "parent_id": self.parent_id,
        }


@dataclass(frozen=True)
class ProtectionVerificationResult:
    """Result of checking broker-side protection for one autonomous trade."""

    autonomous_trade_id: str
    symbol: str
    protected: bool
    recovery_required: bool
    reason: str
    expected_quantity: float = 0.0
    stop_order_id: Optional[int] = None
    matched_order: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "autonomous_trade_id": self.autonomous_trade_id,
            "symbol": self.symbol,
            "protected": self.protected,
            "recovery_required": self.recovery_required,
            "reason": self.reason,
            "expected_quantity": self.expected_quantity,
            "stop_order_id": self.stop_order_id,
            "matched_order": self.matched_order,
        }


class ProtectionVerifier:
    """Verify broker-confirmed stop/bracket protection for open trades."""

    def verify_trade(
        self,
        trade: AutonomousTrade,
        *,
        broker_positions: Dict[str, Any],
        open_orders: Iterable[Any],
    ) -> ProtectionVerificationResult:
        symbol = str(trade.symbol or "").strip().upper()
        expected_qty = self._expected_quantity(trade, broker_positions)
        stop_order_id = _as_int(getattr(trade, "stop_order_id", None))
        if expected_qty <= 0:
            return ProtectionVerificationResult(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=symbol,
                protected=True,
                recovery_required=False,
                reason="broker holds no position requiring protection",
                expected_quantity=0.0,
                stop_order_id=stop_order_id,
            )

        snapshots = [BrokerOrderSnapshot.from_raw(order) for order in open_orders]

        if stop_order_id is not None:
            matches = [order for order in snapshots if order.order_id == stop_order_id]
            if not matches:
                return self._missing(
                    trade,
                    expected_qty,
                    stop_order_id,
                    "protective stop order id is not present in broker open orders",
                )
            order = matches[0]
            return self._evaluate_order(trade, order, expected_qty, stop_order_id)

        bracket_like = [
            order for order in snapshots
            if order.symbol.upper() == symbol
            and order.parent_id == _as_int(trade.entry_order_id)
            and order.is_protective_sell_stop
        ]
        if bracket_like:
            return self._evaluate_order(trade, bracket_like[0], expected_qty, None)

        equivalent = [
            order for order in snapshots
            if order.symbol.upper() == symbol and order.is_protective_sell_stop
        ]
        if equivalent:
            return self._evaluate_order(trade, equivalent[0], expected_qty, None)

        return self._missing(
            trade,
            expected_qty,
            None,
            "no broker-visible protective stop/bracket order covers the position",
        )

    def verify_open_trades(
        self,
        trades: Iterable[AutonomousTrade],
        *,
        broker_positions: Dict[str, Any],
        open_orders: Iterable[Any],
    ) -> List[ProtectionVerificationResult]:
        return [
            self.verify_trade(
                trade,
                broker_positions=broker_positions,
                open_orders=open_orders,
            )
            for trade in trades
            if not _is_dry_run_trade(trade)
        ]

    def _evaluate_order(
        self,
        trade: AutonomousTrade,
        order: BrokerOrderSnapshot,
        expected_qty: float,
        stop_order_id: Optional[int],
    ) -> ProtectionVerificationResult:
        if order.symbol.upper() != str(trade.symbol or "").strip().upper():
            return self._missing(
                trade,
                expected_qty,
                stop_order_id,
                "protective order symbol does not match the autonomous trade",
                matched_order=order,
            )
        if not order.is_protective_sell_stop:
            return self._missing(
                trade,
                expected_qty,
                stop_order_id,
                "matching order is not an active SELL stop/bracket order",
                matched_order=order,
            )
        if order.active_quantity < expected_qty:
            return self._missing(
                trade,
                expected_qty,
                stop_order_id,
                "protective stop quantity is below broker-held position quantity",
                matched_order=order,
            )
        return ProtectionVerificationResult(
            autonomous_trade_id=trade.autonomous_trade_id,
            symbol=str(trade.symbol or "").strip().upper(),
            protected=True,
            recovery_required=False,
            reason="broker-visible protective stop/bracket order confirmed",
            expected_quantity=expected_qty,
            stop_order_id=stop_order_id or order.order_id,
            matched_order=order.to_dict(),
        )

    def _missing(
        self,
        trade: AutonomousTrade,
        expected_qty: float,
        stop_order_id: Optional[int],
        reason: str,
        matched_order: Optional[BrokerOrderSnapshot] = None,
    ) -> ProtectionVerificationResult:
        return ProtectionVerificationResult(
            autonomous_trade_id=trade.autonomous_trade_id,
            symbol=str(trade.symbol or "").strip().upper(),
            protected=False,
            recovery_required=True,
            reason=reason,
            expected_quantity=expected_qty,
            stop_order_id=stop_order_id,
            matched_order=matched_order.to_dict() if matched_order else None,
        )

    @staticmethod
    def _expected_quantity(
        trade: AutonomousTrade,
        broker_positions: Dict[str, Any],
    ) -> float:
        symbol = str(trade.symbol or "").strip().upper()
        for raw_symbol, position in (broker_positions or {}).items():
            if str(raw_symbol or "").strip().upper() != symbol:
                continue
            qty = _position_quantity(position)
            if qty != 0:
                return abs(float(qty))
        return abs(float(getattr(trade, "quantity", 0) or 0))


def _position_quantity(position: Any) -> float:
    if position is None:
        return 0.0
    if isinstance(position, dict):
        for key in ("quantity", "position", "shares"):
            if key in position:
                return _as_float(position[key])
        return 0.0
    for key in ("quantity", "position", "shares"):
        value = getattr(position, key, None)
        if value is not None:
            return _as_float(value)
    return 0.0


def _is_dry_run_trade(trade: AutonomousTrade) -> bool:
    return any(str(note).strip().lower() == "dry_run=true" for note in (trade.notes or []))


def _obj_get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, name, default)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    return _as_float(value)
