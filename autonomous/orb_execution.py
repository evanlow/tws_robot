"""ORB paper-autonomous execution with protective orders (Phase 2.5, #209).

This module turns a *valid, recommend-only* :class:`~autonomous.orb_proposals.ORBProposal`
into a **paper** trade — and only ever a paper trade — while preserving the ORB
safety posture. It is the controlled bridge from a recommend-only trade card to a
simulated paper fill, used exclusively when the trader has explicitly enabled
paper-autonomous mode.

Safety posture (Prime Directive):
- Paper only. :class:`ORBPaperExecutor` refuses any mode other than
  ``PAPER_AUTONOMOUS``; there is no code path here that can place, route, or
  simulate a live/real-money order.
- No raw market orders. The entry is always a marketable *limit* order and the
  protective children are *stop* / *limit* orders; a market order can never be
  constructed (the adapter rejects any non-limit/stop order type).
- Stop and target are mandatory. A proposal missing a valid stop or target — or
  one that is not a recommend-only, long-only ``stop < entry < target`` card — is
  rejected before any order is submitted.
- Mandatory broker-visible protection. Bracket submission is preferred whenever
  the adapter supports it. A paper-only ``EXIT_MANAGER_FALLBACK`` is allowed only
  when explicitly configured *and* surfaced in the execution result. Otherwise the
  proposal is rejected as ``MISSING_PROTECTION_REJECTED`` and no entry is placed.
- Long-only, no short selling, no Model C execution.
- Idempotent. Executing the same proposal twice never places duplicate orders;
  the original trade record is returned unchanged.
- Emergency stop and the daily/session cap both block execution.
- Every entry/stop/target order is linked to the ORB strategy, session, setup,
  and proposal ids, and every execution/rejection is written to the autonomous
  audit log so ORB evidence can be reconstructed end to end.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from autonomous.audit import AuditLogger
from autonomous.orb_proposals import (
    ORDER_TYPE_LIMIT,
    ORBProposal,
    ORBProposalStore,
    ProposalError,
    _validate_proposal,
)

logger = logging.getLogger(__name__)

# Audit-log record kind for every ORB paper-execution lifecycle event.
_AUDIT_KIND = "orb_paper_execution"

# Order types this module may ever construct. A raw market order is impossible.
ORDER_TYPE_STOP = "STOP"


class ORBExecutionMode(str, Enum):
    """Execution modes recognised by the ORB paper executor.

    Only ``PAPER_AUTONOMOUS`` can execute. The assisted/live values exist so the
    executor can explicitly *reject* them (missing broker-visible protection is
    never tolerated outside the paper fallback) without ever placing a live
    order — there is no live execution path in this phase.
    """

    PAPER_AUTONOMOUS = "paper_autonomous"
    ASSISTED_LIVE = "assisted_live"
    TINY_LIVE_CANDIDATE = "tiny_live_candidate"


class ORBOrderProtectionStatus(str, Enum):
    """How a paper trade's stop/target protection was established."""

    BRACKET_CONFIRMED = "BRACKET_CONFIRMED"
    EXIT_MANAGER_FALLBACK = "EXIT_MANAGER_FALLBACK"
    MISSING_PROTECTION_REJECTED = "MISSING_PROTECTION_REJECTED"


class ORBOrderRole(str, Enum):
    """Role of an individual order within an ORB paper trade."""

    ENTRY = "ENTRY"
    STOP = "STOP"
    TARGET = "TARGET"


class ORBBlockReason(str, Enum):
    """Why an execution attempt was blocked or rejected."""

    EMERGENCY_STOP = "emergency_stop"
    SESSION_CAP_CONSUMED = "session_cap_consumed"
    MISSING_PROTECTION = "missing_protection"
    NOT_EXECUTABLE = "not_executable"
    UNSUPPORTED_MODE = "unsupported_mode"


class ORBExecutionError(RuntimeError):
    """Raised when an ORB proposal cannot be executed as a paper trade."""


