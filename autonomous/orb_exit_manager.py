"""ORB Phase 2.6 intraday exit lifecycle and in-trade monitor (autonomous/orb_exit_manager.py, #210).

Once :class:`autonomous.orb_execution.ORBPaperExecutor` has submitted the
paper entry/protective orders for a valid ORB proposal, this module owns what
happens next: registering the trade for in-trade monitoring, simulating
entry/exit fills from a live price feed, and deciding when a trade must be
flattened.

ORB is a scalping strategy and does not rely on the existing multi-day
autonomous exit manager (:mod:`autonomous.exit_manager`); it needs its own
target/stop/force-flat/max-holding lifecycle plus explicit operator controls.

Exit triggers (highest priority first):

1. Emergency stop — flattens every open ORB trade immediately.
2. Manual close — operator-initiated ``close_now``.
3. Take-profit — last price >= ``target_price``.
4. Stop-loss — last price <= ``stop_price``.
5. Force-flat time — the strategy's configured flat time has passed.
6. Max holding minutes — optional per-trade holding-time cap.

Safety posture (Prime Directive):
- Paper-only; no broker/live order is ever placed here.
- Force-close can only *reduce* exposure. Every exit request submits a SELL
  sized to the trade's original (never increased) quantity, and the trade
  store makes duplicate exit requests a no-op — a trade can be flattened only
  once.
- If a trade must be flattened (force-flat, emergency stop, max holding) but
  no live price is available, we never guess: the trade is marked ``FAILED``
  with an explicit broker/order-failure note rather than silently remaining
  ``OPEN`` past its safety boundary.
- Every exit decision, fill, and failure is written to the autonomous audit
  log so ORB evidence can be reconstructed end to end.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dt_time, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from autonomous.audit import AuditLogger
from autonomous.orb_trade_store import (
    ORBExitReason,
    ORBIntradayTrade,
    ORBTradeState,
    ORBTradeStore,
    ORBTradeStoreError,
)

logger = logging.getLogger(__name__)

_AUDIT_KIND = "orb_intraday_exit"

PriceProvider = Callable[[str], Optional[float]]


class ORBExitManagerError(RuntimeError):
    """Raised when an operator action cannot be performed on an ORB trade."""


@dataclass
class ORBExitDecision:
    """Result of evaluating a single ORB trade for an exit trigger."""

    trade_id: str
    symbol: str
    decision: str  # one of ORBExitReason values, "NO_EXIT", or "NO_PRICE_AVAILABLE"
    reason: str
    price: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _force_flat_datetime(trade: ORBIntradayTrade, tz_name: str = "America/New_York") -> Optional[datetime]:
    """The force-flat instant (timezone-aware) for a trade's session date."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):  # pragma: no cover - defensive
        tz = ZoneInfo("America/New_York")
    try:
        session_date = datetime.strptime(trade.session_date, "%Y-%m-%d").date()
        hh, mm = (int(p) for p in trade.force_flat_time.split(":"))
    except (ValueError, AttributeError):  # pragma: no cover - defensive
        return None
    return datetime.combine(session_date, dt_time(hh, mm), tzinfo=tz)


