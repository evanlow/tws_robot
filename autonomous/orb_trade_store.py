"""ORB Phase 2.6 intraday trade lifecycle store (autonomous/orb_trade_store.py, #210).

Tracks a single paper ORB trade (produced by
:class:`autonomous.orb_execution.ORBPaperExecutor`) through its intraday
lifecycle — from the moment the entry order is submitted through fill,
in-trade monitoring, and exit — and exposes the fields the in-trade
dashboard/API needs.

Safety posture (Prime Directive):
- Paper-only. This module never talks to a broker; it only records state
  transitions that are driven by paper/simulated fills supplied by the caller
  (:mod:`autonomous.orb_exit_manager`).
- Long-only. R-multiple math assumes ``stop < entry < target``.
- Exit quantity can never exceed the trade's original quantity — there is no
  code path here that increases exposure once a trade is open.
- State transitions are idempotent: requesting a second exit for a trade that
  is already ``EXIT_PENDING``/``CLOSED``/``FAILED`` is a no-op rather than a
  duplicate order.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ORBTradeState(str, Enum):
    """Intraday lifecycle states for a single ORB paper trade."""

    ENTRY_PENDING = "ENTRY_PENDING"
    OPEN = "OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


# States from which a trade may still be evaluated / acted on by the operator.
ACTIVE_STATES = (ORBTradeState.ENTRY_PENDING, ORBTradeState.OPEN, ORBTradeState.EXIT_PENDING)


class ORBExitReason(str, Enum):
    """Why an ORB paper trade's exposure was reduced to flat."""

    TARGET = "TARGET"
    STOP = "STOP"
    FORCE_FLAT = "FORCE_FLAT"
    MAX_HOLDING_MINUTES = "MAX_HOLDING_MINUTES"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    ENTRY_CANCELLED = "ENTRY_CANCELLED"
    BROKER_FAILURE = "BROKER_FAILURE"


