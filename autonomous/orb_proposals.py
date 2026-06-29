"""ORB recommend-only trade proposals and setup audit trail (Phase 2.4, #208).

This module turns a deterministic, broker-free :class:`~autonomous.opening_range.ORBSetup`
into a transparent *recommend-only* trade proposal: a structured "trade card"
that shows exactly what ORB would do **before** any order is placed. It is the
safe bridge from runtime signal detection to a later paper-autonomous execution
phase.

Safety posture (Prime Directive):
- Nothing here places, routes, or simulates an order. Proposals are
  recommend-only descriptions; paper/live execution is a separate later phase.
- A proposal can never exist without both a stop and a target price, and never
  represents a raw market order — the entry is always a marketable *limit*
  price carried over from the ORB setup.
- Long-only for the MVP; short-side proposals are rejected.
- Every proposal creation, skip, and expiry is written to the autonomous audit
  log so a trader can always explain why ORB did (or did not) trade.

The :class:`ORBProposalStore` keeps proposals in memory for the dashboard/API
and audit-logs every lifecycle event. Proposals expire after the entry cutoff,
on setup invalidation, on stale/degraded data, or once the session cap has been
consumed.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from autonomous.audit import AuditLogger
from autonomous.opening_range import ORBDirection, ORBSetup

logger = logging.getLogger(__name__)

# Audit-log record kind for every ORB proposal lifecycle event.
_AUDIT_KIND = "orb_proposal"

# The entry is always a marketable limit price inherited from the ORB setup.
# Proposals must never represent a raw market order (Prime Directive).
ORDER_TYPE_LIMIT = "LIMIT"


class ProposalStatus(str, Enum):
    """Lifecycle status of a recommend-only ORB proposal."""

    PENDING = "PENDING"
    SKIPPED = "SKIPPED"
    EXPIRED = "EXPIRED"
    # EXECUTED is reserved for the later paper-execution phase; this phase never
    # transitions a proposal to EXECUTED.
    EXECUTED = "EXECUTED"


class ExpiryReason(str, Enum):
    """Why a proposal expired without being acted on."""

    ENTRY_CUTOFF = "entry_cutoff"
    INVALIDATION = "invalidation"
    STALE_DATA = "stale_data"
    SESSION_CAP_CONSUMED = "session_cap_consumed"
    MANUAL = "manual"


class ProposalError(ValueError):
    """Raised when a proposal cannot be created or transitioned safely."""


class ProposalNotFoundError(ProposalError):
    """Raised when a referenced proposal id does not exist in the store."""


# Gate names that must pass for a proposal to be considered executable later.
# ``spread_acceptable`` is intentionally excluded because it is only meaningful
# when live quote data is available (it may be ``None``).
_REQUIRED_GATES = (
    "opening_range_valid",
    "breakout_5m_confirmed",
    "model_1m_detected",
    "market_data_healthy",
    "risk_manager_approved",
    "stop_present",
    "target_present",
    "session_cap_available",
    "no_existing_open_orb_trade",
    "emergency_stop_inactive",
)


@dataclass
class ProposalGates:
    """Transparent pass/fail gate results shown on a proposal card.

    ``spread_acceptable`` is ``None`` when no live quote data is available, in
    which case it does not count against the proposal's readiness.
    """

    opening_range_valid: bool = False
    breakout_5m_confirmed: bool = False
    model_1m_detected: bool = False
    market_data_healthy: bool = False
    spread_acceptable: Optional[bool] = None
    risk_manager_approved: bool = False
    stop_present: bool = False
    target_present: bool = False
    session_cap_available: bool = False
    no_existing_open_orb_trade: bool = False
    emergency_stop_inactive: bool = False

    def failing(self) -> List[str]:
        """Return the names of required gates that are not satisfied."""
        out = [name for name in _REQUIRED_GATES if not getattr(self, name)]
        # Spread is only a blocker when quote data exists and is unacceptable.
        if self.spread_acceptable is False:
            out.append("spread_acceptable")
        return out

    def all_pass(self) -> bool:
        """True when every required gate passes (spread optional)."""
        return not self.failing()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _candle_meta(setup: ORBSetup) -> Dict[str, Any]:
    """Confirmation 5m candle metadata for the proposal card."""
    conf = setup.confirmation
    c5 = conf.candle_5m
    return {
        "direction": conf.direction.value,
        "confirmed_at": conf.confirmed_at.isoformat(),
        "range_high": conf.range_high,
        "range_low": conf.range_low,
        "open": c5.open,
        "high": c5.high,
        "low": c5.low,
        "close": c5.close,
        "volume": c5.volume,
        "start": c5.start.isoformat(),
        "end": c5.end.isoformat(),
    }


def size_quantity(equity: float, risk_per_trade_equity_pct: float,
                  risk_per_share: float) -> int:
    """Whole-share quantity so that worst-case loss stays within risk budget.

    Returns ``0`` when inputs are non-positive (a zero-quantity proposal is
    still valid as a recommend-only card; it simply means the configured risk
    budget cannot fund even one share).
    """
    if risk_per_share <= 0 or equity <= 0 or risk_per_trade_equity_pct <= 0:
        return 0
    budget = equity * risk_per_trade_equity_pct
    return int(budget // risk_per_share)


@dataclass
class ORBProposal:
    """A structured, recommend-only ORB trade card.

    Carries everything a trader needs to understand the setup before any order
    exists: entry/stop/target, sizing, R/R, the opening range, confirmation
    candle metadata, setup evidence, and transparent gate results. The entry is
    always a marketable limit price (``order_type == LIMIT``); a proposal never
    represents a raw market order and can never exist without a stop and target.
    """

    proposal_id: str
    strategy_name: str
    symbol: str
    session_date: str
    orb_state: str
    entry_model: str
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_share: float
    reward_per_share: float
    rr_ratio: float
    quantity: int
    risk_dollars: float
    position_value: float
    range_high: float
    range_low: float
    range_width_pct: float
    confirmation_candle: Dict[str, Any]
    evidence: Dict[str, Any]
    gates: ProposalGates
    created_at: str
    expires_at: Optional[str] = None
    order_type: str = ORDER_TYPE_LIMIT
    recommend_only: bool = True
    status: str = ProposalStatus.PENDING.value
    expiry_reason: Optional[str] = None
    skip_reason: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["gates"] = self.gates.to_dict()
        out["gates_passing"] = self.gates.all_pass()
        out["gates_failing"] = self.gates.failing()
        return out

    @property
    def is_open(self) -> bool:
        """True while the proposal is still pending (not skipped/expired)."""
        return self.status == ProposalStatus.PENDING.value


def build_proposal(
    setup: ORBSetup,
    *,
    strategy_name: str,
    session_date: str,
    orb_state: str,
    gates: ProposalGates,
    equity: float = 100_000.0,
    risk_per_trade_equity_pct: float = 0.002,
    expires_at: Optional[str] = None,
    proposal_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> ORBProposal:
    """Build an :class:`ORBProposal` from an ORB setup (recommend-only).

    Raises :class:`ProposalError` when the setup is unsafe to propose: missing
    stop/target, a non-long direction, or a stop that is not below the entry.
    """
    if setup.direction != ORBDirection.LONG:
        raise ProposalError("only long-side ORB proposals are supported")
    if setup.stop_price is None or setup.stop_price <= 0:
        raise ProposalError("proposal requires a positive stop price")
    if setup.target_price is None or setup.target_price <= 0:
        raise ProposalError("proposal requires a positive target price")
    if setup.entry_price is None or setup.entry_price <= 0:
        raise ProposalError("proposal requires a positive entry price")
    # Long-only invariant: stop below entry below target.
    if not (setup.stop_price < setup.entry_price < setup.target_price):
        raise ProposalError(
            "proposal requires stop < entry < target for a long setup"
        )

    qty = size_quantity(equity, risk_per_trade_equity_pct, setup.risk_per_share)
    risk_dollars = round(qty * setup.risk_per_share, 2)
    position_value = round(qty * setup.entry_price, 2)
    rng = setup.opening_range

    # Gate flags that are intrinsic to the setup are always truthful here so the
    # card never claims a stop/target/model it does not have.
    gates.stop_present = True
    gates.target_present = True
    gates.model_1m_detected = True
    gates.breakout_5m_confirmed = True
    gates.opening_range_valid = True

    return ORBProposal(
        proposal_id=proposal_id or uuid.uuid4().hex,
        strategy_name=strategy_name,
        symbol=setup.symbol,
        session_date=session_date,
        orb_state=orb_state,
        entry_model=setup.model.value,
        direction=setup.direction.value,
        entry_price=setup.entry_price,
        stop_price=setup.stop_price,
        target_price=setup.target_price,
        risk_per_share=setup.risk_per_share,
        reward_per_share=setup.reward_per_share,
        rr_ratio=setup.rr_ratio,
        quantity=qty,
        risk_dollars=risk_dollars,
        position_value=position_value,
        range_high=rng.high,
        range_low=rng.low,
        range_width_pct=rng.width_pct,
        confirmation_candle=_candle_meta(setup),
        evidence=dict(setup.evidence),
        gates=gates,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
        reason=(
            f"ORB {setup.model.value} long: entry {setup.entry_price} "
            f"stop {setup.stop_price} target {setup.target_price} "
            f"range[{rng.low},{rng.high}]"
        ),
    )


def _validate_proposal(proposal: ORBProposal) -> None:
    """Re-validate a pre-built proposal's safety invariants before storing.

    Mirrors the guarantees of :func:`build_proposal` so that a proposal can
    never be stored or audit-logged unless it is a recommend-only, long-only,
    marketable-limit card with a valid ``stop < entry < target`` relationship
    and consistent stop/target gates. Raises :class:`ProposalError` otherwise.
    """
    if proposal.recommend_only is not True:
        raise ProposalError("proposal must be recommend-only")
    if proposal.order_type != ORDER_TYPE_LIMIT:
        raise ProposalError(
            f"proposal order_type must be {ORDER_TYPE_LIMIT}, "
            f"not a raw market order"
        )
    if proposal.direction != ORBDirection.LONG.value:
        raise ProposalError("only long-side ORB proposals are supported")
    if proposal.status != ProposalStatus.PENDING.value:
        raise ProposalError(
            f"a newly added proposal must be PENDING, not '{proposal.status}'"
        )
    if not (proposal.stop_price > 0):
        raise ProposalError("proposal requires a positive stop price")
    if not (proposal.entry_price > 0):
        raise ProposalError("proposal requires a positive entry price")
    if not (proposal.target_price > 0):
        raise ProposalError("proposal requires a positive target price")
    if not (proposal.stop_price < proposal.entry_price < proposal.target_price):
        raise ProposalError(
            "proposal requires stop < entry < target for a long setup"
        )
    # The stop/target gates must not claim a price the proposal does not carry.
    if proposal.gates.stop_present and not (proposal.stop_price > 0):
        raise ProposalError("stop_present gate set without a valid stop price")
    if proposal.gates.target_present and not (proposal.target_price > 0):
        raise ProposalError(
            "target_present gate set without a valid target price"
        )


class ORBProposalStore:
    """In-memory store of recommend-only ORB proposals with an audit trail.

    Thread-safe. Every create/skip/expire is written to the autonomous audit
    log so the dashboard/API and external tooling can reconstruct exactly why
    ORB did or did not trade. No orders are ever placed.
    """

    def __init__(
        self,
        audit: Optional[AuditLogger] = None,
        log_dir: str = "logs",
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._audit = audit or AuditLogger(str(log_dir))
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._proposals: Dict[str, ORBProposal] = {}

    # ---- creation ----------------------------------------------------
    def create_from_setup(self, setup: ORBSetup, **kwargs: Any) -> ORBProposal:
        """Create and store a recommend-only proposal from an ORB setup."""
        proposal = build_proposal(setup, **kwargs)
        with self._lock:
            self._proposals[proposal.proposal_id] = proposal
        self._log("proposal_created", proposal, {})
        return proposal

    def add(self, proposal: ORBProposal) -> ORBProposal:
        """Store a pre-built proposal and audit-log its creation.

        Re-validates the proposal's safety invariants before storing so that
        integration code can never inject an unsafe card (raw market order,
        non-recommend-only, short direction, missing/invalid stop/target, or a
        non-pending status) into the store or audit trail.
        """
        _validate_proposal(proposal)
        with self._lock:
            self._proposals[proposal.proposal_id] = proposal
        self._log("proposal_created", proposal, {})
        return proposal

    # ---- reads -------------------------------------------------------
    def get(self, proposal_id: str) -> Optional[ORBProposal]:
        with self._lock:
            return self._proposals.get(proposal_id)

    def list(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
    ) -> List[ORBProposal]:
        with self._lock:
            items = list(self._proposals.values())
        if status:
            items = [p for p in items if p.status == status]
        if symbol:
            sym = symbol.upper()
            items = [p for p in items if p.symbol.upper() == sym]
        if strategy_name:
            items = [p for p in items if p.strategy_name == strategy_name]
        return sorted(items, key=lambda p: p.created_at)

    # ---- transitions -------------------------------------------------
    def skip(self, proposal_id: str, reason: Optional[str] = None) -> ORBProposal:
        """Trader-initiated skip with an optional reason. Idempotent on skip."""
        with self._lock:
            proposal = self._require(proposal_id)
            if proposal.status not in (
                ProposalStatus.PENDING.value,
                ProposalStatus.SKIPPED.value,
            ):
                raise ProposalError(
                    f"cannot skip a proposal in status '{proposal.status}'"
                )
            first_transition = proposal.status != ProposalStatus.SKIPPED.value
            proposal.status = ProposalStatus.SKIPPED.value
            proposal.skip_reason = reason or ""
            if first_transition:
                self._log("proposal_skipped", proposal, {"reason": proposal.skip_reason})
        return proposal

    def mark_executed(
        self,
        proposal_id: str,
        trade_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ORBProposal:
        """Transition a pending proposal to EXECUTED once a paper trade exists.

        Only a ``PENDING`` proposal may be executed; a skipped or expired
        proposal can never be turned into a trade, and an already-executed
        proposal cannot be executed again (idempotency is enforced by the
        executor, but this guard keeps the store and audit trail honest).
        The ``trade_id`` linking the proposal to its paper trade is recorded in
        the audit log so ORB evidence can be reconstructed end to end.
        """
        with self._lock:
            proposal = self._require(proposal_id)
            if proposal.status != ProposalStatus.PENDING.value:
                raise ProposalError(
                    f"cannot execute a proposal in status '{proposal.status}'"
                )
            proposal.status = ProposalStatus.EXECUTED.value
        self._log(
            "proposal_executed",
            proposal,
            {"trade_id": trade_id, **(extra or {})},
        )
        return proposal

    def expire(
        self,
        proposal_id: str,
        reason: ExpiryReason = ExpiryReason.MANUAL,
    ) -> ORBProposal:
        """Expire a pending proposal (cutoff, invalidation, stale data, cap)."""
        reason_val = reason.value if isinstance(reason, ExpiryReason) else str(reason)
        with self._lock:
            proposal = self._require(proposal_id)
            if proposal.status not in (
                ProposalStatus.PENDING.value,
                ProposalStatus.EXPIRED.value,
            ):
                raise ProposalError(
                    f"cannot expire a proposal in status '{proposal.status}'"
                )
            proposal.status = ProposalStatus.EXPIRED.value
            proposal.expiry_reason = reason_val
        self._log("proposal_expired", proposal, {"reason": reason_val})
        return proposal

    def expire_due(self, now: Optional[datetime] = None) -> List[ORBProposal]:
        """Auto-expire pending proposals whose ``expires_at`` cutoff has passed."""
        moment = now or self._now()
        expired: List[ORBProposal] = []
        with self._lock:
            due = [
                p for p in self._proposals.values()
                if p.status == ProposalStatus.PENDING.value
                and _is_past(p.expires_at, moment)
            ]
        for proposal in due:
            try:
                expired.append(self.expire(proposal.proposal_id, ExpiryReason.ENTRY_CUTOFF))
            except ProposalError:
                # Another thread may have already transitioned this proposal
                # (e.g., to SKIPPED) between the snapshot above and this call.
                # This is expected under concurrent usage; skip it silently.
                logger.debug(
                    "expire_due: skipping proposal %s — already transitioned",
                    proposal.proposal_id,
                )
        return expired

    # ---- helpers -----------------------------------------------------
    def _require(self, proposal_id: str) -> ORBProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"proposal '{proposal_id}' not found")
        return proposal

    def _log(self, action: str, proposal: ORBProposal, extra: Dict[str, Any]) -> None:
        self._audit.log_decision({
            "kind": _AUDIT_KIND,
            "action": action,
            "proposal_id": proposal.proposal_id,
            "strategy": proposal.strategy_name,
            "symbol": proposal.symbol,
            "session_date": proposal.session_date,
            "status": proposal.status,
            "recommend_only": proposal.recommend_only,
            **extra,
        })


def _is_past(expires_at: Optional[str], moment: datetime) -> bool:
    if not expires_at:
        return False
    try:
        deadline = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment >= deadline