class ORBExitManager:
    """Intraday exit lifecycle manager for paper ORB trades.

    Thread-safe. Holds no broker connection; all fills are simulated from the
    supplied ``price_provider``. Registers trades from
    :class:`autonomous.orb_execution.ORBTradeRecord`, tracks in-trade monitor
    state via :class:`autonomous.orb_trade_store.ORBTradeStore`, and evaluates
    open trades for exit triggers.
    """

    def __init__(
        self,
        store: Optional[ORBTradeStore] = None,
        *,
        price_provider: Optional[PriceProvider] = None,
        audit: Optional[AuditLogger] = None,
        log_dir: str = "logs",
        now_fn: Optional[Callable[[], datetime]] = None,
        id_prefix: str = "ORB-EXIT",
    ) -> None:
        self._store = store or ORBTradeStore()
        self._price_provider = price_provider or (lambda symbol: None)
        self._audit = audit or AuditLogger(str(log_dir))
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._prefix = id_prefix
        self._seq = 0
        self._lock = threading.RLock()
        self._emergency = False
        self._new_entries_disabled: Set[str] = set()

    @property
    def store(self) -> ORBTradeStore:
        return self._store

    # ---- emergency stop --------------------------------------------------
    def trip_emergency_stop(self) -> None:
        with self._lock:
            self._emergency = True

    def reset_emergency_stop(self) -> None:
        with self._lock:
            self._emergency = False

    @property
    def emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency

    # ---- new-entries gate (operator action) ------------------------------
    def disable_new_entries(self, strategy_name: str) -> None:
        """Block further paper *entries* for a strategy without touching any
        already-open trade's exit management."""
        with self._lock:
            self._new_entries_disabled.add(strategy_name)
        self._audit.log_decision({
            "kind": _AUDIT_KIND,
            "action": "disable_new_entries",
            "strategy": strategy_name,
        })

    def enable_new_entries(self, strategy_name: str) -> None:
        with self._lock:
            self._new_entries_disabled.discard(strategy_name)
        self._audit.log_decision({
            "kind": _AUDIT_KIND,
            "action": "enable_new_entries",
            "strategy": strategy_name,
        })

    def new_entries_disabled(self, strategy_name: str) -> bool:
        with self._lock:
            return strategy_name in self._new_entries_disabled

    # ---- registration ------------------------------------------------
    def register_trade(
        self,
        trade,
        *,
        force_flat_time: str = "15:55",
        max_holding_minutes: Optional[int] = None,
    ) -> ORBIntradayTrade:
        """Register an executed :class:`ORBTradeRecord` for intraday monitoring."""
        return self._store.register(
            trade_id=trade.trade_id,
            proposal_id=trade.proposal_id,
            strategy_name=trade.strategy_name,
            session_date=trade.session_date,
            symbol=trade.symbol,
            entry_model=trade.entry_model,
            setup_ref=trade.setup_ref,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            entry_order_id=trade.entry_order_id,
            stop_order_id=trade.stop_order_id,
            target_order_id=trade.target_order_id,
            protection_status=trade.protection_status,
            force_flat_time=force_flat_time,
            max_holding_minutes=max_holding_minutes,
        )

    # ---- entry fill simulation ----------------------------------------
    def mark_entry_filled(self, trade_id: str, fill_price: float) -> ORBIntradayTrade:
        trade = self._store.mark_entry_filled(trade_id, fill_price, filled_at=self._now())
        self._audit.log_decision({
            "kind": _AUDIT_KIND, "action": "entry_filled", "trade_id": trade_id,
            "fill_price": fill_price, "entry_slippage": trade.entry_slippage,
        })
        return trade

    def mark_entry_failed(self, trade_id: str, note: str) -> ORBIntradayTrade:
        trade = self._store.mark_entry_failed(trade_id, note)
        self._audit.log_decision({
            "kind": _AUDIT_KIND, "action": "entry_failed", "trade_id": trade_id, "note": note,
        })
        return trade

    # ---- reads ---------------------------------------------------------
    def get_trade(self, trade_id: str) -> Optional[ORBIntradayTrade]:
        return self._store.get(trade_id)

    def list_trades(self, **kwargs) -> List[ORBIntradayTrade]:
        return self._store.list_all(**kwargs)

    def force_flat_countdown_seconds(
        self, trade: ORBIntradayTrade, *, now: Optional[datetime] = None,
    ) -> Optional[float]:
        """Seconds remaining until this trade's force-flat time (negative if past)."""
        target = _force_flat_datetime(trade)
        if target is None:
            return None
        return (target - (now or self._now())).total_seconds()

    # ---- evaluation loop -------------------------------------------------
    def evaluate_all(self) -> List[ORBExitDecision]:
        """Evaluate every currently-``OPEN`` trade for an exit trigger."""
        return [self._evaluate_one(t) for t in self._store.list_open()]

    def evaluate_trade(self, trade_id: str) -> Optional[ORBExitDecision]:
        trade = self._store.get(trade_id)
        if trade is None or trade.state != ORBTradeState.OPEN.value:
            return None
        return self._evaluate_one(trade)

    def _evaluate_one(self, trade: ORBIntradayTrade) -> ORBExitDecision:
        now = self._now()
        price = self._safe_price(trade.symbol)
        if price is not None:
            self._store.update_price(trade.trade_id, price, now=now)

        # 1. Emergency stop takes precedence over everything else.
        if self.emergency_stopped:
            return self._trigger_exit(trade, ORBExitReason.EMERGENCY_STOP, price, now)

        # 2. Take-profit / stop-loss.
        if price is not None:
            if price >= trade.target_price:
                return self._trigger_exit(trade, ORBExitReason.TARGET, trade.target_price, now)
            if price <= trade.stop_price:
                return self._trigger_exit(trade, ORBExitReason.STOP, trade.stop_price, now)

        # 3. Force-flat time.
        flat_at = _force_flat_datetime(trade)
        if flat_at is not None and now >= flat_at:
            return self._trigger_exit(trade, ORBExitReason.FORCE_FLAT, price, now)

        # 4. Max holding minutes (optional).
        if trade.max_holding_minutes:
            elapsed = trade.time_in_trade_seconds(now)
            if elapsed is not None and elapsed >= trade.max_holding_minutes * 60:
                return self._trigger_exit(trade, ORBExitReason.MAX_HOLDING_MINUTES, price, now)

        if price is None:
            return ORBExitDecision(
                trade_id=trade.trade_id, symbol=trade.symbol,
                decision="NO_PRICE_AVAILABLE", reason="no live price available for symbol",
            )
        return ORBExitDecision(
            trade_id=trade.trade_id, symbol=trade.symbol,
            decision="NO_EXIT", reason="no exit trigger met", price=price,
        )

    # ---- operator actions ------------------------------------------------
    def close_now(self, trade_id: str) -> ORBExitDecision:
        """Operator-initiated immediate close. Only ever reduces exposure."""
        trade = self._store.get(trade_id)
        if trade is None:
            raise ORBExitManagerError(f"unknown ORB trade '{trade_id}'")
        if trade.state != ORBTradeState.OPEN.value:
            raise ORBExitManagerError(
                f"trade {trade_id} is '{trade.state}'; close-now requires OPEN"
            )
        price = self._safe_price(trade.symbol)
        if price is None:
            self._audit.log_decision({
                "kind": _AUDIT_KIND, "action": "close_now_no_price",
                "trade_id": trade_id, "symbol": trade.symbol,
                "decision": "NO_PRICE_AVAILABLE",
            })
            return ORBExitDecision(
                trade_id=trade_id, symbol=trade.symbol,
                decision="NO_PRICE_AVAILABLE",
                reason="manual close requested but no live price available; trade remains OPEN for retry",
            )
        return self._trigger_exit(trade, ORBExitReason.MANUAL_CLOSE, price, self._now())

    def cancel_entry(self, trade_id: str) -> ORBIntradayTrade:
        """Cancel a not-yet-filled entry. Never opens/increases exposure."""
        try:
            trade = self._store.cancel_entry(trade_id)
        except ORBTradeStoreError as exc:
            raise ORBExitManagerError(str(exc)) from exc
        self._audit.log_decision({
            "kind": _AUDIT_KIND, "action": "cancel_entry", "trade_id": trade_id,
        })
        return trade

    # ---- internals ---------------------------------------------------
    def _safe_price(self, symbol: str) -> Optional[float]:
        try:
            price = self._price_provider(symbol)
        except Exception:  # pragma: no cover - defensive
            logger.exception("ORB exit manager: price provider raised for %s", symbol)
            return None
        return float(price) if price is not None else None

    def _next_exit_order_id(self) -> str:
        with self._lock:
            self._seq += 1
            return f"{self._prefix}-{self._seq:06d}-{uuid.uuid4().hex[:8]}"

    def _trigger_exit(
        self,
        trade: ORBIntradayTrade,
        reason: ORBExitReason,
        price: Optional[float],
        now: datetime,
    ) -> ORBExitDecision:
        if price is None:
            # Never guess an exit price and never leave the trade silently
            # OPEN past a mandatory flatten boundary: record an explicit
            # broker/order-failure instead.
            self._store.mark_exit_failed(
                trade.trade_id,
                f"{reason.value}: no live price available to flatten position",
                reason=reason,
            )
            self._audit.log_decision({
                "kind": _AUDIT_KIND, "action": "exit_failed_no_price",
                "trade_id": trade.trade_id, "symbol": trade.symbol,
                "would_exit_reason": reason.value,
            })
            return ORBExitDecision(
                trade_id=trade.trade_id, symbol=trade.symbol,
                decision="NO_PRICE_AVAILABLE",
                reason=f"cannot flatten for {reason.value}: no live price available",
                notes=[f"would_exit:{reason.value}"],
            )

        exit_order_id = self._next_exit_order_id()
        pending = self._store.request_exit(
            trade.trade_id, reason, requested_price=price, exit_order_id=exit_order_id,
        )
        if pending is None:
            # Trade is no longer OPEN (already exiting/closed/failed) — this is
            # what makes duplicate-exit and oversell/over-close attempts a
            # no-op instead of a second reducing order.
            current = self._store.get(trade.trade_id)
            return ORBExitDecision(
                trade_id=trade.trade_id, symbol=trade.symbol,
                decision="NO_EXIT",
                reason="trade is no longer open; exit already in progress or complete",
                notes=[f"state:{current.state if current else 'unknown'}"],
            )

        self._audit.log_decision({
            "kind": _AUDIT_KIND, "action": "exit_requested", "trade_id": trade.trade_id,
            "symbol": trade.symbol, "reason": reason.value, "requested_price": price,
            "exit_order_id": exit_order_id, "quantity": trade.quantity,
        })

        # Paper fill simulation: the exit is filled immediately at the
        # requested price (target/stop/flat/manual level). This never places
        # a broker order and the fill quantity is always the trade's original
        # (never increased) quantity.
        closed = self._store.mark_exit_filled(trade.trade_id, price, filled_at=now)
        self._audit.log_decision({
            "kind": _AUDIT_KIND, "action": "exit_filled", "trade_id": trade.trade_id,
            "symbol": trade.symbol, "reason": reason.value, "fill_price": price,
            "realized_r": closed.realized_r, "exit_slippage": closed.exit_slippage,
            # MFE/MAE are only ever tracked in-memory on the intraday trade
            # record; persist them here so end-of-session evidence review
            # (#211) can reconstruct them after a process restart.
            "mfe_r": closed.mfe_r, "mae_r": closed.mae_r,
        })
        return ORBExitDecision(
            trade_id=trade.trade_id, symbol=trade.symbol,
            decision=reason.value, reason=f"exit triggered by {reason.value}", price=price,
        )