class ORBTradeStoreError(RuntimeError):
    """Raised on an invalid ORB intraday trade lifecycle transition."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _r_multiple(entry_price: float, stop_price: float, price: Optional[float]) -> Optional[float]:
    """Long-only R-multiple of ``price`` relative to ``entry_price``/``stop_price``."""
    if price is None:
        return None
    risk = entry_price - stop_price
    if risk <= 0:
        return None
    return (price - entry_price) / risk


@dataclass
class ORBIntradayTrade:
    """In-trade monitor record for a single ORB paper trade.

    ``planned_entry_price``/``stop_price``/``target_price`` are the values the
    proposal was executed with (never mutated). ``actual_entry_price`` is the
    simulated fill price once the entry is filled — R-multiples use it when
    available and fall back to the planned entry price beforehand.
    """

    trade_id: str
    proposal_id: str
    strategy_name: str
    session_date: str
    symbol: str
    entry_model: str
    setup_ref: str
    quantity: int
    planned_entry_price: float
    stop_price: float
    target_price: float
    entry_order_id: Optional[str]
    stop_order_id: Optional[str]
    target_order_id: Optional[str]
    protection_status: str
    force_flat_time: str = "15:55"
    max_holding_minutes: Optional[int] = None

    state: str = ORBTradeState.ENTRY_PENDING.value
    entry_order_status: str = "SUBMITTED"
    target_order_status: str = "WORKING"
    stop_order_status: str = "WORKING"

    actual_entry_price: Optional[float] = None
    entry_filled_at: Optional[str] = None
    entry_slippage: Optional[float] = None

    current_price: Optional[float] = None
    current_price_at: Optional[str] = None
    current_r: Optional[float] = None
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None

    exit_order_id: Optional[str] = None
    exit_order_status: Optional[str] = None
    requested_exit_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_slippage: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_r: Optional[float] = None

    failure_note: Optional[str] = None

    created_at: str = field(default_factory=lambda: _iso(_now()))
    closed_at: Optional[str] = None

    @property
    def risk_per_share(self) -> float:
        return self.planned_entry_price - self.stop_price

    @property
    def entry_price_for_r(self) -> float:
        return self.actual_entry_price if self.actual_entry_price is not None else (
            self.planned_entry_price
        )

    def time_in_trade_seconds(self, now: Optional[datetime] = None) -> Optional[float]:
        if not self.entry_filled_at:
            return None
        start = datetime.fromisoformat(self.entry_filled_at)
        end = now or _now()
        return (end - start).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["time_in_trade_seconds"] = self.time_in_trade_seconds()
        out["risk_per_share"] = self.risk_per_share
        return out


class ORBTradeStore:
    """Thread-safe in-memory lifecycle store for ORB intraday paper trades.

    Mirrors the ``ENTRY_PENDING``/``OPEN``/``EXIT_PENDING``/``CLOSED``/``FAILED``
    states used elsewhere in the autonomous trade lifecycle
    (:mod:`autonomous.trade_store`) so the ORB monitor is consistent with the
    rest of the system.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._trades: Dict[str, ORBIntradayTrade] = {}

    # ---- registration --------------------------------------------------
    def register(
        self,
        *,
        trade_id: str,
        proposal_id: str,
        strategy_name: str,
        session_date: str,
        symbol: str,
        entry_model: str,
        setup_ref: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
        entry_order_id: Optional[str],
        stop_order_id: Optional[str],
        target_order_id: Optional[str],
        protection_status: str,
        force_flat_time: str = "15:55",
        max_holding_minutes: Optional[int] = None,
    ) -> ORBIntradayTrade:
        with self._lock:
            if trade_id in self._trades:
                return self._trades[trade_id]
            record = ORBIntradayTrade(
                trade_id=trade_id,
                proposal_id=proposal_id,
                strategy_name=strategy_name,
                session_date=session_date,
                symbol=symbol,
                entry_model=entry_model,
                setup_ref=setup_ref,
                quantity=int(quantity),
                planned_entry_price=float(entry_price),
                stop_price=float(stop_price),
                target_price=float(target_price),
                entry_order_id=entry_order_id,
                stop_order_id=stop_order_id,
                target_order_id=target_order_id,
                protection_status=protection_status,
                force_flat_time=force_flat_time,
                max_holding_minutes=max_holding_minutes,
            )
            self._trades[trade_id] = record
            return record

    # ---- reads -----------------------------------------------------------
    def get(self, trade_id: str) -> Optional[ORBIntradayTrade]:
        with self._lock:
            return self._trades.get(trade_id)

    def list_all(
        self,
        *,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        session_date: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[ORBIntradayTrade]:
        with self._lock:
            items = list(self._trades.values())
        if symbol:
            sym = symbol.upper()
            items = [t for t in items if t.symbol.upper() == sym]
        if strategy_name:
            items = [t for t in items if t.strategy_name == strategy_name]
        if session_date:
            items = [t for t in items if t.session_date == session_date]
        if state:
            items = [t for t in items if t.state == state]
        return sorted(items, key=lambda t: t.created_at)

    def list_open(self) -> List[ORBIntradayTrade]:
        """Trades still eligible for exit-manager evaluation."""
        with self._lock:
            return [t for t in self._trades.values() if t.state == ORBTradeState.OPEN.value]

    def list_active(self) -> List[ORBIntradayTrade]:
        """Trades that have not reached a terminal state."""
        active = {s.value for s in ACTIVE_STATES}
        with self._lock:
            return [t for t in self._trades.values() if t.state in active]

    # ---- entry lifecycle ---------------------------------------------
    def mark_entry_filled(
        self, trade_id: str, fill_price: float, *, filled_at: Optional[datetime] = None,
    ) -> ORBIntradayTrade:
        with self._lock:
            trade = self._require(trade_id)
            if trade.state != ORBTradeState.ENTRY_PENDING.value:
                return trade
            trade.actual_entry_price = float(fill_price)
            trade.entry_slippage = float(fill_price) - trade.planned_entry_price
            trade.entry_filled_at = _iso(filled_at or _now())
            trade.entry_order_status = "FILLED"
            trade.state = ORBTradeState.OPEN.value
            trade.current_r = 0.0
            trade.mfe_r = 0.0
            trade.mae_r = 0.0
            return trade

    def mark_entry_failed(self, trade_id: str, note: str) -> ORBIntradayTrade:
        with self._lock:
            trade = self._require(trade_id)
            if trade.state != ORBTradeState.ENTRY_PENDING.value:
                return trade
            trade.entry_order_status = "FAILED"
            trade.state = ORBTradeState.FAILED.value
            trade.exit_reason = ORBExitReason.BROKER_FAILURE.value
            trade.failure_note = note
            trade.closed_at = _iso(_now())
            return trade

    def cancel_entry(self, trade_id: str) -> ORBIntradayTrade:
        """Cancel a not-yet-filled entry order. Never opens/increases exposure."""
        with self._lock:
            trade = self._require(trade_id)
            if trade.state != ORBTradeState.ENTRY_PENDING.value:
                raise ORBTradeStoreError(
                    f"trade {trade_id} is '{trade.state}'; entry can only be "
                    "cancelled while ENTRY_PENDING"
                )
            trade.entry_order_status = "CANCELLED"
            trade.target_order_status = "CANCELLED"
            trade.stop_order_status = "CANCELLED"
            trade.state = ORBTradeState.CLOSED.value
            trade.exit_reason = ORBExitReason.ENTRY_CANCELLED.value
            trade.closed_at = _iso(_now())
            return trade

    # ---- in-trade monitoring -------------------------------------------
    def update_price(
        self, trade_id: str, price: float, *, now: Optional[datetime] = None,
    ) -> ORBIntradayTrade:
        with self._lock:
            trade = self._require(trade_id)
            if trade.state != ORBTradeState.OPEN.value:
                return trade
            trade.current_price = float(price)
            trade.current_price_at = _iso(now or _now())
            r = _r_multiple(trade.entry_price_for_r, trade.stop_price, price)
            trade.current_r = r
            if r is not None:
                trade.mfe_r = r if trade.mfe_r is None else max(trade.mfe_r, r)
                trade.mae_r = r if trade.mae_r is None else min(trade.mae_r, r)
            return trade

    # ---- exit lifecycle --------------------------------------------------
    def request_exit(
        self,
        trade_id: str,
        reason: ORBExitReason,
        *,
        requested_price: Optional[float],
        exit_order_id: str,
    ) -> Optional[ORBIntradayTrade]:
        """Transition ``OPEN`` -> ``EXIT_PENDING``.

        Returns ``None`` (no-op) if the trade is not currently ``OPEN`` — this
        is what makes duplicate-exit requests and oversell/over-close attempts
        safe: a second call for a trade already ``EXIT_PENDING``/``CLOSED``/
        ``FAILED`` never mints a second reducing order.
        """
        with self._lock:
            trade = self._require(trade_id)
            if trade.state != ORBTradeState.OPEN.value:
                return None
            trade.state = ORBTradeState.EXIT_PENDING.value
            trade.exit_reason = reason.value
            trade.requested_exit_price = requested_price
            trade.exit_order_id = exit_order_id
            trade.exit_order_status = "SUBMITTED"
            trade.target_order_status = "CANCELLED"
            trade.stop_order_status = "CANCELLED"
            return trade

    def mark_exit_filled(
        self, trade_id: str, fill_price: float, *, filled_at: Optional[datetime] = None,
    ) -> ORBIntradayTrade:
        with self._lock:
            trade = self._require(trade_id)
            if trade.state != ORBTradeState.EXIT_PENDING.value:
                return trade
            trade.exit_price = float(fill_price)
            if trade.requested_exit_price is not None:
                trade.exit_slippage = float(fill_price) - trade.requested_exit_price
            trade.realized_r = _r_multiple(
                trade.entry_price_for_r, trade.stop_price, fill_price
            )
            trade.exit_order_status = "FILLED"
            trade.state = ORBTradeState.CLOSED.value
            trade.closed_at = _iso(filled_at or _now())
            return trade

    def mark_exit_failed(
        self,
        trade_id: str,
        note: str,
        *,
        reason: Optional[ORBExitReason] = None,
    ) -> ORBIntradayTrade:
        """A broker/order failure while trying to reduce exposure.

        The trade is marked ``FAILED`` (never left silently ``OPEN``) so an
        explicit failure record always exists; it is never re-opened or
        re-sized upward from here. ``reason`` (e.g. ``FORCE_FLAT`` or
        ``EMERGENCY_STOP``) is preserved on ``exit_reason`` so evidence/session
        review can query *why* the mandatory flatten attempt failed, even
        though no exit was actually filled.
        """
        with self._lock:
            trade = self._require(trade_id)
            if trade.state not in (ORBTradeState.OPEN.value, ORBTradeState.EXIT_PENDING.value):
                return trade
            trade.exit_order_status = "FAILED"
            trade.state = ORBTradeState.FAILED.value
            if reason is not None:
                trade.exit_reason = reason.value
            trade.failure_note = note
            trade.closed_at = _iso(_now())
            return trade

    # ---- internals ---------------------------------------------------
    def _require(self, trade_id: str) -> ORBIntradayTrade:
        trade = self._trades.get(trade_id)
        if trade is None:
            raise ORBTradeStoreError(f"unknown ORB trade '{trade_id}'")
        return trade