class ORBExecutionBlocked(ORBExecutionError):
    """Raised when a safety gate blocks an otherwise well-formed execution.

    Carries the structured :class:`ORBBlockReason` so callers (API, dashboard)
    can render exactly which gate stopped the trade.
    """

    def __init__(self, reason: ORBBlockReason, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass
class ORBPaperOrder:
    """A single simulated paper order within an ORB bracket/trade.

    ``order_type`` is constrained to ``LIMIT`` or ``STOP`` — never a raw market
    order. ``links`` carries the ORB strategy/session/setup/proposal ids so every
    order is traceable back to its ORB evidence.
    """

    order_id: str
    role: str
    action: str
    order_type: str
    quantity: int
    limit_price: Optional[float]
    stop_price: Optional[float]
    links: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ORBTradeRecord:
    """A simulated paper trade produced from a valid ORB proposal."""

    trade_id: str
    proposal_id: str
    strategy_name: str
    session_date: str
    symbol: str
    entry_model: str
    setup_ref: str
    direction: str
    quantity: int
    entry_price: float
    stop_price: float
    target_price: float
    mode: str
    protection_status: str
    orders: List[ORBPaperOrder]
    created_at: str
    status: str = "SUBMITTED"

    @property
    def entry_order_id(self) -> Optional[str]:
        return self._order_id(ORBOrderRole.ENTRY)

    @property
    def stop_order_id(self) -> Optional[str]:
        return self._order_id(ORBOrderRole.STOP)

    @property
    def target_order_id(self) -> Optional[str]:
        return self._order_id(ORBOrderRole.TARGET)

    def _order_id(self, role: ORBOrderRole) -> Optional[str]:
        for order in self.orders:
            if order.role == role.value:
                return order.order_id
        return None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["orders"] = [o.to_dict() for o in self.orders]
        out["entry_order_id"] = self.entry_order_id
        out["stop_order_id"] = self.stop_order_id
        out["target_order_id"] = self.target_order_id
        return out


def _setup_ref(proposal: ORBProposal) -> str:
    """Stable identifier linking a trade back to its originating ORB setup."""
    evidence = proposal.evidence or {}
    for key in ("setup_id", "setup_ref", "id"):
        val = evidence.get(key)
        if val:
            return str(val)
    return f"{proposal.symbol}:{proposal.session_date}:{proposal.entry_model}"


def _links(proposal: ORBProposal, role: ORBOrderRole) -> Dict[str, Any]:
    """Evidence linkage embedded on every order placed for a proposal."""
    return {
        "strategy_name": proposal.strategy_name,
        "session_date": proposal.session_date,
        "symbol": proposal.symbol,
        "entry_model": proposal.entry_model,
        "proposal_id": proposal.proposal_id,
        "setup_ref": _setup_ref(proposal),
        "role": role.value,
    }


class SimulatedPaperBracketAdapter:
    """Broker-free paper adapter that mints deterministic simulated order ids.

    Supports native bracket submission (entry + protective stop + target) and a
    single-entry path used for the explicitly-configured exit-manager fallback.
    It never constructs a market order: every order is a ``LIMIT`` or ``STOP``
    order, validated here as a last line of defence.
    """

    supports_bracket = True

    def __init__(self, id_prefix: str = "ORB-SIM") -> None:
        self._prefix = id_prefix
        self._seq = 0
        self._lock = threading.Lock()

    def _next_id(self) -> str:
        with self._lock:
            self._seq += 1
            return f"{self._prefix}-{self._seq:06d}-{uuid.uuid4().hex[:8]}"

    def _order(
        self,
        proposal: ORBProposal,
        role: ORBOrderRole,
        action: str,
        order_type: str,
        *,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> ORBPaperOrder:
        if order_type not in (ORDER_TYPE_LIMIT, ORDER_TYPE_STOP):
            raise ORBExecutionError(
                f"refusing to construct a non-limit/stop order ({order_type!r}); "
                "raw market orders are impossible from ORB execution"
            )
        return ORBPaperOrder(
            order_id=self._next_id(),
            role=role.value,
            action=action,
            order_type=order_type,
            quantity=int(proposal.quantity),
            limit_price=limit_price,
            stop_price=stop_price,
            links=_links(proposal, role),
        )

    def submit_bracket(self, proposal: ORBProposal) -> List[ORBPaperOrder]:
        """Submit a long bracket: BUY LIMIT entry + SELL STOP + SELL LIMIT target."""
        return [
            self._order(proposal, ORBOrderRole.ENTRY, "BUY", ORDER_TYPE_LIMIT,
                        limit_price=proposal.entry_price),
            self._order(proposal, ORBOrderRole.STOP, "SELL", ORDER_TYPE_STOP,
                        stop_price=proposal.stop_price),
            self._order(proposal, ORBOrderRole.TARGET, "SELL", ORDER_TYPE_LIMIT,
                        limit_price=proposal.target_price),
        ]

    def submit_entry_managed(self, proposal: ORBProposal) -> List[ORBPaperOrder]:
        """Submit only the marketable-limit entry (exit-manager fallback path)."""
        return [
            self._order(proposal, ORBOrderRole.ENTRY, "BUY", ORDER_TYPE_LIMIT,
                        limit_price=proposal.entry_price),
        ]


class ORBPaperExecutor:
    """Execute valid ORB proposals as paper trades with mandatory protection.

    Thread-safe. Holds an in-memory index of the paper trades it has produced so
    duplicate execution of a proposal is blocked idempotently, and enforces the
    emergency-stop and per-session cap gates. Every execution and rejection is
    written to the autonomous audit log. Never places a live order.
    """

    def __init__(
        self,
        proposal_store: ORBProposalStore,
        *,
        adapter: Optional[SimulatedPaperBracketAdapter] = None,
        audit: Optional[AuditLogger] = None,
        log_dir: str = "logs",
        allow_exit_manager_fallback: bool = False,
        session_cap: int = 1,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._store = proposal_store
        self._adapter = adapter if adapter is not None else SimulatedPaperBracketAdapter()
        self._audit = audit or AuditLogger(str(log_dir))
        self._allow_fallback = bool(allow_exit_manager_fallback)
        self._session_cap = max(1, int(session_cap))
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._trades: Dict[str, ORBTradeRecord] = {}
        self._by_proposal: Dict[str, str] = {}
        self._emergency = False

    # ---- emergency stop ---------------------------------------------
    def trip_emergency_stop(self) -> None:
        """Block all subsequent ORB paper execution until reset."""
        with self._lock:
            self._emergency = True

    def reset_emergency_stop(self) -> None:
        with self._lock:
            self._emergency = False

    @property
    def emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency

    # ---- reads -------------------------------------------------------
    def get_trade(self, trade_id: str) -> Optional[ORBTradeRecord]:
        with self._lock:
            return self._trades.get(trade_id)

    def get_trade_for_proposal(self, proposal_id: str) -> Optional[ORBTradeRecord]:
        with self._lock:
            trade_id = self._by_proposal.get(proposal_id)
            return self._trades.get(trade_id) if trade_id else None

    def list_trades(
        self,
        *,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        session_date: Optional[str] = None,
    ) -> List[ORBTradeRecord]:
        with self._lock:
            items = list(self._trades.values())
        if symbol:
            sym = symbol.upper()
            items = [t for t in items if t.symbol.upper() == sym]
        if strategy_name:
            items = [t for t in items if t.strategy_name == strategy_name]
        if session_date:
            items = [t for t in items if t.session_date == session_date]
        return sorted(items, key=lambda t: t.created_at)

    def session_trade_count(self, strategy_name: str, session_date: str) -> int:
        """Number of paper trades already executed for a strategy's session."""
        with self._lock:
            return sum(
                1 for t in self._trades.values()
                if t.strategy_name == strategy_name and t.session_date == session_date
            )

    # ---- execution ---------------------------------------------------
    def execute_paper(
        self,
        proposal: ORBProposal,
        *,
        mode: ORBExecutionMode = ORBExecutionMode.PAPER_AUTONOMOUS,
        session_cap: Optional[int] = None,
    ) -> ORBTradeRecord:
        """Execute a valid ORB proposal as a single paper trade.

        Returns the resulting :class:`ORBTradeRecord`. Re-executing the same
        proposal is idempotent: the original record is returned and no new orders
        are placed. Raises :class:`ORBExecutionBlocked` when a safety gate stops
        execution and :class:`ORBExecutionError` when the proposal itself is not a
        safe, executable card.
        """
        with self._lock:
            # Idempotency first: never place duplicate orders for a proposal.
            existing = self.get_trade_for_proposal(proposal.proposal_id)
            if existing is not None:
                return existing

            # Paper only. Assisted/live can never execute here, and missing
            # broker-visible protection is never tolerated for those modes.
            if mode != ORBExecutionMode.PAPER_AUTONOMOUS:
                self._log_reject(proposal, ORBBlockReason.UNSUPPORTED_MODE,
                                 ORBOrderProtectionStatus.MISSING_PROTECTION_REJECTED,
                                 mode)
                raise ORBExecutionBlocked(
                    ORBBlockReason.UNSUPPORTED_MODE,
                    f"ORB execution supports paper-autonomous only, not '{mode.value}'",
                )

            # Emergency stop blocks everything.
            if self._emergency:
                self._log_reject(proposal, ORBBlockReason.EMERGENCY_STOP, None, mode)
                raise ORBExecutionBlocked(
                    ORBBlockReason.EMERGENCY_STOP,
                    "emergency stop is active; ORB paper execution is blocked",
                )

            # The proposal must be a safe, recommend-only, long-only,
            # marketable-limit card with stop < entry < target and PENDING
            # status (this rejects skipped/expired/already-executed proposals).
            try:
                _validate_proposal(proposal)
            except ProposalError as exc:
                self._log_reject(proposal, ORBBlockReason.NOT_EXECUTABLE, None, mode)
                raise ORBExecutionError(
                    f"proposal is not executable: {exc}"
                ) from exc
            if int(proposal.quantity) <= 0:
                self._log_reject(proposal, ORBBlockReason.NOT_EXECUTABLE, None, mode)
                raise ORBExecutionError(
                    "proposal has zero quantity; nothing to execute"
                )

            # Daily/session cap blocks execution once consumed.
            cap = self._session_cap if session_cap is None else max(1, int(session_cap))
            consumed = self.session_trade_count(
                proposal.strategy_name, proposal.session_date
            )
            if consumed >= cap:
                self._log_reject(proposal, ORBBlockReason.SESSION_CAP_CONSUMED, None, mode)
                raise ORBExecutionBlocked(
                    ORBBlockReason.SESSION_CAP_CONSUMED,
                    f"session cap of {cap} ORB paper trade(s) already consumed "
                    f"for strategy '{proposal.strategy_name}' on {proposal.session_date}",
                )

            # Establish broker-visible protection. Bracket is preferred; the
            # exit-manager fallback is allowed only when explicitly configured.
            protection, orders = self._protect(proposal, mode)

            trade = ORBTradeRecord(
                trade_id=uuid.uuid4().hex,
                proposal_id=proposal.proposal_id,
                strategy_name=proposal.strategy_name,
                session_date=proposal.session_date,
                symbol=proposal.symbol,
                entry_model=proposal.entry_model,
                setup_ref=_setup_ref(proposal),
                direction=proposal.direction,
                quantity=int(proposal.quantity),
                entry_price=proposal.entry_price,
                stop_price=proposal.stop_price,
                target_price=proposal.target_price,
                mode=mode.value,
                protection_status=protection.value,
                orders=orders,
                created_at=self._now().isoformat(),
            )

            # Mark the proposal EXECUTED in its store (audit-logged there) before
            # indexing the trade so the store stays the source of truth. If the
            # store rejects the transition (e.g. a race), do not place orders.
            try:
                self._store.mark_executed(
                    proposal.proposal_id,
                    trade.trade_id,
                    extra={"protection_status": protection.value},
                )
            except ProposalError as exc:
                self._log_reject(proposal, ORBBlockReason.NOT_EXECUTABLE, None, mode)
                raise ORBExecutionError(
                    f"proposal could not be transitioned to executed: {exc}"
                ) from exc

            self._trades[trade.trade_id] = trade
            self._by_proposal[proposal.proposal_id] = trade.trade_id
            self._log_executed(trade)
            return trade

    # ---- internals ---------------------------------------------------
    def _protect(
        self,
        proposal: ORBProposal,
        mode: ORBExecutionMode,
    ) -> tuple[ORBOrderProtectionStatus, List[ORBPaperOrder]]:
        if getattr(self._adapter, "supports_bracket", False):
            orders = self._adapter.submit_bracket(proposal)
            return ORBOrderProtectionStatus.BRACKET_CONFIRMED, orders

        if self._allow_fallback:
            orders = self._adapter.submit_entry_managed(proposal)
            return ORBOrderProtectionStatus.EXIT_MANAGER_FALLBACK, orders

        # No broker-visible protection and no explicitly-configured fallback:
        # reject without placing any entry order (no naked entries).
        self._log_reject(
            proposal,
            ORBBlockReason.MISSING_PROTECTION,
            ORBOrderProtectionStatus.MISSING_PROTECTION_REJECTED,
            mode,
        )
        raise ORBExecutionBlocked(
            ORBBlockReason.MISSING_PROTECTION,
            "no broker-visible bracket protection is available and the paper "
            "exit-manager fallback is not explicitly enabled",
        )

    def _log_executed(self, trade: ORBTradeRecord) -> None:
        self._audit.log_decision({
            "kind": _AUDIT_KIND,
            "action": "orb_paper_executed",
            "trade_id": trade.trade_id,
            "proposal_id": trade.proposal_id,
            "strategy": trade.strategy_name,
            "session_date": trade.session_date,
            "symbol": trade.symbol,
            "entry_model": trade.entry_model,
            "setup_ref": trade.setup_ref,
            "mode": trade.mode,
            "protection_status": trade.protection_status,
            "quantity": trade.quantity,
            "entry_price": trade.entry_price,
            "stop_price": trade.stop_price,
            "target_price": trade.target_price,
            "entry_order_id": trade.entry_order_id,
            "stop_order_id": trade.stop_order_id,
            "target_order_id": trade.target_order_id,
        })

    def _log_reject(
        self,
        proposal: ORBProposal,
        reason: ORBBlockReason,
        protection: Optional[ORBOrderProtectionStatus],
        mode: ORBExecutionMode,
    ) -> None:
        self._audit.log_decision({
            "kind": _AUDIT_KIND,
            "action": "orb_paper_rejected",
            "proposal_id": proposal.proposal_id,
            "strategy": proposal.strategy_name,
            "session_date": proposal.session_date,
            "symbol": proposal.symbol,
            "mode": mode.value,
            "reason": reason.value,
            "protection_status": protection.value if protection else None,
        })
